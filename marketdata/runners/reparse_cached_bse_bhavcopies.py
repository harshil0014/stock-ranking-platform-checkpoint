"""Reparse locally cached official BSE bhavcopies for unresolved exact identities.

This utility performs no network access and never writes adjusted histories.  It
recovers auditable raw OHLC observations so the existing corporate-action
readiness pipeline can decide whether a series is safe to promote.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_ranker.company_facts import (  # noqa: E402
    load_company_fact_snapshot,
    resolve_company_fact_snapshot,
)

from recover_bse_history_from_bhavcopy import (  # noqa: E402
    parse_legacy_zip,
    parse_udiff_csv,
)
from audit_bse_adjustment_readiness import (  # noqa: E402
    find_phase1,
    load_phase1_histories,
    merge_history,
)


DEFAULT_BHAVCOPY_ROOT = Path.home() / "Downloads" / "BSE_History_Bhavcopy_Fallback" / "raw"
DEFAULT_FACT_ROOT = ROOT / "data" / "company_facts"
LEGACY_NAME = re.compile(r"EQ(\d{2})(\d{2})(\d{2})_CSV\.ZIP$", re.I)
UDIFF_NAME = re.compile(r"BhavCopy_BSE_CM_0_0_0_(\d{8})_F_0000\.CSV$", re.I)


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    with pending.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    pending.replace(path)


def _date_from_path(path: Path):
    legacy = LEGACY_NAME.fullmatch(path.name)
    if legacy:
        day, month, year = legacy.groups()
        return datetime.strptime(f"{day}{month}{year}", "%d%m%y").date(), "LEGACY"
    udiff = UDIFF_NAME.fullmatch(path.name)
    if udiff:
        return datetime.strptime(udiff.group(1), "%Y%m%d").date(), "UDIFF"
    return None


def unresolved_mapping(company_fact_root: Path, cohort: Path | None = None) -> dict[str, dict[str, str]]:
    bundle = load_company_fact_snapshot(resolve_company_fact_snapshot(company_fact_root))
    facts = bundle.facts
    selected = facts.loc[facts["primary_exchange"].astype(str).str.upper().eq("BSE")]
    if cohort is None:
        selected = selected.loc[
            selected["product_baseline_reason_code"].astype(str).eq("PRICE_HISTORY_UNAVAILABLE")
        ]
    else:
        with cohort.open("r", encoding="utf-8-sig", newline="") as handle:
            requested = list(csv.DictReader(handle))
        if not requested or not {"bse_code", "isin"}.issubset(requested[0]):
            raise ValueError("--cohort requires bse_code and isin columns")
        exact = {
            (str(row["bse_code"]).strip().removesuffix(".0").zfill(6), str(row["isin"]).strip())
            for row in requested
        }
        selected = selected.loc[selected.apply(
            lambda row: (str(row["exchange_security_id"]).strip().split(".", 1)[0].zfill(6), str(row["isin"]).strip()) in exact,
            axis=1,
        )]
        found = {
            (str(row["exchange_security_id"]).strip().split(".", 1)[0].zfill(6), str(row["isin"]).strip())
            for row in selected.to_dict("records")
        }
        if found != exact:
            raise ValueError(f"cohort identities do not exactly match accepted facts: {sorted(exact - found)[:5]}")
    result: dict[str, dict[str, str]] = {}
    for row in selected.to_dict("records"):
        code = str(row["exchange_security_id"]).strip().split(".", 1)[0].zfill(6)
        ticker = str(row["ticker"])
        if not re.fullmatch(r"\d{6}", code) or ticker != f"BSE-{code}":
            raise ValueError(f"invalid exact BSE identity: {ticker}/{code}")
        result[code] = {
            "ticker": ticker,
            "isin": str(row["isin"]).strip(),
            "company": str(row["company"]).strip(),
        }
    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output_root.resolve()
    if output.exists():
        raise FileExistsError(f"output must be fresh: {output}")
    mapping = unresolved_mapping(
        args.company_fact_root.resolve(), args.cohort.resolve() if args.cohort else None
    )
    wanted = set(mapping)
    rows_by_code: dict[str, list[dict[str, Any]]] = {code: [] for code in wanted}
    file_inventory: list[dict[str, Any]] = []
    identity_conflicts: list[dict[str, Any]] = []

    bhavcopy_roots = args.bhavcopy_root or [DEFAULT_BHAVCOPY_ROOT]
    for path in sorted(
        candidate
        for root in bhavcopy_roots
        for candidate in root.resolve().rglob("*")
    ):
        if not path.is_file():
            continue
        parsed_name = _date_from_path(path)
        if parsed_name is None:
            continue
        trade_date, kind = parsed_name
        raw = path.read_bytes()
        parsed = (
            parse_legacy_zip(raw, trade_date, wanted)
            if kind == "LEGACY"
            else parse_udiff_csv(raw, trade_date, wanted)
        )
        for row in parsed:
            expected_isin = mapping[row["bse_code"]]["isin"]
            observed_isin = str(row.get("isin") or "").strip()
            if kind == "UDIFF" and observed_isin != expected_isin:
                identity_conflicts.append({
                    "date": row["date"], "bse_code": row["bse_code"],
                    "expected_isin": expected_isin, "observed_isin": observed_isin,
                    "source_file": path.name,
                })
                continue
            rows_by_code[row["bse_code"]].append(row)
        file_inventory.append({
            "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw), "format": kind, "matched_rows": len(parsed),
        })

    phase1 = load_phase1_histories(find_phase1(Path.home() / "Downloads", args.phase1))
    audits: list[dict[str, Any]] = []
    output_fields = [
        "date", "bse_code", "isin", "ticker", "open", "high", "low", "close",
        "volume", "trades", "turnover", "source", "source_file",
    ]
    for code in sorted(wanted):
        conflicts = [row for row in identity_conflicts if row["bse_code"] == code]
        combined = merge_history(code, [rows_by_code[code], phase1.get(code, [])])
        status = "RAW_HISTORY_RECOVERED"
        if conflicts:
            status = "UDIFF_ISIN_CONFLICT"
        elif not combined:
            status = "NO_OFFICIAL_RAW_HISTORY"
        if combined:
            normalized = []
            for row in combined:
                normalized.append({field: row.get(field, "") for field in output_fields})
            _write_csv(output / "raw_history" / f"BSE-{code}.csv", normalized, output_fields)
        audits.append({
            "bse_code": code,
            **mapping[code],
            "status": status,
            "rows": len(combined),
            "first_date": combined[0]["date"] if combined else "",
            "last_date": combined[-1]["date"] if combined else "",
            "udiff_exact_isin_rows": sum(
                1 for row in rows_by_code[code] if str(row.get("isin") or "") == mapping[code]["isin"]
            ),
            "udiff_isin_conflicts": len(conflicts),
            "legacy_code_only_rows": sum(
                1 for row in rows_by_code[code] if row.get("source") == "BSE_LEGACY_BHAVCOPY"
            ),
            "phase1_rows": len(phase1.get(code, [])),
        })

    _write_csv(output / "per_code_audit.csv", audits, list(audits[0]))
    _write_csv(
        output / "identity_conflicts.csv",
        identity_conflicts,
        ["date", "bse_code", "expected_isin", "observed_isin", "source_file"],
    )
    _write_csv(
        output / "source_inventory.csv",
        file_inventory,
        ["path", "sha256", "size", "format", "matched_rows"],
    )
    summary = {
        "target_count": len(mapping),
        "status_counts": {
            status: sum(row["status"] == status for row in audits)
            for status in sorted({row["status"] for row in audits})
        },
        "codes_with_raw_history": sum(row["rows"] > 0 for row in audits),
        "total_rows": sum(row["rows"] for row in audits),
        "identity_conflicts": len(identity_conflicts),
        "network_access": False,
        "adjusted_history_written": False,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return summary


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--company-fact-root", type=Path, default=DEFAULT_FACT_ROOT)
    value.add_argument("--cohort", type=Path, help="Exact bse_code/isin CSV cohort.")
    value.add_argument(
        "--bhavcopy-root", type=Path, action="append",
        help="Cached bhavcopy root; repeat to merge non-overlapping cache generations.",
    )
    value.add_argument("--phase1", type=Path)
    value.add_argument("--output-root", type=Path, required=True)
    return value


def main(argv: list[str] | None = None) -> int:
    try:
        print(json.dumps(run(parser().parse_args(argv)), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"cached BSE reparse failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
