"""Post-lock audit for the deeper v2 walk-forward championship."""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
import numpy as np
import pandas as pd
from research.runners import personalized_deeper_championship_v2 as d
from research.runners import personalized_successor_20261002 as prior

METRICS=d.METRICS


def aggregate_delta(frame: pd.DataFrame) -> dict:
    result={}
    for metric in METRICS:
        old=float(frame[f"{metric}_champion"].mean())
        new=float(frame[f"{metric}_challenger"].mean())
        result[metric]={"champion":old,"challenger":new,"delta":new-old}
    return result


def run():
    root=d.OUT
    lock=json.loads((root/"locked_selection.json").read_text())
    if not (root/"evaluation_record.json").is_file():
        raise FileNotFoundError("final evaluation record required")
    chosen=lock["winner"]
    adjustment=chosen["candidate"].startswith("score_adjustment|")
    if adjustment:
        _,signal,_=chosen["candidate"].split("|")
    else:
        recipe,label,pname=chosen["candidate"].split("|")
    panel=pd.read_pickle(root/"prepared.pkl.gz",compression="gzip")

    # Recreate the locked winner on development only. No selection changes.
    if not (root/"development_winner_profiles.csv").exists():
        dates=lock["selection_dates"]
        base=pd.read_pickle(root/"development_baseline.pkl.gz",compression="gzip")
        scored=(base[["isin","decision_date","profile_name","ranker_score"]].copy()
                if adjustment or float(chosen["alpha"]) == 0 else
                d.predict(panel,dates,d.RECIPES[recipe],label,d.PARAMS[pname],compact=True))
        frame=base.drop(columns=["ranker_score"]).merge(
            scored,on=["isin","decision_date","profile_name"],validate="one_to_one")
        frame["candidate_score"]=(d.score_adjustment_score(frame,signal,float(chosen["age_penalty"]),
                                                              float(chosen.get("age_coefficient",0.0)))
            if adjustment else d.candidate_score(
                frame,float(chosen["goal_weight"]),float(chosen["alpha"]),float(chosen["age_penalty"])))
        dev=d.hist.evaluate(frame,"champion_score").merge(
            d.hist.evaluate(frame,"candidate_score"),
            on=["decision_date","profile"],suffixes=("_champion","_challenger"))
        dev.insert(0,"partition","development")
        dev.to_csv(root/"development_winner_profiles.csv",index=False)
        frame[["isin","decision_date","profile_name","champion_score","candidate_score",
               "cagr_5y_observed","history_months"]].to_csv(
                   root/"development_winner_scores.csv.gz",index=False)

    partitions=[
        ("development","development_winner_profiles.csv","development_winner_scores.csv.gz"),
        ("postlock_2024","postlock_2024_profiles.csv","postlock_2024_diagnostics_scores.csv.gz"),
        ("untouched_final_2025","untouched_final_profiles.csv","untouched_final_2025_scores.csv.gz"),
        ("postfinal_2025","postfinal_2025_profiles.csv","postfinal_2025_diagnostics_scores.csv.gz"),
    ]
    all_slices=[]; turnover=[]; missing=[]; summaries={}
    for partition,slice_file,score_file in partitions:
        measures=pd.read_csv(root/slice_file)
        if "partition" not in measures:
            measures.insert(0,"partition",partition)
        all_slices.append(measures)
        summaries[partition]=aggregate_delta(measures)
        scores=pd.read_csv(root/score_file)
        for (date,profile),group in scores.groupby(["decision_date","profile_name"]):
            for kind,col in (("champion","champion_score"),("challenger","candidate_score")):
                eligible=group.dropna(subset=[col]).sort_values([col,"isin"],ascending=[False,True])
                for n in (20,50,100):
                    missing.append({
                        "partition":partition,"date":date,"profile":profile,"kind":kind,
                        "top_n":n,
                        "top_missing_share":float(eligible.head(n).cagr_5y_observed.ne(1).mean()),
                        "universe_missing_share":float(eligible.cagr_5y_observed.ne(1).mean()),
                    })
        for profile,g in scores.groupby("profile_name"):
            for kind,col in (("champion","champion_score"),("challenger","candidate_score")):
                tops=[]
                for date,block in g.groupby("decision_date"):
                    tops.append((date,set(block.dropna(subset=[col]).nlargest(20,col)["isin"])))
                for (a,old),(b,new) in zip(tops,tops[1:]):
                    turnover.append({
                        "partition":partition,"profile":profile,"kind":kind,
                        "date_a":a,"date_b":b,
                        "replacement_fraction":1-len(old&new)/20,
                    })

    slices=pd.concat(all_slices,ignore_index=True)
    slices.to_csv(root/"all_profile_date_slices.csv",index=False)
    pd.DataFrame(missing).to_csv(root/"missing_history_audit.csv",index=False)
    pd.DataFrame(turnover).to_csv(root/"turnover.csv",index=False)

    # Worst profile/date deltas per partition.
    robust={}
    for partition,g in slices.groupby("partition"):
        date_mean=g.groupby("decision_date").mean(numeric_only=True)
        profile_mean=g.groupby("profile").mean(numeric_only=True)
        robust[partition]={
            "worst_profile_shortfall_delta":float(
                (profile_mean.target_shortfall_top20_challenger-profile_mean.target_shortfall_top20_champion).max()),
            "worst_profile_achievement_delta":float(
                (profile_mean.target_achievement_top20_challenger-profile_mean.target_achievement_top20_champion).min()),
            "worst_profile_median_xirr_delta":float(
                (profile_mean.median_xirr_top20_challenger-profile_mean.median_xirr_top20_champion).min()),
            "worst_profile_drawdown_delta":float(
                (profile_mean.mean_asset_drawdown_top20_challenger-profile_mean.mean_asset_drawdown_top20_champion).min()),
            "worst_date_shortfall_delta":float(
                (date_mean.target_shortfall_top20_challenger-date_mean.target_shortfall_top20_champion).max()),
            "worst_date_achievement_delta":float(
                (date_mean.target_achievement_top20_challenger-date_mean.target_achievement_top20_champion).min()),
            "worst_date_median_xirr_delta":float(
                (date_mean.median_xirr_top20_challenger-date_mean.median_xirr_top20_champion).min()),
        }

    # Current inference is diagnostic only. By 2026-09-18 every panel outcome is mature.
    v3=pd.read_csv(d.V3,low_memory=False)
    frozen=pd.read_csv(d.hist.FREEZE/"rankings.csv.gz",low_memory=False)
    current=frozen.drop(columns=["cagr_5y"]).merge(
        prior.current_features(v3),on=["isin","decision_date"],how="left",validate="many_to_one")
    current["champion_score"]=current.selected_ensemble_score
    if adjustment or float(chosen["alpha"]) == 0:
        current["ranker_score"] = current.lightgbm_lambdarank_score
    else:
        actual=pd.read_csv(
            d.PANEL,
            usecols=["isin","decision_date","profile_name","future_xirr","future_shortfall","future_drawdown"])
        train=panel.drop(columns=["future_xirr","future_shortfall","future_drawdown"]).merge(
            actual,on=["isin","decision_date","profile_name"],how="left",validate="one_to_one")
        pred,_=d.old.fit_predict(train,current,d.RECIPES[recipe],"lgbm",label,d.PARAMS[pname],d.SEED)
        current["ranker_score"]=pred
    current["candidate_score"]=(d.score_adjustment_score(current,signal,float(chosen["age_penalty"]),
                                                          float(chosen.get("age_coefficient",0.0)))
        if adjustment else d.candidate_score(
            current,float(chosen["goal_weight"]),float(chosen["alpha"]),float(chosen["age_penalty"])))
    current[["isin","profile_name","champion_score","candidate_score","cagr_5y_observed"]].to_csv(
        root/"current_scores.csv.gz",index=False)
    identity=v3[["isin","ticker","sector"]]
    base=current.loc[current.profile_name.eq("base7500")].merge(identity,on="isin",how="left")
    cur={}
    for kind,col in (("champion","champion_score"),("challenger","candidate_score")):
        ranked=base.dropna(subset=[col]).sort_values([col,"isin"],ascending=[False,True])
        retail=ranked.loc[ranked.sector.eq("Retailing")]
        cur[kind]={
            "coverage":int(len(ranked)),
            "universe_missing_true_5y":float(ranked.cagr_5y_observed.ne(1).mean()),
            **{f"top{n}_missing_true_5y":float(ranked.head(n).cagr_5y_observed.ne(1).mean()) for n in (20,50,100)},
            "nykaa_global_rank":int(np.flatnonzero(ranked.ticker.eq("NYKAA"))[0]+1),
            "nykaa_retail_rank":int(np.flatnonzero(retail.ticker.eq("NYKAA"))[0]+1),
        }
    (root/"current_diagnostic.json").write_text(json.dumps(cur,indent=2))

    summary={
        "winner":chosen,
        "aggregate":summaries,
        "robustness":robust,
        "current":cur,
        "untouched_final_dates":lock["untouched_final_dates"],
        "selection_uses_untouched_final":lock["selection_uses_untouched_final"],
        "production_mutated":False,
        "frozen_champion_mutated":False,
    }
    (root/"audit_summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))


if __name__=="__main__":
    run()
