"""Post-lock audits; reads fixed selection and existing one-time evaluation only."""
from __future__ import annotations

import json
from pathlib import Path
import sys
sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[2] / "src")]
import numpy as np
import pandas as pd
from research.runners import personalized_deep_championship as d
from research.runners import personalized_successor_20261002 as prior


def run():
    root=d.OUT
    lock=json.loads((root/"locked_selection.json").read_text())
    assert (root/"evaluation_record.json").is_file()
    chosen=lock["winner"]
    recipe,label,pname=chosen["candidate"].split("|")
    panel=pd.read_pickle(root/"prepared.pkl.gz",compression="gzip")
    dates=lock["selection_dates"]
    if not (root/"development_winner_profiles.csv").exists():
        scored=d.predict(panel,dates,d.RECIPES[recipe],label,d.PARAMS[pname],compact=True)
        base=pd.read_pickle(root/"development_baseline.pkl.gz",compression="gzip")
        frame=base.drop(columns=["ranker_score"]).merge(scored,on=["isin","decision_date","profile_name"],validate="one_to_one")
        frame["candidate_score"]=d.candidate_score(frame,float(chosen["goal_weight"]),float(chosen["alpha"]),float(chosen["age_penalty"]))
        dev=d.hist.evaluate(frame,"champion_score").merge(d.hist.evaluate(frame,"candidate_score"),on=["decision_date","profile"],suffixes=("_champion","_challenger"))
        dev.to_csv(root/"development_winner_profiles.csv",index=False)
        frame[["isin","decision_date","profile_name","champion_score","candidate_score","cagr_5y_observed","history_months"]].to_csv(root/"development_winner_scores.csv.gz",index=False)
    all_slices=[];turnover=[];missing=[]
    for partition,slice_file,score_file in (("development","development_winner_profiles.csv","development_winner_scores.csv.gz"),
            ("clean_2024","holdout_profiles.csv","clean_2024_holdout_scores.csv.gz"),
            ("exposed_2025","exposed_profiles.csv","exposed_2025_diagnostic_scores.csv.gz")):
        measures=pd.read_csv(root/slice_file)
        if "partition" not in measures:
            measures.insert(0,"partition",partition)
        all_slices.append(measures)
        try:
            scores=pd.read_csv(root/score_file)
        except EOFError:
            # A failed optional score export does not alter locked metrics.
            if partition != "development":
                raise
            continue
        for (date,profile),group in scores.groupby(["decision_date","profile_name"]):
            for kind,col in (("champion","champion_score"),("challenger","candidate_score")):
                eligible=group.dropna(subset=[col]).sort_values([col,"isin"],ascending=[False,True])
                for n in (20,50,100):
                    missing.append({"partition":partition,"date":date,"profile":profile,"kind":kind,
                        "top_n":n,"top_missing_share":float(eligible.head(n).cagr_5y_observed.ne(1).mean()),
                        "universe_missing_share":float(eligible.cagr_5y_observed.ne(1).mean())})
        for profile,g in scores.groupby("profile_name"):
            for kind,col in (("champion","champion_score"),("challenger","candidate_score")):
                tops=[]
                for date,block in g.groupby("decision_date"):
                    tops.append((date,set(block.dropna(subset=[col]).nlargest(20,col)["isin"])))
                for (a,old),(b,new) in zip(tops,tops[1:]):
                    turnover.append({"partition":partition,"profile":profile,"kind":kind,
                        "date_a":a,"date_b":b,"replacement_fraction":1-len(old&new)/20})
    slices=pd.concat(all_slices);slices.to_csv(root/"all_profile_date_slices.csv",index=False)
    pd.DataFrame(missing).to_csv(root/"missing_history_audit.csv",index=False)
    pd.DataFrame(turnover).to_csv(root/"turnover.csv",index=False)
    # A current inference diagnostic is fitted after selection. It has no matured outcome.
    final_dates=lock["holdout_dates"]+lock["exposed_diagnostic_dates"]
    actual=pd.read_csv(d.PANEL,usecols=["isin","decision_date","profile_name","future_xirr","future_shortfall","future_drawdown"])
    actual=actual.loc[actual.decision_date.isin(final_dates)]
    train=panel.merge(actual,on=["isin","decision_date","profile_name"],how="left",validate="one_to_one",suffixes=("","_final"))
    for field in ("future_xirr","future_shortfall","future_drawdown"):
        train[field]=train[field].fillna(train.pop(field+"_final"))
    v3=pd.read_csv(d.V3,low_memory=False)
    frozen=pd.read_csv(d.hist.FREEZE/"rankings.csv.gz",low_memory=False)
    current=frozen.drop(columns=["cagr_5y"]).merge(prior.current_features(v3),on=["isin","decision_date"],how="left",validate="many_to_one")
    current["champion_score"]=current.selected_ensemble_score
    pred,_=d.old.fit_predict(train,current,d.RECIPES[recipe],"lgbm",label,d.PARAMS[pname],d.SEED)
    current["ranker_score"]=pred
    current["candidate_score"]=d.candidate_score(current,float(chosen["goal_weight"]),float(chosen["alpha"]),float(chosen["age_penalty"]))
    current[["isin","profile_name","champion_score","candidate_score","cagr_5y_observed"]].to_csv(root/"current_scores.csv.gz",index=False)
    identity=v3[["isin","ticker","sector"]]
    current=current.loc[current.profile_name.eq("base7500")].merge(identity,on="isin",how="left")
    audit={}
    for kind,col in (("champion","champion_score"),("challenger","candidate_score")):
        ranked=current.dropna(subset=[col]).sort_values([col,"isin"],ascending=[False,True])
        nykaa=ranked.loc[ranked.ticker.eq("NYKAA")]
        retail=ranked.loc[ranked.sector.eq("Retailing")]
        audit[kind]={"coverage":len(ranked),"universe_missing_true_5y":float(ranked.cagr_5y_observed.ne(1).mean()),
            **{f"top{n}_missing_true_5y":float(ranked.head(n).cagr_5y_observed.ne(1).mean()) for n in (20,50,100)},
            "nykaa_global_rank":int(np.flatnonzero(ranked.ticker.eq("NYKAA"))[0]+1),
            "nykaa_retail_rank":int(np.flatnonzero(retail.ticker.eq("NYKAA"))[0]+1),
            "nykaa_score":float(nykaa[col].iloc[0])}
    (root/"current_diagnostic.json").write_text(json.dumps(audit,indent=2))


if __name__=="__main__":
    run()
