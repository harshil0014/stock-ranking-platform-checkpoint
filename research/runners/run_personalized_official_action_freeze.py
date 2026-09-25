"""Freeze profile-window official-action executable and exact sector cohorts."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_ranker.personalized import InvestorProfile
from stock_research.personalized_global_tournament import load_frozen_memberships
from stock_research.personalized_official_actions import (OfficialActionHistoryBook,
    load_official_action_ledger, apply_recovered_terms, validate_recovery_pack)


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def verify_pack(pack: Path) -> dict:
    handoff = pack / "handoff_for_codex"
    manifest_path = handoff / "handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures = []
    for relative, expected in manifest["outputs"].items():
        path = handoff / relative
        if not path.is_file() or path.stat().st_size != expected["size"] or digest(path) != expected["sha256"]:
            failures.append(str(path))
    for expected in manifest["source_inventory"]:
        path = pack / expected["path"]
        if not path.is_file() or path.stat().st_size != expected["size"] or digest(path) != expected["sha256"]:
            failures.append(str(path))
    if failures:
        raise ValueError(f"external evidence pack verification failed: {failures[:5]}")
    return {
        "manifest_sha256": digest(manifest_path),
        "verified_outputs": len(manifest["outputs"]),
        "verified_source_files": len(manifest["source_inventory"]),
        "verification_failures": 0,
    }


def sector_panel(book, official: pd.DataFrame, secondary: pd.DataFrame,
                 membership: set[str], profile: InvestorProfile) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    official = official.loc[
        official.classification_level.eq("INDUSTRY_AS_REPORTED_BY_NIFTY500")
        & official.observation_date.isin(["2020-03-31", "2021-03-31", "2022-03-31"])
    ].copy()
    official = official.rename(columns={"canonical_isin": "isin", "industry_or_sector": "observed_industry"})
    official = official.loc[official["isin"].isin(membership)].drop_duplicates(["observation_date", "isin"])
    panels, coverage, metrics = [], [], []
    for day, labels in official.groupby("observation_date", sort=True):
        score = book.simulate(profile, day, mode="enhanced_carry", include_journal=False)[
            ["isin", "status", "xirr"]
        ].rename(columns={"status": "score_status", "xirr": "enhanced_carry_xirr_score"})
        endpoint = (pd.Timestamp(day) + pd.DateOffset(months=12)).date().isoformat()
        outcome = book.simulate(profile, endpoint, months=12, mode="enhanced_carry", include_journal=False)[
            ["isin", "status", "xirr"]
        ].rename(columns={"status": "outcome_status", "xirr": "future_12m_xirr"})
        frame = labels.merge(score, on="isin", how="left", validate="one_to_one").merge(
            outcome, on="isin", how="left", validate="one_to_one"
        )
        frame["endpoint"] = endpoint
        frame["exact_date_evidence"] = True
        frame["eligible_for_sector_diagnostic"] = (
            frame.score_status.eq("AVAILABLE") & frame.outcome_status.eq("AVAILABLE")
            & frame.enhanced_carry_xirr_score.notna() & frame.future_12m_xirr.notna()
        )
        usable = frame.loc[frame.eligible_for_sector_diagnostic].copy()
        sizes = usable.groupby("observed_industry").size()
        usable = usable.loc[usable.observed_industry.map(sizes).ge(5)].copy()
        usable["sector_score"] = usable.groupby("observed_industry").enhanced_carry_xirr_score.rank(pct=True)
        usable["sector_outcome"] = usable.groupby("observed_industry").future_12m_xirr.rank(pct=True)
        frame = frame.merge(usable[["isin", "sector_score", "sector_outcome"]], on="isin", how="left")
        panels.append(frame)
        coverage.append({
            "evidence_tier": "official", "observation_date": day,
            "observed_full_classifications": len(labels),
            "score_available": int(frame.score_status.eq("AVAILABLE").sum()),
            "outcome_available": int(frame.outcome_status.eq("AVAILABLE").sum()),
            "sector_diagnostic_rows": len(usable),
            "supported_industries_min_5": int(usable.observed_industry.nunique()),
            "global_frozen_36m_population": len(membership),
            "population_coverage_pct": 100 * len(usable) / len(membership),
        })
        if len(usable) >= 2:
            metrics.append({
                "observation_date": day, "rows": len(usable),
                "industries": int(usable.observed_industry.nunique()),
                "global_score_rank_ic": usable.enhanced_carry_xirr_score.corr(usable.future_12m_xirr, method="spearman"),
                "sector_relative_rank_ic": usable.sector_score.corr(usable.sector_outcome, method="spearman"),
                "global_top20_mean_future_xirr": usable.nlargest(20, "enhanced_carry_xirr_score").future_12m_xirr.mean(),
                "sector_relative_top20_mean_future_xirr": usable.nlargest(20, "sector_score").future_12m_xirr.mean(),
            })
    secondary_rows = []
    for day, labels in secondary.groupby("observation_date", sort=True):
        observed = set(labels.canonical_isin.astype(str))
        secondary_rows.append({
            "evidence_tier": "secondary", "observation_date": day,
            "observed_classifications": len(observed),
            "matched_global_frozen_36m": len(observed & membership),
            "used_for_official_sector_experiment": False,
        })
    return pd.concat(panels, ignore_index=True), pd.DataFrame(coverage + secondary_rows), pd.DataFrame(metrics)


def run(args) -> None:
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("fresh official-action freeze output required")
    output.mkdir(parents=True)
    started = time.perf_counter()
    pack_audit = verify_pack(args.evidence_pack.resolve())
    residual_audit = validate_recovery_pack(args.residual_pack, args.residual_pack.parent / "event_terms_round2")
    handoff = args.evidence_pack / "handoff_for_codex"
    action_source = args.evidence_pack / "corporate_actions/reconciled/official_share_structure_events_2010_2026.csv.gz"
    protected = [ROOT / "data/company_facts/accepted_state.json", ROOT / "data/live_market/accepted_state.json"]
    protected_before = {str(path.relative_to(ROOT)): digest(path) for path in protected}
    snapshot = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts"))
    facts = snapshot.facts
    frozen_fingerprint = json.loads((args.frozen_root / "manifest.json").read_text(encoding="utf-8"))["fingerprint"]
    memberships = load_frozen_memberships(args.frozen_root, frozen_fingerprint)
    identity_set = set.union(*memberships.values())
    identities = facts.loc[facts["isin"].isin(identity_set), ["isin", "ticker", "primary_exchange"]].copy()
    ledger, mapping_audit = load_official_action_ledger(facts, action_source, as_of_date=args.as_of_date)
    ledger, recovered_audit = apply_recovered_terms(ledger, args.residual_pack, as_of_date=args.as_of_date)
    supplied_profiles = pd.read_csv(handoff / "corporate_action_profile_status.csv")
    target_ids = set(supplied_profiles["isin"])
    target_rows = []
    end_ts = pd.Timestamp(args.as_of_date)
    for months in (12, 36, 60):
        supplied = supplied_profiles.loc[supplied_profiles.lookback_months.eq(months)]
        window = ledger.loc[
            ledger["isin"].isin(target_ids)
            & pd.to_datetime(ledger.event_date).between(end_ts - pd.DateOffset(months=months), end_ts)
        ]
        target_rows.append({
            "lookback_months": months,
            "reconciled_target_identities": len(target_ids),
            "supplied_pack_blocking_identities": int(supplied.window_evidence_status.eq(
                "OFFICIAL_BLOCKING_COMPLEX_EVENT_IN_WINDOW").sum()),
            "continuity_mapped_blocking_identities": int(window.loc[
                window.mechanics_status.eq("BLOCKING"), "isin"].nunique()),
            "continuity_mapped_auto_identities": int(window.loc[
                window.mechanics_status.eq("AUTO_MULTIPLIER"), "isin"].nunique()),
            "continuity_mapping_additional_blockers": int(window.loc[
                window.mechanics_status.eq("BLOCKING"), "isin"].nunique()) - int(
                    supplied.window_evidence_status.eq("OFFICIAL_BLOCKING_COMPLEX_EVENT_IN_WINDOW").sum()),
        })
    target_reconciliation = pd.DataFrame(target_rows)
    target_reconciliation.to_csv(output / "handoff_target_reconciliation.csv", index=False, lineterminator="\n")
    repairs = pd.read_csv(args.frozen_root / "terminal_repairs.csv")
    live_state = json.loads((ROOT / "data/live_market/accepted_state.json").read_text(encoding="utf-8"))
    live_path = ROOT / "data/live_market" / live_state["bundle_path"] / "live_market.csv"
    live = pd.read_csv(live_path, low_memory=False)
    history_audit = pd.read_csv(ROOT / "research/data/ownership-recovery-20260925/history_recovery_audit.csv")
    nominal_tickers = set(history_audit.loc[history_audit.raw_basis.eq("OFFICIAL_NOMINAL"), "ticker"])
    adjustment_dates = history_audit.dropna(subset=["provider_adjustment_through"]).set_index("ticker").provider_adjustment_through.to_dict()
    history_audit.to_csv(output / "history_recovery_audit.csv", index=False)
    resulting_terms = pd.read_csv(ROOT / "research/data/ownership-recovery-20260925/resulting_equity_terms.csv")
    child_ids = set(resulting_terms.child_isin)
    identities = pd.concat([identities, facts.loc[facts["isin"].isin(child_ids), identities.columns]]).drop_duplicates("isin")
    for term in resulting_terms.itertuples(index=False):
        mask = ledger["isin"].eq(term.parent_isin) & ledger.event_date.eq(term.event_date) & ledger.event_type.eq("DEMERGER")
        ledger.loc[mask, "mechanics_status"] = "RESULTING_EQUITY"
        ledger.loc[mask, "block_reason"] = None
        ledger.loc[mask, "economic_policy"] = "RESULTING_EQUITY_HOLD_PRICE_ONLY"
    resulting_terms.to_csv(output / "resulting_equity_terms.csv", index=False)
    book = OfficialActionHistoryBook(
        identities, args.history_cache, args.split_root, ledger, as_of_date=args.as_of_date,
        terminal_repairs=repairs, terminal_raw_prices=live[["isin", "trade_date", "latest_price"]], resulting_terms=resulting_terms,
        history_overlay=ROOT / "external_research_pack/ownership_history_20260925",
        nominal_tickers=nominal_tickers, adjustment_dates=adjustment_dates,
    )
    prior = pd.concat([pd.read_csv(args.previous_freeze / f"frozen_executable_cohort_{months}m.csv.gz", low_memory=False)
                       for months in (12, 36, 60)], ignore_index=True)
    profile_names = {12: "lookback12", 36: "base7500", 60: "lookback60"}
    coverage_rows, cohorts = [], []
    for months, profile_name in profile_names.items():
        profile = InvestorProfile(amount=7500, interval_days=30, lookback_months=months,
                                  horizon_months=12, target_cagr=.2, whole_shares=True)
        result = book.simulate(profile, args.as_of_date, mode="enhanced_carry", include_journal=False)
        result = result.loc[result["isin"].isin(memberships[months])].copy()
        old = prior.loc[prior.lookback_months.eq(months), ["isin", "status"]].rename(columns={"status": "status_before"})
        result = result.merge(old, on="isin", how="left", validate="one_to_one")
        result["false_quarantine_removed"] = result.status_before.ne("AVAILABLE") & result.status.eq("AVAILABLE")
        result["true_blocking_event"] = result.status.isin([
            "UNRESOLVED_CORPORATE_ACTION", "UNRESOLVED_FRACTIONAL_ENTITLEMENT"
        ])
        result["freeze_status"] = np.where(result.status.eq("AVAILABLE"), "INCLUDE_EXECUTABLE", "QUARANTINE_PROFILE_WINDOW")
        result["recovery_class"] = "PERMANENTLY_UNRESOLVED_OR_QUARANTINED"
        result.loc[result.status.eq("AVAILABLE") & result.status_before.eq("AVAILABLE"), "recovery_class"] = "RETAINED"
        result.loc[result.false_quarantine_removed, "recovery_class"] = "RECOVERED_FALSE_QUARANTINE"
        result.loc[result.true_blocking_event, "recovery_class"] = "LEGITIMATE_PROFILE_WINDOW_BLOCK"
        result["lookback_months"] = months
        result = result.sort_values("isin").reset_index(drop=True)
        result.to_csv(output / f"frozen_executable_cohort_{months}m.csv.gz", index=False,
                      compression={"method": "gzip", "mtime": 0})
        cohorts.append(result)
        before_available = int(result.status_before.eq("AVAILABLE").sum())
        after_available = int(result.status.eq("AVAILABLE").sum())
        coverage_rows.append({
            "lookback_months": months, "frozen_global_population": len(result),
            "executable_available_before": before_available,
            "executable_coverage_before_pct": 100 * before_available / len(result),
            "executable_available_after": after_available,
            "executable_coverage_after_pct": 100 * after_available / len(result),
            "net_available_change": after_available - before_available,
            "false_quarantines_removed": int(result.false_quarantine_removed.sum()),
            "true_blocking_events_remaining": int(result.true_blocking_event.sum()),
            "corporate_action_blocks": int(result.status.eq("UNRESOLVED_CORPORATE_ACTION").sum()),
            "fractional_entitlement_blocks": int(result.status.eq("UNRESOLVED_FRACTIONAL_ENTITLEMENT").sum()),
            "other_unresolved": int((~result.status.eq("AVAILABLE") & ~result.true_blocking_event).sum()),
        })
    coverage = pd.DataFrame(coverage_rows)
    coverage.to_csv(output / "executable_coverage.csv", index=False, lineterminator="\n")
    pd.concat(cohorts, ignore_index=True).to_csv(
        output / "all_profile_recovery_audit.csv.gz", index=False, compression={"method": "gzip", "mtime": 0}
    )
    ledger.to_csv(output / "normalized_official_action_ledger.csv.gz", index=False,
                  compression={"method": "gzip", "mtime": 0})
    official = pd.read_csv(handoff / "historical_sector_observations_official.csv.gz", low_memory=False)
    secondary = pd.read_csv(handoff / "historical_sector_observations_secondary.csv.gz", low_memory=False)
    panel, sector_coverage, sector_metrics = sector_panel(
        book, official, secondary, memberships[36],
        InvestorProfile(amount=7500, interval_days=30, lookback_months=36,
                        horizon_months=12, target_cagr=.2, whole_shares=True),
    )
    panel.to_csv(output / "official_exact_date_sector_panel.csv.gz", index=False,
                 compression={"method": "gzip", "mtime": 0})
    sector_coverage.to_csv(output / "sector_pit_coverage.csv", index=False, lineterminator="\n")
    sector_metrics.to_csv(output / "sector_relative_supplementary_metrics.csv", index=False, lineterminator="\n")
    current_exact = official.loc[
        official.observation_date.eq(args.as_of_date)
        & official.classification_level.eq("INDUSTRY_AS_REPORTED_BY_NIFTY500")
    ]
    protected_after = {str(path.relative_to(ROOT)): digest(path) for path in protected}
    if protected_before != protected_after:
        raise ValueError("protected state changed")
    summary = {
        "schema_version": "personalized_official_action_freeze_v1",
        "as_of_date": args.as_of_date,
        "pack_verification": pack_audit,
        "residual_reconciliation": residual_audit,
        "recovered_action_application": recovered_audit,
        "official_action_mapping": mapping_audit,
        "handoff_target_reconciliation": target_rows,
        "executable_coverage": coverage_rows,
        "false_quarantines_removed_total_profile_rows": int(coverage.false_quarantines_removed.sum()),
        "true_blocking_events_remaining_total_profile_rows": int(coverage.true_blocking_events_remaining.sum()),
        "sector_exact_official_dates": sorted(panel.observation_date.unique().tolist()),
        "sector_current_exact_observation_rows": len(current_exact),
        "sector_current_pit_coverage_pct": 0.0 if current_exact.empty else 100 * current_exact.canonical_isin.nunique() / len(memberships[36]),
        "sector_evidence_boundary": "Exact observed dates only; secondary evidence remains separate; no back-projection.",
        "global_tournament_readiness": "READY_RESEARCH_ONLY",
        "sector_relative_tournament_readiness": "READY_EXACT_DATE_SUPPLEMENTARY_ONLY",
        "protected_state_unchanged": True,
        "runtime_seconds": time.perf_counter() - started,
        "exact_next_milestone": "Run the preregistered official-action global rerun and exact-date sector diagnostic, then await prospective post-2026-09-18 outcomes.",
    }
    write_json(output / "summary.json", summary)
    write_json(output / "inputs.json", {
        "handoff_manifest_sha256": pack_audit["manifest_sha256"],
        "official_source_ledger_sha256": digest(action_source),
        "provider_split_ledger_sha256": digest(args.split_root / "split_ledger.csv"),
        "old_frozen_manifest_sha256": digest(args.frozen_root / "manifest.json"),
        "old_tournament_manifest_sha256": digest(args.previous_tournament / "manifest.json"),
        "previous_freeze_manifest_sha256": digest(args.previous_freeze / "manifest.json"),
        "residual_manifest_sha256": digest(args.residual_pack / "manifest.json"),
        "live_market_sha256": digest(live_path),
        "company_fact_fingerprint": snapshot.manifest["fingerprint"],
        "protected_state": protected_before,
        "source_sha256": {
            "runner": digest(Path(__file__)),
            "module": digest(ROOT / "src/stock_research/personalized_official_actions.py"),
        },
    })
    artifacts = [{"path": path.name, "size": path.stat().st_size, "sha256": digest(path)}
                 for path in sorted(output.iterdir()) if path.is_file() and path.name != "summary.json"]
    write_json(output / "manifest.json", {
        "deterministic_artifacts": artifacts,
        "fingerprint": sha256(json.dumps(artifacts, sort_keys=True).encode()).hexdigest(),
        "observational_artifacts": ["summary.json"],
    })
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-pack", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--previous-tournament", type=Path, required=True)
    parser.add_argument("--previous-freeze", type=Path, required=True)
    parser.add_argument("--residual-pack", type=Path, required=True)
    parser.add_argument("--history-cache", type=Path, required=True)
    parser.add_argument("--split-root", type=Path, required=True)
    parser.add_argument("--as-of-date", default="2026-09-18")
    run(parser.parse_args())
