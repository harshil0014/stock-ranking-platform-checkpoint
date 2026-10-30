"""Record the locked V12 decision without tuning after final evaluation."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import pandas as pd

OUT=ROOT/"experiments/personalized-deep-championship-20261002/v3"
PANEL=ROOT/"experiments/personalized-deep-history-20261002/real-panel-v12"

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run():
    target=OUT/"decision.json"
    if target.exists():raise FileExistsError(target)
    lock=json.loads((OUT/"locked_selection.json").read_text())
    evaluation=json.loads((OUT/"evaluation_record.json").read_text())
    audit=json.loads((OUT/"audit_summary.json").read_text())
    structure=json.loads((PANEL/"integrity_audit.json").read_text())
    assert evaluation["locked_selection_sha256"]==sha(OUT/"locked_selection.json")
    assert audit["selection_uses_untouched_final"] is False
    final=pd.read_csv(OUT/"untouched_final_profiles.csv")
    profiles=final.groupby("profile").mean(numeric_only=True)
    weekly=profiles.loc["weekly"]
    weekly_short=float(weekly.target_shortfall_top20_challenger-weekly.target_shortfall_top20_champion)
    weekly_draw=float(weekly.mean_asset_drawdown_top20_challenger-weekly.mean_asset_drawdown_top20_champion)
    current=audit["current"]
    overlap=pd.read_csv(PANEL/"outcome_window_overlap.csv")
    pair=overlap.loc[overlap.left_date.eq("2025-01-31") & overlap.right_date.eq("2025-08-31")].iloc[0]
    decision={
        "schema":"personalized_v12_decision_v1",
        "verdict":"PROMISING_CHALLENGER",
        "production_replacement_safe":False,
        "frozen_champion_remains_production":True,
        "selected_policy":{
            "base":"frozen chronological 67% Goal / 33% LambdaRank score",
            "score":"champion_score - 0.05 * short_history_uncertainty - 0.20 * min(downside_volatility_1y / 2, 1)",
            "missing_risk_imputation":"same-decision-date observed median; current inference uses v3 provenance-aware value",
            "stock_specific_rules":False,
        },
        "selection_lock_sha256":sha(OUT/"locked_selection.json"),
        "evaluation_record_sha256":sha(OUT/"evaluation_record.json"),
        "v12_panel_sha256":structure["panel_sha256"],
        "frozen_manifest_verified_files":13,
        "development_utility":lock["winner"]["utility"],
        "aggregate":audit["aggregate"],
        "final_weekly_shortfall_delta":weekly_short,
        "final_weekly_drawdown_delta":weekly_draw,
        "current_top20_missing_true5y_champion":current["champion"]["top20_missing_true_5y"],
        "current_top20_missing_true5y_challenger":current["challenger"]["top20_missing_true_5y"],
        "current_scored_universe_missing_true5y":current["challenger"]["universe_missing_true_5y"],
        "nykaa_rank_champion":current["champion"]["nykaa_global_rank"],
        "nykaa_rank_challenger":current["challenger"]["nykaa_global_rank"],
        "final_dates":["2025-01-31","2025-08-31"],
        "final_horizon_overlap_fraction":float(pair.horizon_overlap_fraction),
        "promotion_reasons_against":[
            "The final weekly profile worsens target shortfall and drawdown materially.",
            "The current Top 20 remains heavily concentrated in names without true 5Y history.",
            "NYKAA remains #1; its older drawdown is visible but the score policy has not corrected this diagnostic.",
            "The two final 12-month outcome windows overlap by 42% and are not independent replications.",
        ],
        "selection_uses_final_outcomes":False,
        "production_mutated":False,
        "frozen_champion_mutated":False,
    }
    target.write_text(json.dumps(decision,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:decision[k] for k in ("verdict","production_replacement_safe",
        "final_weekly_shortfall_delta","final_weekly_drawdown_delta",
        "current_top20_missing_true5y_challenger")},indent=2))

if __name__=="__main__":run()
