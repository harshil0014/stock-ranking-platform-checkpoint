"""Build an isolated exact-identity BSE adjusted-history recovery candidate."""

from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import shutil
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
from audit_bse_adjustment_readiness import (  # noqa: E402
    parse_bonus_factor,
    parse_bse_date,
    parse_dividend_amount,
    parse_split_factor,
    prior_close,
)
from build_bse_candidate_history_cache import apply_backward_adjustments  # noqa: E402


PRICE_TYPES = {"DIVIDEND", "BONUS", "SPLIT", "RIGHTS"}
IDENTITY_RISK_WORDS = ("spin off", "demerger", "capital reduction", "reduction of capital")


def action_affects_observed_history(event: dict[str, str], first: date, last: date) -> bool:
    ex = parse_bse_date(event.get("ex_date", ""))
    return ex is None or first < ex <= last


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    with pending.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    pending.replace(path)


def finite_positive(value: Any, label: str) -> float:
    try:
        result = float(value)
    except Exception as exc:
        raise ValueError(f"{label} is not numeric") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return result


def load_facts(root: Path) -> tuple[dict[str, dict[str, Any]], str]:
    bundle = load_company_fact_snapshot(resolve_company_fact_snapshot(root))
    mapping: dict[str, dict[str, Any]] = {}
    for row in bundle.facts.loc[
        bundle.facts["primary_exchange"].astype(str).str.upper().eq("BSE")
    ].to_dict("records"):
        code = str(row["exchange_security_id"]).strip().split(".", 1)[0].zfill(6)
        if str(row["ticker"]) != f"BSE-{code}":
            raise ValueError(f"invalid accepted BSE identity for {code}")
        mapping[code] = row
    return mapping, str(bundle.manifest["fingerprint"])


