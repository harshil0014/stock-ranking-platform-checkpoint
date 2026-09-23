"""Freeze point-in-time personalized-model cohorts after official data recovery."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
import time
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_ranker.personalized import InvestorProfile
from stock_ranker.personalized_recovery import classify_profile_eligibility, recover_history_book


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def load_nse_bridge(root: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(root.glob("*.zip")):
        with ZipFile(path) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(members) != 1 or ".." in Path(members[0]).parts:
                raise ValueError(f"unsafe NSE archive {path}")
            frame = pd.read_csv(archive.open(members[0]), usecols=["TradDt", "ISIN", "TckrSymb", "SctySrs", "ClsPric"])
        frame = frame.loc[frame.SctySrs.isin(["EQ", "BE", "BZ", "SM", "ST", "MT"])].rename(
            columns={"TradDt": "trade_date", "ISIN": "isin", "TckrSymb": "ticker", "ClsPric": "close"}
        )
        rows.append(frame[["trade_date", "isin", "ticker", "close"]])
    return pd.concat(rows, ignore_index=True).drop_duplicates(["trade_date", "isin"])


def archive_coverage(old_db: Path, new_db: Path, start: str, end: str) -> dict:
    old = sqlite3.connect(old_db)
    new = sqlite3.connect(new_db)
    try:
        left = pd.read_sql("SELECT trade_date AS day,status FROM daily_files", old)
        right = pd.read_sql("SELECT day,status FROM days", new)
    finally:
        old.close(); new.close()
    days = pd.concat([left, right], ignore_index=True).drop_duplicates("day", keep="last")
    days.day = pd.to_datetime(days.day)
    expected = pd.date_range(start, end, freq="B")
    selected = days.loc[days.day.isin(expected)]
    missing = expected.difference(selected.day)
    failed = selected.loc[~selected.status.isin(["OK", "NO_FILE"])]
    return {
        "start": start, "end": end, "expected_weekdays": len(expected),
        "recorded_weekdays": len(selected), "missing_weekdays": len(missing),
        "failed_weekdays": len(failed), "complete": len(missing) == 0 and len(failed) == 0,
        "status_counts": selected.status.value_counts().sort_index().to_dict(),
    }


def official_evidence(facts: pd.DataFrame, raw_audit: Path, decisions: Path, complete: bool) -> pd.DataFrame:
    raw = pd.read_csv(raw_audit, dtype={"bse_code": "string"}).fillna("")
    dec = pd.read_csv(decisions, dtype={"bse_code": "string"}).fillna("")
    raw.bse_code = raw.bse_code.str.zfill(6); dec.bse_code = dec.bse_code.str.zfill(6)
    dec = dec[["bse_code", "status", "reason"]].rename(columns={"status": "official_recovery_status", "reason": "official_recovery_reason"})
    evidence = raw.merge(dec, on="bse_code", how="left", validate="one_to_one")
    evidence.loc[evidence.official_recovery_status.eq(""), "official_recovery_status"] = "NO_OFFICIAL_RAW_HISTORY"
    evidence["official_archive_complete"] = bool(complete)
    evidence = evidence.rename(columns={"first_date": "first_official_date", "last_date": "last_official_date"})
    expected = facts[["isin", "primary_exchange", "exchange_security_id"]].copy()
    expected["bse_code"] = expected.exchange_security_id.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    evidence = evidence.merge(expected.loc[expected.primary_exchange.eq("BSE"), ["isin", "bse_code"]], on=["isin", "bse_code"], validate="one_to_one")
    return evidence[["isin", "bse_code", "official_recovery_status", "official_recovery_reason", "official_archive_complete", "first_official_date", "last_official_date", "rows", "udiff_exact_isin_rows", "udiff_isin_conflicts"]]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--history-cache", type=Path, required=True)
    p.add_argument("--nse-bridge", type=Path, required=True)
    p.add_argument("--bse-raw-audit", type=Path, required=True)
    p.add_argument("--bse-decisions", type=Path, required=True)
    p.add_argument(
        "--bse-actions", type=Path, action="append", required=True,
        help="Normalized structured-action CSV; repeat for disjoint acquisition shards.",
    )
    p.add_argument("--bse-source-inventory", type=Path, required=True)
    p.add_argument("--bse-old-db", type=Path, required=True)
    p.add_argument("--bse-new-db", type=Path, required=True)
    args = p.parse_args(argv)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("fresh output required")
    output.mkdir(parents=True)
    started = time.perf_counter()
    protected = [ROOT / "data/company_facts/accepted_state.json", ROOT / "data/live_market/accepted_state.json"]
    before = {str(x.relative_to(ROOT)): digest(x) for x in protected}
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    market_state = json.loads((ROOT / "data/live_market/accepted_state.json").read_text(encoding="utf-8"))
    live_path = ROOT / "data/live_market" / market_state["bundle_path"] / "live_market.csv"
    live = pd.read_csv(live_path, low_memory=False)
    actions_path = ROOT / "data/company_facts/providers/official_exchange/automatic-20260920T023321Z/corporate_actions.csv"
    actions = pd.read_csv(actions_path, low_memory=False)
    cutoff = market_state["trade_date"]
    coverage = archive_coverage(args.bse_old_db, args.bse_new_db, "2021-09-18", cutoff)
    if not coverage["complete"]:
        raise ValueError(f"BSE archive is incomplete: {coverage}")
    evidence = official_evidence(facts, args.bse_raw_audit, args.bse_decisions, True)
    recovered = recover_history_book(
        facts, args.history_cache, live, actions, as_of_date=cutoff,
        official_price_bridge=load_nse_bridge(args.nse_bridge),
    )
    recovered.history_audit.to_csv(output / "history_quality_audit.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    recovered.repairs.to_csv(output / "terminal_repairs.csv", index=False, lineterminator="\n")
    evidence.to_csv(output / "official_bse_recovery_evidence.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    bse_actions = pd.concat(
        [pd.read_csv(path, low_memory=False) for path in args.bse_actions],
        ignore_index=True,
    ).drop_duplicates().sort_values(
        ["bse_code", "ex_date", "purpose", "event_type"], kind="mergesort"
    )
    bse_actions.to_csv(output / "official_bse_actions.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    pd.read_csv(args.bse_source_inventory, low_memory=False).to_csv(output / "official_bse_source_inventory.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})

    all_audit = facts[["isin", "ticker", "company", "primary_exchange", "product_sector", "product_classification_as_of"]].copy()
    cover_rows = []
    frozen = {}
    prior = {12: "current_lookback12.csv.gz", 36: "current_base.csv.gz", 60: "current_lookback60.csv.gz"}
    for months in (12, 36, 60):
        profile = InvestorProfile(lookback_months=months)
        simulation = recovered.book.simulate(profile, cutoff)
        classified = classify_profile_eligibility(
            simulation, facts, recovered.history_audit, profile, as_of_date=cutoff,
            official_history_evidence=evidence,
        )
        old = pd.read_csv(ROOT / "experiments/personalized/final-03" / prior[months], usecols=["isin", "status"]).rename(columns={"status": "starting_status"})
        classified = classified.merge(old, on="isin", validate="one_to_one")
        classified["freeze_status"] = "QUARANTINE_UNRESOLVED"
        classified.loc[classified.eligibility_class.eq("ELIGIBLE"), "freeze_status"] = "INCLUDE_GLOBAL"
        classified.loc[classified.eligibility_class.eq("LEGITIMATE_INELIGIBILITY"), "freeze_status"] = "EXCLUDE_LEGITIMATE"
        classified["sector_relative_status"] = "EXCLUDE_NO_PIT_SECTOR_INTERVAL"
        classified.to_csv(output / f"frozen_cohort_{months}m.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
        frozen[months] = classified
        all_audit = all_audit.merge(
            classified[["isin", "status", "classification_reason", "freeze_status"]].rename(columns={
                "status": f"status_{months}m", "classification_reason": f"reason_{months}m", "freeze_status": f"freeze_{months}m"
            }), on="isin", validate="one_to_one",
        )
        counts = classified.freeze_status.value_counts().to_dict()
        cover_rows.append({
            "lookback_months": months,
            "starting_available": int(old.starting_status.eq("AVAILABLE").sum()),
            "starting_unresolved": int(old.starting_status.ne("AVAILABLE").sum()),
            "ending_available": int(classified.status.eq("AVAILABLE").sum()),
            "global_frozen_included": int(counts.get("INCLUDE_GLOBAL", 0)),
            "legitimate_exclusions": int(counts.get("EXCLUDE_LEGITIMATE", 0)),
            "unresolved_quarantine": int(counts.get("QUARANTINE_UNRESOLVED", 0)),
            "eligible_population_coverage_pct": round(
                100 * int(counts.get("INCLUDE_GLOBAL", 0))
                / (len(classified) - int(counts.get("EXCLUDE_LEGITIMATE", 0))), 6
            ),
            "sector_relative_frozen_included": 0,
        })
    all_audit.to_csv(output / "all_security_freeze_audit.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    pd.DataFrame(cover_rows).to_csv(output / "coverage.csv", index=False, lineterminator="\n")

    quarantine = all_audit.loc[all_audit[[f"freeze_{m}m" for m in (12, 36, 60)]].eq("QUARANTINE_UNRESOLVED").any(axis=1)].copy()
    quarantine["quarantine_policy"] = "PERMANENT_UNTIL_NEW_OFFICIAL_EVIDENCE"
    quarantine.to_csv(output / "permanent_quarantine.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    master = pd.read_csv(ROOT / "experiments/personalized-data-recovery/run-05/dated_security_master.csv.gz", low_memory=False)
    master = master.merge(evidence.rename(columns={"isin": "canonical_isin"}), on="canonical_isin", how="left")
    master.to_csv(output / "frozen_dated_security_master.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})

    source_inputs = [args.bse_raw_audit, args.bse_decisions, *args.bse_actions, args.bse_source_inventory, args.bse_old_db, args.bse_new_db, live_path, actions_path]
    summary = {
        "schema_version": "personalized_data_freeze_v1", "as_of_date": cutoff,
        "universe_count": len(facts), "coverage": cover_rows,
        "bse_archive_coverage": coverage,
        "bse_official_recovery": evidence.official_recovery_status.value_counts().sort_index().to_dict(),
        "permanent_quarantine_count_any_profile": len(quarantine),
        "global_model_tournament_readiness": "PASS_WITH_FROZEN_PROFILE_COHORTS",
        "sector_relative_model_tournament_readiness": "BLOCKED_NO_HISTORICAL_SECTOR_INTERVALS",
        "historical_sector_intervals_recovered": 0,
        "overall": "PARTIAL",
        "exact_next_milestone": "Acquire and validate effective-dated historical sector intervals, then freeze sector-relative PIT cohorts.",
        "runtime_seconds": time.perf_counter() - started,
        "artifact_storage_bytes_before_manifest": sum(x.stat().st_size for x in output.iterdir() if x.is_file()),
        "protected_state_unchanged": before == {str(x.relative_to(ROOT)): digest(x) for x in protected},
        "input_hashes": {str(x): digest(x) for x in source_inputs},
        "boundaries": ["No missing price becomes zero", "No delisting receives an invented terminal value", "No current sector is back-projected", "Quarantined actions and identities never enter frozen cohorts"],
    }
    write_json(output / "summary.json", summary)
    deterministic = [{"path": x.name, "size": x.stat().st_size, "sha256": digest(x)} for x in sorted(output.iterdir()) if x.is_file() and x.name != "summary.json"]
    manifest = {"deterministic_artifacts": deterministic, "fingerprint": sha256(json.dumps(deterministic, sort_keys=True).encode()).hexdigest(), "observational_artifacts": ["summary.json"]}
    write_json(output / "manifest.json", manifest)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
