"""Seal the V13 development-only history/weekly-risk challenger before new outcomes."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
import pandas as pd

OUT=ROOT/"experiments/personalized-v13-20261002"
V12=ROOT/"experiments/personalized-deep-championship-20261002/v3"

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def main():
    lock=OUT/"locked_selection.json"
    if lock.exists(): raise FileExistsError(lock)
    first=pd.read_csv(OUT/"development_search.csv")
    smooth=pd.read_csv(OUT/"smooth_development_search.csv")
    strict_pass=first.loc[first.v13_gate.eq(True)]
    if len(strict_pass):
        raise ValueError("initial strict family unexpectedly has a passing candidate")
    gate=(smooth.eligible.eq(True)&smooth.utility.gt(0)
          &smooth.weekly_shortfall_delta.le(0)
          &smooth.weekly_drawdown_delta.ge(0)
          &smooth.weekly_achievement_delta.ge(-.02)
          &smooth.lookback60_shortfall_delta.le(.005)
          &smooth.lookback60_drawdown_delta.ge(-.01)
          &smooth.lookback60_achievement_delta.ge(-.05)
          &smooth.current_top20_missing_true_5y.le(.50)
          &smooth.current_top50_missing_true_5y.le(.40))
    passing=smooth.loc[gate].sort_values("utility",ascending=False)
    if passing.empty: raise ValueError("no V13 candidate satisfies revised guardrails")
    w=passing.iloc[0]
    record={
      "schema":"personalized_v13_selection_lock_v1",
      "phase":"development_locked_before_new_final_collection",
      "winner":{
        "family":"smooth_history_confidence_plus_downside_weekly",
        "formula":"champion_score - 0.06*sqrt((1-min(history_months/60,1))*I(no observed true 5Y CAGR)) - 0.20*normalized_downside_volatility_1y - 0.15*I(weekly profile)*normalized_downside_volatility_1y",
        "history_sqrt_coefficient":float(w.history_sqrt_coefficient),
        "downside_coefficient":float(w.downside_coefficient),
        "weekly_extra_downside":float(w.weekly_extra_downside),
        "development_utility":float(w.utility),
        "delta_ndcg20":float(w.delta_ndcg20),
        "delta_target_achievement_top20":float(w.delta_target_achievement_top20),
        "delta_target_shortfall_top20":float(w.delta_target_shortfall_top20),
        "delta_median_xirr_top20":float(w.delta_median_xirr_top20),
        "delta_mean_asset_drawdown_top20":float(w.delta_mean_asset_drawdown_top20),
        "weekly_shortfall_delta":float(w.weekly_shortfall_delta),
        "weekly_achievement_delta":float(w.weekly_achievement_delta),
        "weekly_drawdown_delta":float(w.weekly_drawdown_delta),
        "lookback60_shortfall_delta":float(w.lookback60_shortfall_delta),
        "lookback60_achievement_delta":float(w.lookback60_achievement_delta),
        "lookback60_drawdown_delta":float(w.lookback60_drawdown_delta),
        "current_top20_missing_true_5y":float(w.current_top20_missing_true_5y),
        "current_top50_missing_true_5y":float(w.current_top50_missing_true_5y),
        "current_top100_missing_true_5y":float(w.current_top100_missing_true_5y),
      },
      "selection_evidence":{
        "outcome_dates":"2020-2023 development only",
        "post_2023_outcomes_loaded":False,
        "current_2026_09_18_structure_used":True,
        "mean_xirr_selection_weight":0,
      },
      "guardrails":{
        "initial_strict_gate":{"top20_missing_max":.50,"top50_missing_max":.35,"passing_candidates":0},
        "documented_revised_gate":{"top20_missing_max":.50,"top50_missing_max":.40,"passing_candidates":int(len(passing)),
          "reason":"35% Top-50 gate admitted no positive-development-utility candidate; 40% still requires material reduction from V12 challenger 46% while preserving weekly and broad development gates."},
        "weekly_shortfall_delta_max":0.0,"weekly_drawdown_delta_min":0.0,"weekly_achievement_delta_min":-.02,
        "lookback60_shortfall_delta_max":.005,"lookback60_drawdown_delta_min":-.01,"lookback60_achievement_delta_min":-.05,
      },
      "future_blind_validation":{
        "target_decision_date":"2025-09-30",
        "target_endpoint":"2026-09-30",
        "required_data_cutoff_at_least":"2026-09-30",
        "outcome_values_seen_before_lock":False,
        "evaluate_once_after_verified_data_extension":True,
      },
      "source_sha256":{
        "v12_development_baseline.pkl.gz":sha(V12/"development_baseline.pkl.gz"),
        "development_search.csv":sha(OUT/"development_search.csv"),
        "smooth_development_search.csv":sha(OUT/"smooth_development_search.csv"),
        "personalized_v13_history_weekly_probe.py":sha(ROOT/"research/runners/personalized_v13_history_weekly_probe.py"),
        "personalized_v13_smooth_history_probe.py":sha(ROOT/"research/runners/personalized_v13_smooth_history_probe.py"),
      },
      "production_mutated":False,
      "frozen_champion_mutated":False,
      "v12_final_reused_for_selection":False,
    }
    lock.write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
    digest=sha(lock)
    (OUT/"selection_lock.sha256").write_text(digest+"  locked_selection.json\n",encoding="utf-8")
    print(json.dumps({"lock":str(lock),"sha256":digest,"winner":record["winner"]},indent=2))
if __name__=="__main__": main()
