"""Build a fresh, non-promoted personalized data-recovery audit."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_ranker.personalized import InvestorProfile
from stock_ranker.personalized_recovery import (
    classify_profile_eligibility, effective_dated_security_master, recover_history_book,
)


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def load_official_nse_bridge(root: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(root.glob("*.zip")):
        with ZipFile(path) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(members) != 1 or ".." in Path(members[0]).parts:
                raise ValueError(f"unsafe NSE archive: {path}")
            frame = pd.read_csv(archive.open(members[0]), usecols=["TradDt", "ISIN", "TckrSymb", "SctySrs", "ClsPric"])
        frame = frame.loc[frame["SctySrs"].isin(["EQ", "BE", "BZ", "SM", "ST", "MT"])].rename(
            columns={"TradDt": "trade_date", "ISIN": "isin", "TckrSymb": "ticker", "ClsPric": "close"}
        )
        frame["source_file"] = path.name
        frame["source_sha256"] = digest(path)
        rows.append(frame[["trade_date", "isin", "ticker", "close", "source_file", "source_sha256"]])
    result = pd.concat(rows, ignore_index=True)
    if result.duplicated(["trade_date", "isin"]).any():
        raise ValueError("duplicate official bridge identity/date")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--nse-bridge", type=Path, required=True)
    parser.add_argument("--mii-master", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output
    if output.exists():
        raise ValueError("fresh output directory required")
    output.mkdir(parents=True)
    started = time.perf_counter()

    protected = [ROOT / "data/company_facts/accepted_state.json", ROOT / "data/live_market/accepted_state.json"]
    checkpoint = {str(p.relative_to(ROOT)): digest(p) for p in protected}
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    market_state = json.loads((ROOT / "data/live_market/accepted_state.json").read_text(encoding="utf-8"))
    market_dir = ROOT / "data/live_market" / market_state["bundle_path"]
    live = pd.read_csv(market_dir / "live_market.csv", low_memory=False)
    action_path = ROOT / "data/company_facts/providers/official_exchange/automatic-20260920T023321Z/corporate_actions.csv"
    actions = pd.read_csv(action_path, low_memory=False)
    as_of = market_state["trade_date"]

    bridge = load_official_nse_bridge(args.nse_bridge)
    recovered = recover_history_book(facts, ROOT / "data/live_market/history_cache", live, actions,
                                     as_of_date=as_of, official_price_bridge=bridge)
    recovered.repairs.to_csv(output / "terminal_repairs.csv", index=False, lineterminator="\n")
    recovered.history_audit.to_csv(output / "history_quality_audit.csv.gz", index=False,
                                   compression={"method": "gzip", "mtime": 0})

    profiles = {str(months): InvestorProfile(lookback_months=months) for months in (12, 36, 60)}
    original_files = {12: "current_lookback12.csv.gz", 36: "current_base.csv.gz", 60: "current_lookback60.csv.gz"}
    wide = facts[["isin", "ticker", "company", "primary_exchange", "listing_date"]].copy()
    coverage = []
    for label, profile in profiles.items():
        months = int(label)
        simulation = recovered.book.simulate(profile, as_of)
        classified = classify_profile_eligibility(simulation, facts, recovered.history_audit, profile, as_of_date=as_of)
        original = pd.read_csv(ROOT / "experiments/personalized/final-03" / original_files[months],
                               usecols=["isin", "status"], low_memory=False).rename(columns={"status": "original_status"})
        classified = classified.merge(original, on="isin", validate="one_to_one")
        classified["repair_outcome"] = "UNRESOLVED"
        classified.loc[classified["eligibility_class"].eq("LEGITIMATE_INELIGIBILITY"), "repair_outcome"] = "LEGITIMATE_INELIGIBILITY"
        classified.loc[classified["status"].eq("AVAILABLE") & classified["original_status"].ne("AVAILABLE"), "repair_outcome"] = "FIXED"
        classified.loc[classified["status"].eq("AVAILABLE") & classified["original_status"].eq("AVAILABLE"), "repair_outcome"] = "PRESERVED_ELIGIBLE"
        classified.to_csv(output / f"eligibility_{months}m.csv.gz", index=False,
                          compression={"method": "gzip", "mtime": 0})
        part = classified[["isin", "status", "eligibility_class", "classification_reason", "repair_outcome"]].rename(
            columns={c: f"{c}_{months}m" for c in ("status", "eligibility_class", "classification_reason", "repair_outcome")}
        )
        wide = wide.merge(part, on="isin", validate="one_to_one")
        old_counts = original["original_status"].value_counts().to_dict()
        new_counts = classified["status"].value_counts().to_dict()
        outcome_counts = classified["repair_outcome"].value_counts().to_dict()
        coverage.append({"lookback_months": months, "starting_available": int(old_counts.get("AVAILABLE", 0)),
                         "ending_available": int(new_counts.get("AVAILABLE", 0)),
                         "fixed": int(outcome_counts.get("FIXED", 0)),
                         "legitimate_ineligibility": int(outcome_counts.get("LEGITIMATE_INELIGIBILITY", 0)),
                         "unresolved": int(outcome_counts.get("UNRESOLVED", 0)),
                         "status_counts": new_counts})
    wide.to_csv(output / "all_security_audit.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    pd.DataFrame([{k: v for k, v in row.items() if k != "status_counts"} for row in coverage]).to_csv(
        output / "coverage.csv", index=False, lineterminator="\n")

    continuity = pd.read_csv(args.identity / "identity_continuity.csv", low_memory=False)
    dispositions = pd.read_csv(ROOT / "data/analysis/universe_reconciliation_20260920_run_01/historical_universe_dispositions.csv",
                               low_memory=False)
    master = effective_dated_security_master(facts, continuity, dispositions, as_of_date=as_of)
    mii = pd.read_csv(args.mii_master, low_memory=False)
    mii = mii.loc[mii["ISIN"].astype(str).str.startswith("INE") & mii["SctySrs"].isin(["EQ", "BE", "BZ", "SM", "ST", "MT"])].copy()
    mii["official_master_listing_date"] = pd.to_datetime(pd.to_numeric(mii["ListgDt"], errors="coerce"), unit="s", errors="coerce").dt.date.astype("string")
    mii["official_master_removal_date"] = pd.to_datetime(pd.to_numeric(mii["RmvlDt"], errors="coerce").replace(0, pd.NA), unit="s", errors="coerce").dt.date.astype("string")
    series_order = {name: i for i, name in enumerate(["EQ", "BE", "BZ", "SM", "ST", "MT"])}
    mii["series_order"] = mii["SctySrs"].map(series_order)
    mii = mii.sort_values(["ISIN", "series_order", "ListgDt"], kind="mergesort").drop_duplicates("ISIN")
    recon = facts[["isin", "ticker", "primary_exchange", "listing_date"]].merge(
        mii[["ISIN", "TckrSymb", "SctySrs", "official_master_listing_date", "official_master_removal_date", "DelFlg"]],
        left_on="isin", right_on="ISIN", how="left", validate="one_to_one",
    )
    recon["official_master_match_status"] = recon["ISIN"].notna().map({True: "EXACT_ISIN", False: "NOT_IN_NSE_MII_MASTER"})
    recon.to_csv(output / "official_master_reconciliation.csv.gz", index=False,
                 compression={"method": "gzip", "mtime": 0})
    lookup = recon.set_index("isin")[["official_master_listing_date", "official_master_removal_date", "official_master_match_status"]]
    for column in lookup.columns:
        master[column] = master["canonical_isin"].map(lookup[column])
    master.to_csv(output / "dated_security_master.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})

    original_base = pd.read_csv(ROOT / "experiments/personalized/final-03/current_base.csv.gz", low_memory=False)
    original_breakdown = original_base.groupby(["status", "reason"], dropna=False).size().reset_index(name="count")
    original_breakdown.to_csv(output / "original_36m_reason_breakdown.csv", index=False, lineterminator="\n")
    current_master = master[master["lifecycle_status"].eq("LISTED_AS_OF_CUTOFF")]
    sector_stats = {
        "current_securities": len(current_master),
        "current_sector_present": int(current_master["sector"].notna().sum()),
        "historical_sector_intervals_recovered": 0,
        "limitation": "Current classifications retain their observed valid-from date and are never projected backward.",
    }
    elapsed = time.perf_counter() - started
    try:
        import psutil
        resident = psutil.Process().memory_info().rss
    except ImportError:
        resident = None
    artifact_storage = sum(p.stat().st_size for p in output.iterdir() if p.is_file())
    summary = {
        "schema_version": "personalized_data_recovery_v1", "as_of_date": as_of,
        "universe_count": len(facts), "coverage": coverage,
        "terminal_repairs": len(recovered.repairs),
        "invalid_observations_removed": int(recovered.history_audit["invalid_observations_removed"].sum()),
        "histories_sanitized": int(recovered.history_audit["invalid_observations_removed"].gt(0).sum()),
        "official_identity_evidence_rows": len(continuity), "security_master_rows": len(master),
        "official_bridge_price_rows": len(bridge),
        "cutoff_mii_exact_isin_matches": int(recon["ISIN"].notna().sum()),
        "historical_dispositions_preserved": int(master["lifecycle_status"].eq("NO_LONGER_IN_CURRENT_UNIVERSE_UNRESOLVED").sum()),
        "automatic_delisting_terminal_values": 0, "automatic_merger_splices": 0,
        "sector_history": sector_stats, "runtime_seconds": elapsed, "resident_memory_bytes_at_completion": resident,
        "artifact_storage_bytes_before_manifest": artifact_storage,
        "protected_state_unchanged": checkpoint == {str(p.relative_to(ROOT)): digest(p) for p in protected},
        "inputs": {"corporate_actions_sha256": digest(action_path),
                   "identity_continuity_sha256": digest(args.identity / "identity_continuity.csv"),
                   "live_market_sha256": digest(market_dir / "live_market.csv"), "protected_state": checkpoint},
        "boundaries": ["No missing price is valued at zero", "No delisting receives an invented terminal value",
                       "No current sector is back-projected", "No unresolved ISIN transition splices price series"],
    }
    write_json(output / "summary.json", summary)
    artifacts = [{"path": p.relative_to(output).as_posix(), "size": p.stat().st_size, "sha256": digest(p)}
                 for p in sorted(output.iterdir()) if p.is_file() and p.name != "summary.json"]
    observational = [{"path": "summary.json", "size": (output / "summary.json").stat().st_size,
                      "sha256": digest(output / "summary.json")}]
    manifest = {"deterministic_artifacts": artifacts, "observational_artifacts": observational,
                "fingerprint_scope": "Deterministic data artifacts; runtime and resident-memory summary excluded."}
    manifest["fingerprint"] = sha256(json.dumps(artifacts, sort_keys=True).encode()).hexdigest()
    write_json(output / "manifest.json", manifest)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
