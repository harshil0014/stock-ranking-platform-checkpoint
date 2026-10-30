"""Post-reveal data-repair sensitivity; original V13 reveal remains immutable."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
import numpy as np
import pandas as pd

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_research.personalized_executable_tournament import load_protocol
from stock_research.personalized_global_tournament import load_frozen_memberships
from stock_research.personalized_official_actions import OfficialActionHistoryBook
from research.runners import personalized_deeper_championship_v2 as d
from research.runners.evaluate_v13_prospective_20250930 import top_diagnostic

BASE = ROOT / "experiments/personalized-v13-20261002/prospective-2025-09-30"
REPAIR = BASE / "post_reveal_price_repair_20260901_18"
COHORT = ROOT / "experiments/personalized-data-freeze/build-01"
PROTOCOL = ROOT / "research/protocols/personalized_official_action_tournament_v1.json"
END = "2026-09-30"


def sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def build_book():
    protocol, profiles = load_protocol(PROTOCOL)
    memberships = load_frozen_memberships(COHORT, protocol["frozen_cohort_fingerprint"])
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    identities = facts.loc[facts["isin"].isin(set.union(*memberships.values())), ["isin", "ticker"]]
    terms = pd.read_csv(ROOT / "research/data/ownership-recovery-20260925/resulting_equity_terms.csv")
    children = facts.loc[facts["isin"].isin(set(terms.child_isin)), ["isin", "ticker"]]
    identities = pd.concat([identities, children]).drop_duplicates("isin")
    failed_provider = pd.read_csv(ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2/acquisition_audit.csv")
    quarantine = set(failed_provider.loc[failed_provider.status.eq("FAILED"), "isin"])
    action = json.loads((BASE / "execution_evidence_summary.json").read_text())["action"]
    quarantine |= set(identities.loc[identities.ticker.isin({f"BSE-{x}" for x in action["bse_failed_codes"]}), "isin"])
    identities = identities.loc[~identities["isin"].isin(quarantine)]
    ledger = pd.read_csv(BASE / "official_actions/normalized_official_action_ledger_through_20260930.csv.gz")
    for term in terms.itertuples(index=False):
        match = ledger["isin"].eq(term.parent_isin) & ledger.event_date.eq(term.event_date) & ledger.event_type.eq("DEMERGER")
        ledger.loc[match, "mechanics_status"] = "RESULTING_EQUITY"
        ledger.loc[match, "block_reason"] = None
        ledger.loc[match, "economic_policy"] = "RESULTING_EQUITY_HOLD_PRICE_ONLY"
    repairs = pd.read_csv(COHORT / "terminal_repairs.csv")
    live_state = json.loads((ROOT / "data/live_market/accepted_state.json").read_text())
    live = pd.read_csv(ROOT / "data/live_market" / live_state["bundle_path"] / "live_market.csv")
    audit = pd.read_csv(ROOT / "research/data/ownership-recovery-20260925/history_recovery_audit.csv")
    nominal = set(audit.loc[audit.raw_basis.eq("OFFICIAL_NOMINAL"), "ticker"])
    adjustment_dates = audit.dropna(subset=["provider_adjustment_through"]).set_index("ticker").provider_adjustment_through.to_dict()
    new_splits = pd.read_csv(BASE / "provider_split_ledger/split_ledger.csv")
    for ticker in new_splits.loc[new_splits.event_date.gt("2026-09-18"), "ticker"]:
        adjustment_dates[ticker] = END
    book = OfficialActionHistoryBook(
        identities, BASE / "official_execution_overlay", BASE / "provider_split_ledger",
        ledger, as_of_date=END, terminal_repairs=repairs,
        terminal_raw_prices=live[["isin", "trade_date", "latest_price"]],
        resulting_terms=terms, nominal_tickers=nominal,
        adjustment_dates=adjustment_dates,
        history_overlay=REPAIR / "history_overlay",
    )
    return book, profiles, quarantine


def main() -> None:
    result_path = REPAIR / "repaired_evaluation_record.json"
    if result_path.exists() or (REPAIR / "repaired_outcomes.csv.gz").exists():
        raise FileExistsError("repair sensitivity already evaluated")
    repair = json.loads((REPAIR / "summary.json").read_text())
    structural = json.loads((REPAIR / "structural_audit.json").read_text())
    if (not structural["post_reveal_sensitivity_only"]
            or structural["weekly_date_gap_identities_after"] >= structural["weekly_date_gap_identities_before"]):
        raise ValueError("post-reveal structural repair not verified")
    if repair["first_reveal_sha256"] != sha(BASE / "evaluation_record.json"):
        raise ValueError("first reveal drift")
    pre = json.loads((BASE / "pre_reveal_record.json").read_text())
    if repair["locked_scores_sha256"] != pre["scores_before_reveal_sha256"]:
        raise ValueError("locked scores drift")
    official_sources = pd.read_csv(REPAIR / "official_price_sources.csv")
    for row in official_sources.itertuples(index=False):
        assert sha(REPAIR / "official_prices" / Path(row.source_url).name) == row.source_sha256
    scores = pd.read_csv(BASE / "scores_before_reveal.csv.gz")
    features = pd.read_csv(BASE / "decision_features_without_outcomes.csv.gz", low_memory=False)
    keys = ["isin", "decision_date", "profile_name"]
    frame = features.drop(columns=["future_xirr", "future_shortfall", "future_drawdown"]).merge(
        scores[keys + ["champion_score", "v13_score"]], on=keys, validate="one_to_one")
    book, profiles, quarantine = build_book()
    outcomes = []
    for name, profile in profiles.items():
        future = book.simulate(profile, pd.Timestamp(END), months=profile.horizon_months,
                               mode="enhanced_carry", include_journal=False)
        future = future[["isin", "status", "xirr", "target_shortfall", "price_drawdown"]]
        future = future.rename(columns={"status": "outcome_status", "xirr": "future_xirr",
                                "target_shortfall": "future_shortfall", "price_drawdown": "future_drawdown"})
        future["profile_name"] = name
        outcomes.append(future)
    actual = pd.concat(outcomes, ignore_index=True)
    actual = actual.loc[~actual["isin"].isin(quarantine)]
    actual.to_csv(REPAIR / "repaired_outcomes.csv.gz", index=False,
                  compression={"method": "gzip", "mtime": 0})
    joined = frame.merge(actual, on=["isin", "profile_name"], how="left", validate="one_to_one")
    for col in ("future_xirr", "future_shortfall", "future_drawdown"):
        joined.loc[joined.outcome_status.ne("AVAILABLE"), col] = np.nan
    champ = d.hist.evaluate(joined, "champion_score")
    v13 = d.hist.evaluate(joined, "v13_score")
    pair = champ.merge(v13, on=["decision_date", "profile"], suffixes=("_champion", "_v13"))
    pair.to_csv(REPAIR / "repaired_profile_metrics.csv", index=False)
    aggregate = {metric: {"champion": float(champ[metric].mean()),
                          "v13": float(v13[metric].mean()),
                          "delta": float(v13[metric].mean() - champ[metric].mean())}
                 for metric in d.METRICS}
    profile_deltas = {}
    for row in pair.itertuples(index=False):
        profile_deltas[row.profile] = {
            metric: float(getattr(row, metric + "_v13") - getattr(row, metric + "_champion"))
            for metric in d.METRICS}
    original = json.loads((BASE / "evaluation_record.json").read_text())
    record = {"schema": "v13_post_reveal_price_repair_sensitivity_v1",
              "status": "POST_REVEAL_STRUCTURAL_DATA_REPAIR_NOT_FRESH_BLIND_VALIDATION",
              "selection_changed": False, "scores_changed": False,
              "first_reveal_sha256": sha(BASE / "evaluation_record.json"),
              "repair_summary_sha256": sha(REPAIR / "summary.json"),
              "repair_structural_audit_sha256": sha(REPAIR / "structural_audit.json"),
              "scores_before_reveal_sha256": sha(BASE / "scores_before_reveal.csv.gz"),
              "repaired_outcomes_sha256": sha(REPAIR / "repaired_outcomes.csv.gz"),
              "rows": len(joined), "outcome_available_rows": int(joined.future_xirr.notna().sum()),
              "aggregate": aggregate, "profile_deltas": profile_deltas,
              "top20_history_champion": top_diagnostic(joined, "champion_score"),
              "top20_history_v13": top_diagnostic(joined, "v13_score"),
              "first_reveal_aggregate": original["aggregate"],
              "production_mutated": False}
    result_path.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"aggregate": aggregate, "weekly": profile_deltas["weekly"],
                      "lookback60": profile_deltas["lookback60"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
