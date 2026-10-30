"""Summarize locked V14 evidence; never retrain or alter selection."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from research.runners import personalized_v14_ml_20261003 as v14

OUT=v14.OUT
REPORT=ROOT / "research/reports/personalized_v14_ml_20261003.md"


def fmt(value, pct=False):
    return f"{value*100:.2f}%" if pct else f"{value:.5f}"


def table(frame, cols):
    def cell(value):
        if pd.isna(value):return ""
        if isinstance(value,(float,np.floating)):return f"{value:.5f}"
        return str(value).replace("|","\\|").replace("\n"," ")
    rows=["| " + " | ".join(cols) + " |", "|"+"|".join(["---"]*len(cols))+"|"]
    rows.extend("| "+" | ".join(cell(v) for v in item)+" |" for item in frame[cols].itertuples(index=False,name=None))
    return "\n".join(rows)


def historical_slices():
    scores=pd.read_csv(OUT/"known_evaluation_scores.csv.gz",usecols=v14.KEYS+["v14_score"])
    dates=set(scores.decision_date.unique())
    source=pd.read_pickle(v14.PREP,compression="gzip")
    source=source.loc[source.decision_date.isin(dates),v14.KEYS+
        ["history_months","cagr_5y_observed","downside_volatility_1y",
         "days_since_recorded_high","distance_from_recorded_high"]]
    outcomes=pd.read_csv(v14.PANEL,usecols=v14.KEYS+["future_xirr","future_shortfall","future_drawdown"])
    outcomes=outcomes.loc[outcomes.decision_date.isin(dates)]
    frame=source.merge(outcomes,on=v14.KEYS,validate="one_to_one").merge(scores,on=v14.KEYS,validate="one_to_one")
    frame=frame.merge(v14.benchmark_scores(sorted(dates)),on=v14.KEYS,validate="one_to_one")
    frame["cohort_short_history"]=frame.history_months.lt(60)|frame.history_months.isna()
    frame["cohort_no_true_5y"]=frame.cagr_5y_observed.ne(1)
    frame["cohort_high_downside"]=frame.downside_volatility_1y.ge(
        frame.groupby("decision_date").downside_volatility_1y.transform("median"))
    frame["cohort_old_ath"]=frame.days_since_recorded_high.ge(365)
    frame["cohort_deep_below_ath"]=frame.distance_from_recorded_high.le(-.3)
    rows=[]
    for model,score in (("champion","champion_score"),("v14","v14_score")):
        ranked=frame.dropna(subset=[score,"future_xirr","future_shortfall","future_drawdown"]).sort_values(
            ["decision_date","profile_name",score,"isin"],ascending=[True,True,False,True],kind="stable")
        top=ranked.groupby(["decision_date","profile_name"],sort=False).head(20)
        for cohort in [c for c in frame.columns if c.startswith("cohort_")]:
            subset=top.loc[top[cohort]]
            rows.append({"model":model,"cohort":cohort,"selected_top20_rows":len(subset),
                "share_of_all_top20":len(subset)/len(top),
                "target_achievement":float(subset.future_shortfall.eq(0).mean()) if len(subset) else np.nan,
                "target_shortfall":float(subset.future_shortfall.mean()) if len(subset) else np.nan,
                "median_xirr":float(subset.future_xirr.median()) if len(subset) else np.nan,
                "mean_drawdown":float(subset.future_drawdown.mean()) if len(subset) else np.nan})
    result=pd.DataFrame(rows)
    result.to_csv(OUT/"known_evaluation_history_risk_slices.csv",index=False)
    return result


def stability_and_sector(current):
    scores=pd.read_csv(OUT/"known_evaluation_scores.csv.gz",usecols=v14.KEYS+["v14_score"])
    scores=scores.merge(v14.benchmark_scores(sorted(scores.decision_date.unique())),on=v14.KEYS,validate="one_to_one")
    rows=[]
    for model,column in (("champion","champion_score"),("v14","v14_score")):
        ranked=scores.dropna(subset=[column]).sort_values(
            ["profile_name","decision_date",column,"isin"],ascending=[True,True,False,True],kind="stable")
        top=ranked.groupby(["profile_name","decision_date"],sort=False).head(20)
        for profile,block in top.groupby("profile_name"):
            by_date={date:set(g["isin"]) for date,g in block.groupby("decision_date")}
            dates=sorted(by_date)
            for before,after in zip(dates[:-1],dates[1:]):
                rows.append({"model":model,"profile":profile,"from":before,"to":after,
                    "top20_overlap":len(by_date[before]&by_date[after]),
                    "top20_turnover":1-len(by_date[before]&by_date[after])/20})
    turnover=pd.DataFrame(rows)
    turnover.to_csv(OUT/"known_evaluation_turnover.csv",index=False)
    overlay=v14.ROOT/"experiments/professor-current-fallback-20261003/equal-priority-v2/current_company_facts_equal_priority.csv.gz"
    sector=pd.read_csv(overlay,usecols=["isin","derived_research_sector"]).drop_duplicates("isin")
    merged=current.merge(sector,on="isin",validate="many_to_one")
    concentration=[]
    for model,column in (("champion","champion_rank"),("v14","v14_rank")):
        for n in (20,50,100):
            top=merged.sort_values(["profile_name",column]).groupby("profile_name").head(n)
            for profile,group in top.groupby("profile_name"):
                shares=group.derived_research_sector.fillna("UNKNOWN").value_counts(normalize=True)
                concentration.append({"model":model,"profile":profile,"top_n":n,
                    "sector_hhi":float((shares**2).sum()),"largest_sector":str(shares.index[0]),
                    "largest_sector_share":float(shares.iloc[0]),"sector_count":len(shares)})
    sectors=pd.DataFrame(concentration)
    sectors.to_csv(OUT/"current_sector_concentration.csv",index=False)
    return turnover,sectors


def main():
    lock=json.loads((OUT/"selection_lock_v3.json").read_text())
    decision=json.loads((OUT/"decision.json").read_text())
    assert v14.sha(OUT/"feature_contract.json")==lock["feature_contract_sha256"]
    assert v14.sha(v14.PANEL)==lock["panel_sha256"]
    assert v14.sha(v14.PREP)==lock["prepared_sha256"]
    v14.write_json(OUT/"model_config.json",{"selected_label":lock["selected"]["label"],
        "label_weights":v14.LABELS[lock["selected"]["label"]],
        "lightgbm_parameters":v14.PARAMS[lock["selected"]["params"]],
        "goal_percentile_weight":lock["selected"]["goal_weight"],
        "training_seed":20261003,"feature_contract_sha256":lock["feature_contract_sha256"],
        "model_sha256":v14.sha(OUT/"lambdarank.txt"),
        "final_training_endpoint_rule":"endpoint < 2024-03-31",
        "champion_score_as_model_input":False})
    dev=pd.read_csv(OUT/"development_full.csv")
    dev_champion=pd.read_csv(v14.deep.OUT/"development_champion_profiles.csv")
    assert len(dev_champion)==16*9
    comp=pd.read_csv(OUT/"known_evaluation_comparison.csv")
    current=pd.read_csv(OUT/"current_rankings.csv.gz")
    imp=pd.read_csv(OUT/"feature_importance.csv")
    shap=pd.read_csv(OUT/"current_shap_importance.csv")
    slices=historical_slices()
    turnover,sectors=stability_and_sector(current)
    assert current["isin"].notna().all() and not current.duplicated(v14.KEYS).any()
    assert current.v14_rank.notna().equals(current.champion_rank.notna())
    assert not comp.duplicated(["decision_date","profile"]).any()
    assert len(comp)==12*9
    # The frozen files must still match the accepted prior reproducibility proof.
    freeze=ROOT/"research/freezes/personalized-d499580"
    from stock_research.personalized_shadow import verify
    freeze_manifest=verify(freeze)
    reproduction=json.loads((ROOT/"experiments/professor-current-fallback-20261003/champion-data-refresh-research-v1/summary.json").read_text())
    provenance=json.loads((OUT/"current_provenance_audit.json").read_text())
    assert provenance["risk_only_raw_values_used_as_model_features"] is False
    assert reproduction["baseline_reproduction_max_prediction_error"]<1e-12
    assert reproduction["baseline_reproduction_max_blend_error"]<1e-12
    audit={"panel_sha256":v14.sha(v14.PANEL),"prepared_sha256":v14.sha(v14.PREP),
        "feature_contract_sha256":v14.sha(OUT/"feature_contract.json"),
        "selection_lock_sha256":v14.sha(OUT/"selection_lock_v3.json"),
        "frozen_champion_manifest_sha256":v14.sha(freeze/"manifest.json"),
        "frozen_champion_fingerprint":freeze_manifest["fingerprint"],
        "frozen_current_prediction_reproduction_max_error":reproduction["baseline_reproduction_max_prediction_error"],
        "frozen_current_blend_reproduction_max_error":reproduction["baseline_reproduction_max_blend_error"],
        "equal_priority_current_overlay_sha256":v14.sha(ROOT/"experiments/professor-current-fallback-20261003/equal-priority-v2/current_company_facts_equal_priority.csv.gz"),
        "historical_professor_values_used":False,"current_professor_provenance_used_as_model_feature":False,
        "champion_score_used_as_v14_model_feature":False,"company_identity_used_as_v14_model_feature":False,
        "current_sector_used_historically":False,
        "train_max_endpoint_strictly_before_eval_min_decision":True,
        "evaluation_dates_already_exposed_before_v14":True,
        "evaluation_rows":len(comp),"evaluation_dates":int(comp.decision_date.nunique()),
        "evaluation_profiles":int(comp.profile.nunique()),
        "evaluation_date_profile_duplicates":int(comp.duplicated(["decision_date","profile"]).sum()),
        "current_rows":len(current),"current_profiles":int(current.profile_name.nunique()),
        "current_scored_rows_each":int(current.v14_rank.notna().sum()),
        "current_key_duplicates":int(current.duplicated(v14.KEYS).sum()),
        "current_raw_risk_only_profile_rows_quarantined":provenance["raw_risk_only_profile_rows_quarantined"],
        "production_modified":False}
    v14.write_json(OUT/"leakage_integrity_audit.json",audit)
    metrics=["coverage","rank_ic","ndcg20","pairwise_accuracy","target_achievement_top20",
        "target_shortfall_top20","median_xirr_top20","mean_xirr_top20","mean_asset_drawdown_top20"]
    dev_levels=[]
    for k in metrics:
        baseline=float(dev_champion[k].mean())
        delta=float(lock["selected"]["delta_"+k])
        dev_levels.append({"metric":k,"champion":baseline,"v14":baseline+delta,"delta":delta})
    dev_levels=pd.DataFrame(dev_levels)
    dev_levels.to_csv(OUT/"development_selected_comparison.csv",index=False)
    agg=[]
    for k in metrics:
        a=comp[f"{k}_champion"].mean();b=comp[f"{k}_v14"].mean()
        agg.append({"metric":k,"champion":a,"v14":b,"delta":b-a})
    aggregate=pd.DataFrame(agg)
    aggregate.to_csv(OUT/"aggregate_comparison.csv",index=False)
    prof=[]
    for name,block in comp.groupby("profile"):
        row={"profile":name}
        for k in metrics:row[k+"_delta"]=(block[k+"_v14"]-block[k+"_champion"]).mean()
        prof.append(row)
    profiles=pd.DataFrame(prof)
    profiles.to_csv(OUT/"profile_regressions.csv",index=False)
    dates=[]
    for name,block in comp.groupby("decision_date"):
        row={"decision_date":name}
        for k in metrics:row[k+"_delta"]=(block[k+"_v14"]-block[k+"_champion"]).mean()
        dates.append(row)
    dates=pd.DataFrame(dates)
    dates.to_csv(OUT/"date_regressions.csv",index=False)
    top_stats=[]
    for n in (20,50,100):
        top=current.sort_values(["profile_name","v14_rank"]).groupby("profile_name").head(n)
        old=current.sort_values(["profile_name","champion_rank"]).groupby("profile_name").head(n)
        for profile in sorted(current.profile_name.unique()):
            a=top.loc[top.profile_name.eq(profile)];b=old.loc[old.profile_name.eq(profile)]
            top_stats.append({"profile":profile,"top_n":n,"v14_missing_true_5y":float((1-a.has_true_5y).mean()),
                "champion_missing_true_5y":float((1-b.has_true_5y).mean()),
                "overlap":len(set(a["isin"]) & set(b["isin"])),"turnover":1-len(set(a["isin"]) & set(b["isin"]))/n})
    tops=pd.DataFrame(top_stats)
    tops.to_csv(OUT/"current_top_concentration.csv",index=False)
    base_top=current.loc[current.profile_name.eq("base7500")].sort_values("v14_rank").head(20)
    nykaa=current.loc[current["isin"].eq("INE388Y01029")]
    family={}
    for c in imp.feature:
        family[c]=( "base_goal_execution" if c in v14.BASE else
            "history_growth_risk" if c in v14.HISTORY else
            "relative" if c.startswith("pct_") else "derived_personalization_missingness")
    imp["family"]=imp.feature.map(family)
    imp.to_csv(OUT/"feature_importance.csv",index=False)
    family_imp=imp.groupby("family",as_index=False)[["gain","split"]].sum().sort_values("gain",ascending=False)
    family_imp.to_csv(OUT/"feature_family_importance.csv",index=False)
    # Consecutive quarterly decisions share roughly 9 of 12 outcome months.
    sequence=pd.to_datetime(sorted(comp.decision_date.unique()))
    days=np.diff(sequence.to_numpy()).astype("timedelta64[D]").astype(int)
    overlap=pd.DataFrame({"from":sequence[:-1].date.astype(str),"to":sequence[1:].date.astype(str),
        "decision_gap_days":days,"approx_overlap_days":np.maximum(365-days,0)})
    overlap.to_csv(OUT/"outcome_window_overlap.csv",index=False)
    assert (overlap.approx_overlap_days>0).all()
    lines=["# V14 independent ranking model — research result", "",
        f"**Verdict: {decision['verdict']}.** Production d499580 remains untouched. V14 is a separately trained LightGBM LambdaRank model; its features exclude the champion score/rank and stock identity.","",
        "## Evidence and selection", "",
        f"V12 provides 1,516,870 historical date/profile/security rows on 50 dates (2015-01-31 to 2025-08-31). The development model trains only on labels ending before 2020-03-31. Six initial label/parameter combinations, 15 goal blends of the leading configurations, and eight return-oriented extensions were compared on 16 decisions in 2020–2023. The return extension was declared after observing development median-XIRR losses, before any V14 post-development evaluation. The selected configuration was locked in `selection_lock_v3.json` (SHA256 `{audit['selection_lock_sha256']}`) before V14's 2024–2025 evaluation. The final model trains only on labels ending strictly before 2024-03-31. All 2024–2025 dates were already exposed to earlier research: this is retrospective evaluation, not a new blind test.","",
        f"Selected configuration: `{lock['selected']['label']}` relevance, `{lock['selected']['params']}` parameters, goal percentile weight {lock['selected']['goal_weight']:.2f}, {decision['train_rows']:,} final training rows across {decision['train_groups']} date/profile groups. Label relevance is a weighted average of within-date/profile percentile return, reversed shortfall, drawdown, and achievement, bucketed 0–3. Exact weights and model parameters are in the machine artifacts. Overlapping 12-month outcomes share evidence: adjacent evaluation decisions overlap by {overlap.approx_overlap_days.min()}–{overlap.approx_overlap_days.max()} days. Rows are not independent trials.","",
        f"The locked balanced label weights are {v14.LABELS['balanced']}; LightGBM parameters are {v14.PARAMS[lock['selected']['params']]}. Features cover contribution amount/count/frequency, horizon and target, historical plan score, whole-share affordability and cash use, adjusted price growth (strict 1Y/7Y/10Y where observed), 3Y/5Y, old highs, underwater duration, drawdown, volatility, explicit history completeness, and same-date percentiles. Historical price ratios use observations at or before the decision date with a seven-day anchor tolerance. Missing ranks remain missing; current professor values enter only current inference at equal priority. No historical sector label or current fundamental was backfilled.","",
        "## Development tournament", "",
        table(dev[["label","params","goal_weight","eligible","utility","robustness_failed","delta_ndcg20","delta_target_shortfall_top20","delta_mean_asset_drawdown_top20","weekly_shortfall_delta"]],
            ["label","params","goal_weight","eligible","utility","robustness_failed","delta_ndcg20","delta_target_shortfall_top20","delta_mean_asset_drawdown_top20","weekly_shortfall_delta"]),"",
        "Selected candidate on development (the median-XIRR loss violates selection eligibility):","",
        table(dev_levels,["metric","champion","v14","delta"]),"",
        "## Known retrospective evaluation versus champion", "",
        "Mean XIRR is reported for completeness and has zero selection weight because outliers can dominate it.","",
        table(aggregate,["metric","champion","v14","delta"]),"",
        "Profile deltas (V14 minus champion; drawdown improvement is positive):", "",
        table(profiles[["profile","ndcg20_delta","target_achievement_top20_delta","target_shortfall_top20_delta","median_xirr_top20_delta","mean_asset_drawdown_top20_delta"]],
            ["profile","ndcg20_delta","target_achievement_top20_delta","target_shortfall_top20_delta","median_xirr_top20_delta","mean_asset_drawdown_top20_delta"]),"",
        "Date deltas (negative achievement/return/drawdown and positive shortfall are regressions):","",
        table(dates[["decision_date","ndcg20_delta","target_achievement_top20_delta",
            "target_shortfall_top20_delta","median_xirr_top20_delta","mean_asset_drawdown_top20_delta"]],
            ["decision_date","ndcg20_delta","target_achievement_top20_delta",
            "target_shortfall_top20_delta","median_xirr_top20_delta","mean_asset_drawdown_top20_delta"]),"",
        "Selected Top-20 composition by historical cohort (outcomes within the selected cohort are in the CSV):","",
        table(slices[["model","cohort","share_of_all_top20","target_shortfall","median_xirr","mean_drawdown"]],
            ["model","cohort","share_of_all_top20","target_shortfall","median_xirr","mean_drawdown"]),"",
        "## Current inference on trusted equal-priority data", "",
        f"The same V14 model scored the frozen current plan cohort with the professor current overlay as a normal trusted fallback. The professor provenance field is retained only in the source audit, never fed into the model. Risk-only raw BSE fallback values were excluded from model inputs for {provenance['raw_risk_only_profile_rows_quarantined']} profile rows. This mixes the frozen 2026-09-18 plan snapshot with later current professor fills, so it is an illustrative current-data research inference, not a point-in-time backtest. Current inference does not alter the website.","",
        table(tops.loc[tops.profile.eq("base7500"),["top_n","champion_missing_true_5y","v14_missing_true_5y","overlap","turnover"]],
            ["top_n","champion_missing_true_5y","v14_missing_true_5y","overlap","turnover"]),"",
        f"The base-profile Top 20 changes {20-int(tops.loc[tops.profile.eq('base7500') & tops.top_n.eq(20),'overlap'].iloc[0])} of 20 names and selects no security without observed true 5Y history. This may be an age overcorrection; it is one reason current behavior does not justify promotion. Current sector labels are used here only for diagnostics:","",
        table(sectors.loc[sectors.profile.eq("base7500"),["model","top_n","sector_hhi","largest_sector","largest_sector_share"]],
            ["model","top_n","sector_hhi","largest_sector","largest_sector_share"]),"",
        f"Known-evaluation adjacent-date Top-20 turnover: champion {turnover.loc[turnover.model.eq('champion'),'top20_turnover'].mean():.3f}, V14 {turnover.loc[turnover.model.eq('v14'),'top20_turnover'].mean():.3f}. These 12-month windows overlap heavily, so stability is descriptive.","",
        "Base profile current Top 20 (Top 50 and Top 100 for every profile are separate CSV artifacts):","",
        table(base_top,["v14_rank","ticker","company","champion_rank","has_true_5y"]),"",
        f"NYKAA diagnostic (base7500): {nykaa.loc[nykaa.profile_name.eq('base7500'),['champion_rank','v14_rank','days_since_recorded_high','distance_from_recorded_high','downside_volatility_1y','history_months']].to_dict('records')}. Its identity did not enter training or selection.","",
        "## What V14 learned", "",
        table(imp.head(20),["feature","gain","split","family"]),"",
        "Family gain totals:","",table(family_imp,["family","gain","split"]),"",
        "Current-cohort mean absolute TreeSHAP contributions (deterministic 1-in-20 row sample):","",
        table(shap.head(15),["feature","mean_abs_shap"]),"",
        "A tree can move a stock based on combinations of plan affordability, historical goal performance, growth, history age, distance from highs, underwater duration, and downside volatility. Gain describes fitted split usage, not a causal effect or guaranteed direction. Missing history is passed as NaN with explicit flags; missing relative percentiles remain NaN.","",
        "## Integrity and limits", "",
        f"Panel SHA256 `{audit['panel_sha256']}`; prepared PIT feature SHA256 `{audit['prepared_sha256']}`; frozen manifest SHA256 `{audit['frozen_champion_manifest_sha256']}`. Frozen current-model predictions and blend reproduce to below 1e-12 absolute error. Original source dates and provider V2 panel remain unchanged. No present-day professor value or sector was used on historical rows, and no future outcome, endpoint, identity, or champion score was a V14 feature. The historical champion comparator is the existing maturity-purged V12 walk-forward reproduction of d499580 logic; it is not a fresh deployment of the frozen 2026 model into its own training past. This limits exact historical comparability. Current inference uses the actual frozen 2026 champion output with research-only current professor values. Model selection saw 16 overlapping development dates, and all later V12 dates were already known in prior research. A fresh, independent future period is required for promotion.","",
        f"The known-evaluation robustness gate {'failed' if decision['robustness_failed'] else 'passed'}, but no development candidate met the predeclared eligibility rule. The selected candidate lost {-100*lock['selected']['delta_median_xirr_top20']:.2f} percentage points of median Top-20 XIRR during development. Its later model had more matured training history and did much better retrospectively, yet those later dates were previously exposed and the current Top-20 turnover is high. These facts prevent promotion. No production, Railway, website, or frozen champion file changed.",""]
    REPORT.write_text("\n".join(lines),encoding="utf-8")
    v14.write_json(OUT/"decision.json",{**decision,"selection_lock_sha256":audit["selection_lock_sha256"],
        "frozen_champion_remains_production":True,"production_replacement_safe":False})
    print(REPORT)


if __name__=="__main__":main()
