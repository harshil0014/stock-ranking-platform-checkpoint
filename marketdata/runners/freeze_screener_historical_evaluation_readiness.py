"""Freeze an outcome-blind readiness audit for the Screener historical extension."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.historical_evaluation_readiness import (  # noqa: E402
    RANKING_DATES,
    audit_historical_evaluation_readiness,
    canonical_json_bytes,
    sha256_file,
)
from stock_ranker.screener_historical_fundamentals import (  # noqa: E402
    build_screener_pit_cohorts,
    official_clock_from_availability,
)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(
        path, index=False, encoding="utf-8", lineterminator="\n",
        float_format="%.17g",
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )


def _verify_inventory(root: Path) -> None:
    inventory = json.loads((root / "artifact_inventory.json").read_text(encoding="utf-8"))
    for record in inventory:
        path = root / record["path"]
        if not path.is_file() or path.stat().st_size != int(record["size"]):
            raise ValueError(f"batch inventory size/path mismatch: {path}")
        if sha256_file(path) != record["sha256"]:
            raise ValueError(f"batch inventory hash mismatch: {path}")


def _targeted_data_fix(
    blind_root: Path,
    selected: pd.DataFrame,
    identities: pd.DataFrame,
    availability: pd.DataFrame,
    final_membership: pd.DataFrame,
) -> pd.DataFrame:
    selected_keys = set(zip(
        selected["ranking_date"].astype(str), selected["ticker"].astype(str)
    ))
    exact_identity = identities.loc[
        identities["screener_exact_isin_match"].astype(str).str.lower().eq("true")
    ].drop_duplicates("reference_nse_code").set_index("reference_nse_code")
    availability = availability.copy()
    availability["pit_available"] = availability["pit_available"].astype(str).str.lower().eq("true")
    exact_clock = set(zip(
        availability.loc[availability["pit_available"], "ranking_date"].astype(str),
        availability.loc[availability["pit_available"], "ticker"].astype(str),
    ))
    rows: list[dict[str, object]] = []
    for ranking_date in RANKING_DATES:
        snapshot = blind_root / ranking_date
        universe = pd.read_csv(snapshot / "historical_universe.csv", dtype=str)
        universe = universe.loc[universe["investable"].astype(str).str.lower().eq("true")]
        provenance = json.loads((snapshot / "provenance.json").read_text(encoding="utf-8"))
        reviewed_clock = set(provenance.get("fundamental_provenance", {}))
        existing = final_membership.loc[
            final_membership["ranking_date"].astype(str).eq(ranking_date)
        ]
        sector_counts = existing.groupby("sector").size().to_dict()
        selected_tickers = set(existing["ticker"].astype(str))
        candidates = []
        for item in universe.to_dict("records"):
            ticker = str(item["historical_symbol"])
            if ticker in selected_tickers or (ranking_date, ticker) in selected_keys:
                continue
            identity = exact_identity.loc[ticker] if ticker in exact_identity.index else None
            has_exact_isin = identity is not None and isinstance(identity, pd.Series)
            has_clock = (ranking_date, ticker) in exact_clock or ticker in reviewed_clock
            if not has_exact_isin or str(item["historical_sector"]) == "Financial Services":
                continue
            candidates.append({
                "priority_year": ranking_date[:4],
                "ranking_date": ranking_date,
                "ticker": ticker,
                "company": item["company"],
                "sector": item["historical_sector"],
                "isin": str(identity["isin"]) if has_exact_isin else "",
                "screener_url": f"https://www.screener.in/company/{ticker}/" if has_exact_isin else "",
                "exact_identity_available": has_exact_isin,
                "exact_official_clock_available": has_clock,
                "targeted_action": (
                    "SCREENER_WORKBOOK_AFTER_CLOCK_VERIFICATION"
                    if has_clock else "OFFICIAL_CLOCK_RESCUE_BEFORE_WORKBOOK"
                ),
            })
        chosen: list[dict[str, object]] = []
        while (
            len(selected_tickers) < 10
            or sum(count >= 3 for count in sector_counts.values()) < 2
        ):
            remaining = [item for item in candidates if item["ticker"] not in selected_tickers]
            if not remaining:
                break
            remaining.sort(key=lambda item: (
                -int(bool(item["exact_official_clock_available"])),
                -min(int(sector_counts.get(str(item["sector"]), 0)), 2),
                str(item["ticker"]),
            ))
            item = remaining[0]
            chosen.append(item)
            selected_tickers.add(str(item["ticker"]))
            sector = str(item["sector"])
            sector_counts[sector] = int(sector_counts.get(sector, 0)) + 1
        rows.extend(chosen)
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    grouped = []
    for ticker, group in result.groupby("ticker", sort=True):
        first = group.sort_values("ranking_date", kind="stable").iloc[0]
        needs_clock = group["exact_official_clock_available"].eq(False).any()
        grouped.append({
            "priority": min(int(value[:4]) for value in group["ranking_date"]),
            "ticker": ticker,
            "company": first["company"],
            "isin": first["isin"],
            "sector": first["sector"],
            "screener_url": first["screener_url"],
            "historical_dates_helped": "|".join(sorted(group["ranking_date"].unique())),
            "exact_identity_available": bool(first["exact_identity_available"]),
            "exact_official_clock_available_for_all_dates": not needs_clock,
            "targeted_action": (
                "OFFICIAL_CLOCK_RESCUE_BEFORE_WORKBOOK"
                if needs_clock else "SCREENER_WORKBOOK_AFTER_CLOCK_VERIFICATION"
            ),
        })
    return pd.DataFrame(grouped).sort_values(
        ["priority", "targeted_action", "ticker"], kind="stable"
    ).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", action="append", type=Path, required=True)
    parser.add_argument("--combined-normalized", type=Path, required=True)
    parser.add_argument("--availability", type=Path, required=True)
    parser.add_argument("--identity-master", type=Path, required=True)
    parser.add_argument("--prospective-counts", type=Path, required=True)
    parser.add_argument("--blind-root", type=Path, required=True)
    parser.add_argument("--outcome-cache", type=Path, required=True)
    parser.add_argument("--outcome-history-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--targeted-input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError(f"output directory already exists: {args.output}")

    batch_dirs = sorted(args.batch_dir, key=lambda path: path.as_posix())
    if not batch_dirs:
        raise ValueError("at least one accepted batch directory is required")
    attempted_total = accepted_total = quarantined_total = 0
    for path in batch_dirs:
        _verify_inventory(path)
        audit = pd.read_csv(path / "file_audit.csv")
        summary = json.loads((path / "batch_summary.json").read_text(encoding="utf-8"))
        if len(audit) != int(summary["attempted_files"]):
            raise ValueError(f"batch audit count disagrees with summary: {path}")
        if not audit["file_status"].isin(["ACCEPTED", "QUARANTINED"]).all():
            raise ValueError(f"batch contains an unknown file status: {path}")
        attempted_total += len(audit)
        accepted_total += int(audit["file_status"].eq("ACCEPTED").sum())
        quarantined_total += int(audit["file_status"].eq("QUARANTINED").sum())

    normalized = pd.read_csv(args.combined_normalized)
    availability = pd.read_csv(args.availability, dtype=str)
    clock = official_clock_from_availability(availability)
    rebuilt = build_screener_pit_cohorts(
        normalized, clock, [pd.Timestamp(value).date() for value in RANKING_DATES]
    )
    identities = pd.read_csv(args.identity_master, dtype=str)
    exact_identities = identities.loc[
        identities["screener_exact_isin_match"].astype(str).str.lower().eq("true")
        & identities["reference_nse_code"].notna()
        & identities["reference_nse_code"].ne("")
    ].copy()
    canonical_identities = exact_identities.assign(
        ticker=exact_identities["reference_nse_code"]
    )[["ticker", "company", "isin"]].drop_duplicates()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    outcome_date_frames = []
    outcome_history_hashes: dict[str, str] = {}
    for ranking_date in RANKING_DATES:
        universe = pd.read_csv(
            args.blind_root / ranking_date / "historical_universe.csv", dtype=str
        )
        tickers = universe.loc[
            universe["investable"].astype(str).str.lower().eq("true"),
            "historical_symbol",
        ].astype(str)
        for ticker in sorted(tickers.unique()):
            path = args.outcome_history_root / f"{ticker}.csv"
            if not path.is_file():
                continue
            dates = pd.read_csv(path, usecols=["date"], dtype=str)
            dates.insert(0, "ticker", ticker)
            dates.insert(0, "ranking_date", ranking_date)
            outcome_date_frames.append(dates)
            outcome_history_hashes[path.name] = sha256_file(path)
    outcome_dates = pd.concat(outcome_date_frames, ignore_index=True)
    result = audit_historical_evaluation_readiness(
        screener_selected=rebuilt.accepted,
        identity_master=canonical_identities,
        prospective_counts=pd.read_csv(args.prospective_counts),
        blind_root=args.blind_root,
        outcome_dates=outcome_dates,
        protocol=protocol,
    )
    target = _targeted_data_fix(
        args.blind_root, rebuilt.accepted, identities, availability,
        result.cohort_membership,
    )
    target_resolution_rows = []
    if args.targeted_input:
        supplied_targets = pd.read_csv(args.targeted_input, dtype=str, keep_default_na=False)
        selected_lookup = rebuilt.accepted.copy()
        selected_lookup["ranking_date"] = selected_lookup["ranking_date"].astype(str)
        for supplied in supplied_targets.to_dict("records"):
            for ranking_date in str(supplied["historical_dates_helped"]).split("|"):
                match = selected_lookup.loc[
                    selected_lookup["ranking_date"].eq(ranking_date)
                    & selected_lookup["ticker"].astype(str).eq(str(supplied["ticker"]))
                ]
                if len(match) == 1:
                    chosen = match.iloc[0]
                    target_resolution_rows.append({
                        "ranking_date": ranking_date, "ticker": supplied["ticker"],
                        "isin": supplied["isin"], "clock_status": "EXACT_OFFICIAL_CLOCK_SELECTED",
                        "selected_period_end": str(chosen["period_end"])[:10],
                        "official_available_at": str(chosen["official_available_at"]),
                        "official_filing_url": chosen["official_filing_url"],
                    })
                else:
                    target_resolution_rows.append({
                        "ranking_date": ranking_date, "ticker": supplied["ticker"],
                        "isin": supplied["isin"], "clock_status": "CLOCK_UNRESOLVED",
                        "selected_period_end": "", "official_available_at": "",
                        "official_filing_url": "",
                    })
    target_resolution = pd.DataFrame(target_resolution_rows)
    exclusion_counts = (
        result.exclusions.groupby(["ranking_date", "reason_code"], sort=True)
        .size().rename("security_count").reset_index()
    )
    report = dict(result.report)
    report.update({
        "batch_workbooks_attempted": attempted_total,
        "batch_workbooks_accepted": accepted_total,
        "batch_workbooks_quarantined": quarantined_total,
        "corrected_screener_selected_counts": {
            str(key): int(value) for key, value in rebuilt.accepted.groupby("ranking_date")["isin"].nunique().items()
            if str(key) in RANKING_DATES
        },
        "targeted_data_fix_count": int(len(target)),
        "targeted_required_date_count": int(len(target_resolution)),
        "targeted_clock_resolved_count": int(
            target_resolution.get("clock_status", pd.Series(dtype=str))
            .eq("EXACT_OFFICIAL_CLOCK_SELECTED").sum()
        ),
        "targeted_general_batch_recommended": False,
        "input_fingerprints": {
            "combined_normalized": sha256_file(args.combined_normalized),
            "official_availability": sha256_file(args.availability),
            "identity_master": sha256_file(args.identity_master),
            "prospective_counts": sha256_file(args.prospective_counts),
            "blind_manifest": sha256_file(args.blind_root / "manifest.json"),
            "outcome_cache_manifest": sha256_file(args.outcome_cache / "cache_manifest.json"),
            "outcome_price_file": sha256_file(args.outcome_cache / "outcome_prices.csv"),
            "outcome_history_files": outcome_history_hashes,
            "protocol": sha256(canonical_json_bytes(protocol)).hexdigest(),
        },
    })

    args.output.mkdir(parents=True)
    outputs = {
        "cohort_membership.csv": result.cohort_membership,
        "exclusions.csv": result.exclusions,
        "exclusion_counts.csv": exclusion_counts,
        "cohort_summary.csv": result.cohort_summary,
        "sector_distribution.csv": result.sector_distribution,
        "corrected_screener_pit_selected.csv": rebuilt.accepted,
        "corrected_screener_pit_rejected.csv": rebuilt.rejected,
        "targeted_data_fix.csv": target,
        "targeted_clock_resolution.csv": target_resolution,
    }
    for name, frame in outputs.items():
        _write_csv(args.output / name, frame)
    _write_json(args.output / "evaluation_protocol.json", protocol)
    _write_json(args.output / "readiness_report.json", report)
    inventory = [
        {
            "path": path.relative_to(args.output).as_posix(),
            "sha256": sha256_file(path), "size": path.stat().st_size,
        }
        for path in sorted(args.output.iterdir(), key=lambda item: item.name)
        if path.is_file() and path.name != "artifact_inventory.json"
    ]
    _write_json(args.output / "artifact_inventory.json", inventory)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
