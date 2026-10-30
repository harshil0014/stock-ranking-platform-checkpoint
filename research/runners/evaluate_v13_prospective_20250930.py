"""One-time reveal of the locked V13 prospective 2025-09-30 outcome."""
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

OUT = ROOT / "experiments/personalized-v13-20261002/prospective-2025-09-30"
V13 = ROOT / "experiments/personalized-v13-20261002"
OLD_SPLIT = ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2"
COHORT = ROOT / "experiments/personalized-data-freeze/build-01"
PROTOCOL = ROOT / "research/protocols/personalized_official_action_tournament_v1.json"
LOCK_SHA = "dad3ce68b22a1f744650e501505a3ebc78dc7c4bd39c3247982c4ed84bcac13b"
DAY, END = "2025-09-30", "2026-09-30"


def sha(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def guard() -> dict:
    if sha(V13 / "locked_selection.json") != LOCK_SHA:
        raise ValueError("V13 lock drift")
    pre = json.loads((OUT / "pre_reveal_record.json").read_text())
    if pre["scores_before_reveal_sha256"] != sha(OUT / "scores_before_reveal.csv.gz"):
        raise ValueError("pre-reveal score hash drift")
    if pre["decision_features_without_outcomes_sha256"] != sha(OUT / "decision_features_without_outcomes.csv.gz"):
        raise ValueError("pre-reveal feature hash drift")
    if pre["outcome_columns_loaded"] or pre["outcome_simulation_run"]:
        raise ValueError("pre-reveal assertion drift")
    evidence = json.loads((OUT / "execution_evidence_summary.json").read_text())
    if evidence["pre_reveal_record_sha256"] != sha(OUT / "pre_reveal_record.json"):
        raise ValueError("execution evidence was not bound to pre-reveal record")
    if evidence["official_price_rows"] < 20000 or evidence["action"]["new_rows"] < 2:
        raise ValueError("endpoint evidence incomplete")
    audit = json.loads((OUT / "pre_reveal_integrity_audit.json").read_text())
    if (audit["outcome_values_loaded"] or audit["outcome_file_exists"]
            or audit["scores_before_reveal_sha256"] != pre["scores_before_reveal_sha256"]):
        raise ValueError("pre-reveal integrity audit failed")
    source = pd.read_csv(OUT / "official_price_sources.csv")
    if len(source) != 16:
        raise ValueError("missing daily official price source")
    for row in source.itertuples(index=False):
        path = OUT / "official_prices" / Path(row.source_url).name
        if sha(path) != row.source_sha256:
            raise ValueError("official price source hash drift")
    return {"pre": pre, "evidence": evidence, "audit": audit}


def book_and_profiles(evidence: dict):
    protocol, profiles = load_protocol(PROTOCOL)
    memberships = load_frozen_memberships(COHORT, protocol["frozen_cohort_fingerprint"])
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    identities = facts.loc[facts["isin"].isin(set.union(*memberships.values())), ["isin", "ticker"]]
    terms = pd.read_csv(ROOT / "research/data/ownership-recovery-20260925/resulting_equity_terms.csv")
    children = facts.loc[facts["isin"].isin(set(terms.child_isin)), ["isin", "ticker"]]
    identities = pd.concat([identities, children]).drop_duplicates("isin")
    failed_provider = pd.read_csv(OLD_SPLIT / "acquisition_audit.csv")
    quarantine = set(failed_provider.loc[failed_provider.status.eq("FAILED"), "isin"])
    bad_codes = set(evidence["action"]["bse_failed_codes"])
    bad_tickers = {f"BSE-{code}" for code in bad_codes}
    quarantine |= set(identities.loc[identities.ticker.isin(bad_tickers), "isin"])
    identities = identities.loc[~identities["isin"].isin(quarantine)]
    ledger = pd.read_csv(OUT / "official_actions/normalized_official_action_ledger_through_20260930.csv.gz")
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
    new_splits = pd.read_csv(OUT / "provider_split_ledger/split_ledger.csv")
    new_splits = new_splits.loc[new_splits.event_date.gt("2026-09-18")]
    for ticker in new_splits.ticker:
        adjustment_dates[ticker] = END
    book = OfficialActionHistoryBook(
        identities, OUT / "official_execution_overlay", OUT / "provider_split_ledger",
        ledger, as_of_date=END, terminal_repairs=repairs,
        terminal_raw_prices=live[["isin", "trade_date", "latest_price"]],
        resulting_terms=terms, nominal_tickers=nominal,
        adjustment_dates=adjustment_dates,
    )
    return book, profiles, quarantine


def top_diagnostic(frame: pd.DataFrame, score: str) -> dict:
    result = {}
    for profile, group in frame.groupby("profile_name"):
        valid = group.dropna(subset=[score, "future_xirr", "future_shortfall", "future_drawdown"])
        ranked = valid.sort_values([score, "isin"], ascending=[False, True], kind="stable")
        top = ranked.head(20)
        result[profile] = {
            "top20_isins": top["isin"].tolist(),
            "top20_missing_true_5y_share": float(top.cagr_5y_observed.ne(1).mean()),
            "top20_history_months_median": float(top.history_months.median()),
            "scored_available": len(valid),
        }
    return result


def main() -> None:
    if (OUT / "evaluation_record.json").exists() or (OUT / "outcomes_revealed.csv.gz").exists():
        raise FileExistsError("prospective outcomes already revealed")
    bound = guard()
    features = pd.read_csv(OUT / "decision_features_without_outcomes.csv.gz", low_memory=False)
    if features[["future_xirr", "future_shortfall", "future_drawdown"]].notna().any().any():
        raise ValueError("future outcome in decision feature artifact")
    scores = pd.read_csv(OUT / "scores_before_reveal.csv.gz")
    keys = ["isin", "decision_date", "profile_name"]
    if len(scores) != len(features) or scores.duplicated(keys).any() or features.duplicated(keys).any():
        raise ValueError("score/feature key mismatch")
    frame = features.merge(scores[keys + ["champion_score", "v13_score"]],
                           on=keys, how="inner", validate="one_to_one")
    book, profiles, quarantine = book_and_profiles(bound["evidence"])
    # The persisted pre-reveal record and source-hash guard above must have
    # passed before this first call to the 12-month outcome simulator.
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
    actual.to_csv(OUT / "outcomes_revealed.csv.gz", index=False,
                  compression={"method": "gzip", "mtime": 0})
    joined = frame.drop(columns=["future_xirr", "future_shortfall", "future_drawdown"]).merge(
        actual, on=["isin", "profile_name"], how="left", validate="one_to_one")
    for metric in ("future_xirr", "future_shortfall", "future_drawdown"):
        joined.loc[joined.outcome_status.ne("AVAILABLE"), metric] = np.nan
    champ = d.hist.evaluate(joined, "champion_score")
    v13 = d.hist.evaluate(joined, "v13_score")
    pair = champ.merge(v13, on=["decision_date", "profile"], suffixes=("_champion", "_v13"))
    pair.to_csv(OUT / "profile_metrics.csv", index=False)
    aggregate = {metric: {"champion": float(champ[metric].mean()),
                          "v13": float(v13[metric].mean()),
                          "delta": float(v13[metric].mean() - champ[metric].mean())}
                 for metric in d.METRICS}
    top_c = top_diagnostic(joined, "champion_score")
    top_v = top_diagnostic(joined, "v13_score")
    overlap = {p: len(set(top_c[p]["top20_isins"]) & set(top_v[p]["top20_isins"])) / 20
               for p in top_c}
    profile_deltas = {}
    for row in pair.itertuples(index=False):
        profile_deltas[row.profile] = {
            metric: float(getattr(row, metric + "_v13") - getattr(row, metric + "_champion"))
            for metric in d.METRICS}
    record = {"schema": "personalized_v13_prospective_evaluation_v1",
              "decision_date": DAY, "endpoint": END,
              "selection_lock_sha256": LOCK_SHA,
              "pre_reveal_record_sha256": sha(OUT / "pre_reveal_record.json"),
              "pre_reveal_integrity_audit_sha256": sha(OUT / "pre_reveal_integrity_audit.json"),
              "scores_before_reveal_sha256": sha(OUT / "scores_before_reveal.csv.gz"),
              "execution_evidence_summary_sha256": sha(OUT / "execution_evidence_summary.json"),
              "outcomes_revealed_sha256": sha(OUT / "outcomes_revealed.csv.gz"),
              "outcomes_revealed_once": True, "selection_changed_after_reveal": False,
              "rows": len(joined), "outcome_available_rows": int(joined.future_xirr.notna().sum()),
              "quarantined_identity_count": len(quarantine),
              "book_error_identity_count": len(book.errors),
              "aggregate": aggregate, "profile_deltas": profile_deltas,
              "top20_overlap_share": overlap,
              "top20_history_champion": top_c, "top20_history_v13": top_v,
              "production_mutated": False, "frozen_champion_mutated": False}
    (OUT / "evaluation_record.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"aggregate": aggregate,
                      "weekly": profile_deltas.get("weekly"),
                      "lookback60": profile_deltas.get("lookback60")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