def load_raw(path: Path, code: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in read_csv(path):
        day = str(row.get("date", "")).strip()
        date.fromisoformat(day)
        if day in seen:
            raise ValueError(f"{code}: duplicate raw date {day}")
        seen.add(day)
        got = str(row.get("bse_code", "")).strip().zfill(6)
        if got != code:
            raise ValueError(f"{code}: raw row belongs to {got}")
        close = finite_positive(row.get("close"), f"{code}/{day}/close")
        result.append({
            "date": day, "close": close, "raw_close": close,
            "adjusted_close": close, "source_isin": str(row.get("isin", "")).strip(),
        })
    return sorted(result, key=lambda row: row["date"])


def verify_rights_evidence(row: dict[str, str], evidence_root: Path) -> None:
    source = evidence_root / row["source_file"]
    if not source.is_file() or source.read_bytes()[:5] != b"%PDF-":
        raise ValueError(f"invalid rights evidence: {source}")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != row["source_sha256"]:
        raise ValueError(f"rights evidence hash drift: {source.name}")


def action_factor(
    event: dict[str, str],
    history: list[dict[str, Any]],
    rights: dict[tuple[str, str], dict[str, str]],
    evidence_root: Path,
) -> tuple[dict[str, Any] | None, str]:
    code = event["bse_code"]
    event_type = event["event_type"].upper()
    ex = parse_bse_date(event.get("ex_date", ""))
    if ex is None:
        return None, "official action has no parseable ex-date"
    prior = prior_close(history, ex)
    # Split and bonus factors come directly from the official security terms;
    # unlike cash dividends and rights TERP, they do not require a nearby
    # market close. This matters for legitimately suspended/illiquid shares.
    if prior is None and event_type in {"DIVIDEND", "RIGHTS"}:
        return None, "no raw close within 14 days before ex-date"
    prior_day, prior_value = prior if prior is not None else ("", float("nan"))
    purpose = event.get("purpose", "")
    method = ""
    factor: float | None = None
    if event_type == "DIVIDEND":
        amount, method = parse_dividend_amount(purpose)
        if amount is not None and 0 <= amount < prior_value:
            factor = (prior_value - amount) / prior_value
    elif event_type == "BONUS":
        factor, method = parse_bonus_factor(purpose)
    elif event_type == "SPLIT":
        factor, method = parse_split_factor(purpose)
    elif event_type == "RIGHTS":
        decision = rights.get((code, ex.isoformat()))
        if not decision or decision.get("decision") != "ALLOW":
            return None, "rights terms lack accepted official adjudication"
        verify_rights_evidence(decision, evidence_root)
        new = finite_positive(decision["rights_shares"], "rights_shares")
        old = finite_positive(decision["existing_shares"], "existing_shares")
        price = finite_positive(decision["issue_price"], "issue_price")
        factor = ((prior_value * old + price * new) / (old + new)) / prior_value
        method = f"official_rights_terp:{new:g}:{old:g}@{price:g}"
    if factor is None or not math.isfinite(float(factor)) or not 0 < float(factor) <= 1.5:
        return None, method or "action factor is unresolved or implausible"
    return ({
        "ex_date": ex.isoformat(), "factor": float(factor), "event_type": event_type,
        "purpose": purpose, "method": method, "prior_trade_date": prior_day,
        "prior_raw_close": prior_value if prior is not None else "",
    }, "")


def run(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output_cache.resolve()
    if output.exists():
        raise FileExistsError(f"output must be fresh: {output}")
    output.mkdir(parents=True)
    for source in sorted(args.existing_cache.resolve().glob("*.csv")):
        shutil.copy2(source, output / source.name)

    facts, fact_fingerprint = load_facts(args.company_fact_root.resolve())
    audits = {row["bse_code"].zfill(6): row for row in read_csv(args.raw_audit.resolve())}
    identity = {row["bse_code"].zfill(6): row for row in read_csv(args.identity_decisions.resolve())}
    rights_rows = read_csv(args.rights_decisions.resolve())
    rights = {(row["bse_code"].zfill(6), row["ex_date"]): row for row in rights_rows}
    events_by_code: dict[str, list[dict[str, str]]] = {}
    for row in read_csv(args.events.resolve()):
        events_by_code.setdefault(row["bse_code"].zfill(6), []).append(row)

    decisions: list[dict[str, Any]] = []
    action_evidence: list[dict[str, Any]] = []
    for code, audit in sorted(audits.items()):
        if int(audit["rows"]) <= 0:
            continue
        row = facts.get(code)
        if row is None or str(row["isin"]).strip() != audit["isin"].strip():
            raise ValueError(f"{code}: accepted identity drift")
        blockers: list[str] = []
        if int(audit["udiff_isin_conflicts"]) != 0:
            blockers.append("UDIFF_ISIN_CONFLICT")
        identity_row = identity.get(code)
        if identity_row and identity_row["decision"] != "ALLOW":
            blockers.append(f"IDENTITY:{identity_row['reason']}")

        history = load_raw(args.raw_root.resolve() / f"BSE-{code}.csv", code)
        trade_date = str(row["trade_date"])
        history = [item for item in history if item["date"] <= trade_date]
        if identity_row and identity_row.get("history_start_boundary", "").strip():
            boundary = date.fromisoformat(identity_row["history_start_boundary"].strip()).isoformat()
            history = [item for item in history if item["date"] >= boundary]
            # Boundary adjudications deliberately discard legacy/code-only rows;
            # only UDiFF observations explicitly carrying the current ISIN survive.
            history = [item for item in history if item["source_isin"] == str(row["isin"]).strip()]
        if not history:
            raise ValueError(f"{code}: no raw history on or before accepted trade date")
        first_observed = date.fromisoformat(history[0]["date"])
        last_observed = date.fromisoformat(history[-1]["date"])
        factors: list[dict[str, Any]] = []
        for event in events_by_code.get(code, []):
            event_type = event["event_type"].upper()
            purpose_lower = event.get("purpose", "").lower()
            # An action outside the observed interval cannot affect any retained
            # close: pre-history rows are already post-action, and post-snapshot
            # actions must not enter the accepted current product state.
            if not action_affects_observed_history(event, first_observed, last_observed):
                continue
            if event_type not in PRICE_TYPES:
                if any(word in purpose_lower for word in IDENTITY_RISK_WORDS):
                    blockers.append(f"UNRESOLVED_SECURITY_EVENT:{event.get('purpose', '')}")
                continue
            factor, error = action_factor(event, history, rights, args.evidence_root.resolve())
            if error:
                blockers.append(f"{event_type}:{error}")
            else:
                assert factor is not None
                factors.append(factor)

        duplicate_dates = {f["ex_date"] for f in factors if sum(x["ex_date"] == f["ex_date"] for x in factors) > 1}
        if duplicate_dates:
            blockers.append(f"MULTIPLE_ACTIONS_SAME_DATE:{sorted(duplicate_dates)}")

        if blockers:
            decisions.append({
                "bse_code": code, "ticker": row["ticker"], "isin": row["isin"],
                "status": "QUARANTINED", "raw_rows": len(history),
                "first_date": history[0]["date"], "last_date": history[-1]["date"],
                "actions_applied": 0, "reason": " | ".join(blockers),
            })
            continue

        adjusted = apply_backward_adjustments(history, factors)
        latest = finite_positive(row["latest_price"], f"{code}/latest_price")
        by_date = {item["date"]: item for item in adjusted}
        by_date[trade_date] = {"date": trade_date, "raw_close": latest, "adjusted_close": latest}
        adjusted = [by_date[key] for key in sorted(by_date)]
        write_csv(output / f"BSE-{code}.csv", adjusted, ["date", "raw_close", "adjusted_close"])
        for factor in factors:
            action_evidence.append({"bse_code": code, **factor})
        decisions.append({
            "bse_code": code, "ticker": row["ticker"], "isin": row["isin"],
            "status": "PROMOTED_TO_CANDIDATE", "raw_rows": len(history),
            "first_date": adjusted[0]["date"], "last_date": adjusted[-1]["date"],
            "actions_applied": len(factors), "reason": "",
        })

    report_root = output.parent / f"{output.name}_audit"
    report_root.mkdir(parents=True, exist_ok=False)
    write_csv(report_root / "per_code_decision.csv", decisions, list(decisions[0]))
    write_csv(report_root / "applied_action_factors.csv", action_evidence, [
        "bse_code", "ex_date", "factor", "event_type", "purpose", "method",
        "prior_trade_date", "prior_raw_close",
    ])
    summary = {
        "company_fact_fingerprint": fact_fingerprint,
        "codes_with_raw_history": len(decisions),
        "promoted": sum(row["status"] == "PROMOTED_TO_CANDIDATE" for row in decisions),
        "quarantined": sum(row["status"] == "QUARANTINED" for row in decisions),
        "actions_applied": len(action_evidence),
        "network_access": False,
        "exact_identity_only": True,
        "output_cache": str(output),
    }
    (report_root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return summary


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--company-fact-root", type=Path, default=ROOT / "data/company_facts")
    value.add_argument("--existing-cache", type=Path, default=ROOT / "data/live_market/history_cache")
    value.add_argument("--raw-root", type=Path, required=True)
    value.add_argument("--raw-audit", type=Path, required=True)
    value.add_argument("--events", type=Path, required=True)
    value.add_argument("--identity-decisions", type=Path, default=ROOT / "marketdata/specifications/bse_history_identity_adjudications.csv")
    value.add_argument("--rights-decisions", type=Path, default=ROOT / "marketdata/specifications/bse_history_rights_adjudications.csv")
    value.add_argument("--evidence-root", type=Path, required=True)
    value.add_argument("--output-cache", type=Path, required=True)
    return value


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(parser().parse_args(argv))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"official BSE history recovery failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
