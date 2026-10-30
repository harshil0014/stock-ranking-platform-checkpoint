"""Compute locked V13 scores for 2025-09-30 without loading future outcomes."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
import numpy as np
import pandas as pd

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_ranker.personalized import PersonalizedEngine
from stock_ranker.personalized_data import load_history_book
from stock_research.personalized_executable_tournament import load_protocol, rank_executable
from stock_research.personalized_global_tournament import global_existing_evidence, load_frozen_memberships
from stock_research.personalized_official_actions import OfficialActionHistoryBook
from research.runners import personalized_deeper_championship_v2 as d
from research.runners import evaluate_personalized_v13_blind_20240131 as blind
from research.runners.build_deep_personalized_panel_20261002 import verify_provider_ledger

V13 = ROOT / "experiments/personalized-v13-20261002"
OUT = V13 / "prospective-2025-09-30"
SPLIT = ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2"
FREEZE = ROOT / "experiments/personalized-official-action-freeze/build-06"
COHORT = ROOT / "experiments/personalized-data-freeze/build-01"
PROTOCOL = ROOT / "research/protocols/personalized_official_action_tournament_v1.json"
DAY = "2025-09-30"
LOCK_SHA = "dad3ce68b22a1f744650e501505a3ebc78dc7c4bd39c3247982c4ed84bcac13b"


def sha(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def score_and_record(target: pd.DataFrame, target_path: Path, score_path: Path,
                     prereveal_path: Path, provider: dict) -> None:
    if target[["future_xirr", "future_shortfall", "future_drawdown"]].notna().any().any():
        raise ValueError("outcomes present before reveal")
    train = pd.read_pickle(d.OUT / "prepared.pkl.gz", compression="gzip")
    combined = pd.concat([train, target], ignore_index=True, sort=False)
    scored = d.baseline(combined, [DAY])
    scored["v13_score"] = blind.v13_score(scored)
    fixed = scored[["isin", "decision_date", "profile_name", "champion_score", "v13_score",
                    "history_months", "cagr_5y_observed", "downside_volatility_1y"]].copy()
    available = scored.status.eq("AVAILABLE")
    fixed.to_csv(score_path, index=False, compression={"method": "gzip", "mtime": 0})
    prereveal = {
        "schema": "personalized_v13_prospective_pre_reveal_v1", "decision_date": DAY,
        "endpoint": "2026-09-30", "selection_lock_sha256": sha(V13 / "locked_selection.json"),
        "blind_plan_sha256": sha(V13 / "blind_validation_plan.json"),
        "v12_prepared_sha256": sha(d.OUT / "prepared.pkl.gz"),
        "decision_features_without_outcomes_sha256": sha(target_path),
        "scores_before_reveal_sha256": sha(score_path), "score_rows": len(fixed),
        "available_score_rows": int(available.sum()),
        "null_scores_for_available_rows": int(fixed.loc[available, "v13_score"].isna().sum()),
        "null_scores_for_unavailable_rows": int(fixed.v13_score.isna().sum()),
        "provider_ledger_sha256": provider["ledger_sha256"],
        "outcome_columns_loaded": False, "outcome_simulation_run": False,
        "selection_changed": False, "accepted_production_data_mutated": False,
    }
    prereveal_path.write_text(json.dumps(prereveal, indent=2) + "\n")
    print(json.dumps({"score_rows": len(fixed), "scores_sha256": sha(score_path),
                      "pre_reveal_sha256": sha(prereveal_path)}), flush=True)


def main() -> None:
    if sha(V13 / "locked_selection.json") != LOCK_SHA:
        raise ValueError("V13 selection lock drift")
    target_path = OUT / "decision_features_without_outcomes.csv.gz"
    score_path = OUT / "scores_before_reveal.csv.gz"
    prereveal_path = OUT / "pre_reveal_record.json"
    if score_path.exists() or prereveal_path.exists():
        raise FileExistsError("prospective scores already exist")
    OUT.mkdir(parents=True, exist_ok=True)
    provider = verify_provider_ledger(SPLIT)
    if target_path.exists():
        target = pd.read_csv(target_path, low_memory=False)
        if set(target.decision_date.astype(str)) != {DAY} or len(target) != 30305:
            raise ValueError("checkpoint structural mismatch")
        score_and_record(target, target_path, score_path, prereveal_path, provider)
        return
    protocol, profiles = load_protocol(PROTOCOL)
    memberships = load_frozen_memberships(COHORT, protocol["frozen_cohort_fingerprint"])
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    identities = facts.loc[facts["isin"].isin(set.union(*memberships.values())), ["isin", "ticker"]]
    terms = pd.read_csv(ROOT / "research/data/ownership-recovery-20260925/resulting_equity_terms.csv")
    children = facts.loc[facts["isin"].isin(set(terms.child_isin)), ["isin", "ticker"]]
    identities = pd.concat([identities, children]).drop_duplicates("isin")
    failed = pd.read_csv(SPLIT / "acquisition_audit.csv")
    identities = identities.loc[~identities["isin"].isin(set(failed.loc[failed.status.eq("FAILED"), "isin"]))]
    repairs = pd.read_csv(COHORT / "terminal_repairs.csv")
    ledger = pd.read_csv(FREEZE / "normalized_official_action_ledger.csv.gz", low_memory=False)
    for term in terms.itertuples(index=False):
        match = ledger["isin"].eq(term.parent_isin) & ledger.event_date.eq(term.event_date) & ledger.event_type.eq("DEMERGER")
        ledger.loc[match, "mechanics_status"] = "RESULTING_EQUITY"
        ledger.loc[match, "block_reason"] = None
        ledger.loc[match, "economic_policy"] = "RESULTING_EQUITY_HOLD_PRICE_ONLY"
    live_state = json.loads((ROOT / "data/live_market/accepted_state.json").read_text())
    live = pd.read_csv(ROOT / "data/live_market" / live_state["bundle_path"] / "live_market.csv")
    audit = pd.read_csv(ROOT / "research/data/ownership-recovery-20260925/history_recovery_audit.csv")
    nominal = set(audit.loc[audit.raw_basis.eq("OFFICIAL_NOMINAL"), "ticker"])
    adjustment_dates = audit.dropna(subset=["provider_adjustment_through"]).set_index("ticker").provider_adjustment_through.to_dict()
    book = OfficialActionHistoryBook(
        identities, ROOT / "data/live_market/history_cache", SPLIT, ledger,
        as_of_date="2026-09-18", terminal_repairs=repairs,
        terminal_raw_prices=live[["isin", "trade_date", "latest_price"]], resulting_terms=terms,
        history_overlay=ROOT / "external_research_pack/ownership_history_20260925",
        nominal_tickers=nominal, adjustment_dates=adjustment_dates,
    )
    fractional_book, _ = load_history_book(facts, ROOT / "data/live_market/history_cache", terminal_repairs=repairs)
    engine = PersonalizedEngine(fractional_book, cache_size=128)
    evidence = global_existing_evidence(fractional_book, facts, DAY)
    pieces = []
    for name, profile in profiles.items():
        rank = rank_executable(book, profile, DAY, evidence)
        fractional = engine.rank(replace(profile, whole_shares=False), DAY)[["isin", "professor_style_score"]]
        fractional = fractional.rename(columns={"professor_style_score": "fractional_professor_score"})
        rank = rank.merge(fractional, on="isin", how="left", validate="one_to_one")
        rank = rank.loc[rank["isin"].isin(memberships[profile.lookback_months])].copy()
        rank["decision_date"] = DAY
        rank["endpoint"] = "2026-09-30"
        rank["profile_name"] = name
        rank["partition"] = "PROSPECTIVE"
        pieces.append(rank.drop(columns=["journal"], errors="ignore"))
    target = pd.concat(pieces, ignore_index=True)
    if target.duplicated(["isin", "decision_date", "profile_name"]).any():
        raise ValueError("duplicate prospective rows")
    locator = facts[["isin", "ticker"]].drop_duplicates("isin").copy()
    locator["derived_research_sector"] = "GLOBAL"
    features = d.hist.history_features({"prospective": target[["isin", "decision_date"]].drop_duplicates()}, locator)
    features = features.drop(columns=["sector", "sector_median_cagr_5y"])
    target = target.rename(columns={"cagr_5y": "original_cagr_5y"}).merge(
        features, on=["isin", "decision_date"], how="left", validate="many_to_one")
    target["cagr_5y_observed"] = target.cagr_5y_observed.fillna(0).astype("int8")
    observed = target.loc[target.cagr_5y_observed.eq(1), "observed_cagr_5y"]
    anchor = float(observed.median()) if len(observed) else 0.0
    weight = target.history_months.fillna(0).div(60).clip(0, 1)
    estimated = weight * target.history_start_cagr.clip(-.75, 1).fillna(0) + (1 - weight) * np.clip(anchor, -.5, .5)
    target["cagr_5y"] = target.observed_cagr_5y.where(target.cagr_5y_observed.eq(1), estimated)
    target["cagr_5y_source"] = np.where(target.cagr_5y_observed.eq(1), "OBSERVED",
                                         np.where(target.history_months.notna(), "ESTIMATED_GLOBAL", "NO_HISTORY"))
    for col in ("future_xirr", "future_shortfall", "future_drawdown"):
        target[col] = np.nan
    target.to_csv(target_path, index=False, compression={"method": "gzip", "mtime": 0})
    score_and_record(target, target_path, score_path, prereveal_path, provider)


if __name__ == "__main__":
    main()
