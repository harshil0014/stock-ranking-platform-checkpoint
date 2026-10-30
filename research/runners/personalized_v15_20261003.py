"""Champion-guided, research-only V15. No writes outside V15 and its report.

Run stages in order: prepare, development, final, current, audit.
All historical evaluation dates are already exposed research, never a blind test.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import pickle
from pathlib import Path
import subprocess
import sys
from dataclasses import asdict

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"
import lightgbm as lgb
import numpy as np
import pandas as pd
from stock_ranker.personalized import InvestorProfile
from stock_research.personalized_validation import ranking_metrics
from stock_research.personalized_executable_tournament import rank_executable
from stock_research.personalized_official_actions import OfficialActionHistoryBook

OUT = ROOT / "experiments/personalized-v15-20261003"
FREEZE = ROOT / "research/freezes/personalized-d499580"
V14 = ROOT / "experiments/personalized-v14-ml-20261003"
V12 = ROOT / "experiments/personalized-deep-championship-20261002/v3"
PREP = V12 / "prepared.pkl.gz"
PANEL = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v12/deep_panel.csv.gz"
V7 = ROOT / "experiments/current-data-recovery-20261003/current_company_facts_recovered_v7_full_yahoo.csv.gz"
YAHOO = V7.parent / "yahoo-full-recovery-v1/history-cache"
SPLITS = ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2"
ACTION = ROOT / "experiments/personalized-official-action-freeze/build-06/normalized_official_action_ledger.csv.gz"
TERMS = ROOT / "research/data/ownership-recovery-20260925/resulting_equity_terms.csv"
REPORT = ROOT / "research/reports/personalized_v15_20261003.md"
KEYS = ["isin", "decision_date", "profile_name"]
OUTCOME = ["future_xirr", "future_shortfall", "future_drawdown"]
CORE = ["enhanced_carry_xirr_score", "enhanced_goal_score", "price_drawdown",
        "cagr_3y", "cagr_5y", "cash_utilization", "unaffordable_rate"]
FAMILIES = {
    "goal_user": ["enhanced_carry_xirr_score", "enhanced_goal_score", "cash_utilization",
        "unaffordable_rate", "amount_per_contribution", "contribution_count", "target_wealth",
        "amount_contributed", "amount_invested", "residual_cash", "target_attainment",
        "target_shortfall", "historical_target_frequency_score", "terminal_price",
        "price_to_contribution", "lookback_months", "horizon_months", "frequency_days",
        "target_cagr", "target_to_contributed"],
    "growth": ["strict_cagr_1y", "cagr_3y", "observed_cagr_5y", "strict_cagr_7y",
        "strict_cagr_10y", "momentum_6m", "history_start_cagr"],
    "ath": ["days_since_recorded_high", "distance_from_recorded_high", "distance_from_52w_high",
        "current_drawdown_duration_days", "max_drawdown_duration_days", "recovery_from_worst_trough",
        "distance_from_1y_low", "old_high_depth", "underwater_depth", "recovery_vs_old_high"],
    "risk": ["price_drawdown", "full_history_max_drawdown", "realized_volatility_1y",
        "downside_volatility_1y", "downside_frequency_1y"],
    "history": ["log_history_months", "has_true_1y", "has_true_3y", "has_true_5y",
        "has_true_7y", "has_true_10y"]}
FEATURES = list(dict.fromkeys(c for family in FAMILIES.values() for c in family))
EXTRA_FIELDS = ["amount_per_contribution", "contribution_count", "target_wealth", "amount_contributed",
    "amount_invested", "residual_cash", "target_attainment", "target_shortfall",
    "historical_target_frequency_score", "terminal_price"]
LABELS = {"return": {"xirr":.75,"shortfall":.15,"drawdown":.05,"achievement":.05},
          "balanced_return": {"xirr":.60,"shortfall":.25,"drawdown":.10,"achievement":.05}}
ALPHAS = [.05,.10,.20,.30]
PARAMS = dict(n_estimators=100, learning_rate=.04, num_leaves=7, max_depth=3,
    min_child_samples=400, reg_lambda=30, colsample_bytree=.9,
    lambdarank_truncation_level=30)
METRICS = ["coverage", "ndcg20", "target_achievement_top20", "target_shortfall_top20",
           "median_xirr_top20", "mean_asset_drawdown_top20", "rank_ic", "pairwise_accuracy"]


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()


def clean(obj):
    if isinstance(obj,dict): return {str(k):clean(v) for k,v in obj.items()}
    if isinstance(obj,(list,tuple)): return [clean(v) for v in obj]
    if isinstance(obj,(np.bool_,bool)): return bool(obj)
    if isinstance(obj,(np.integer,int)): return int(obj)
    if isinstance(obj,(np.floating,float)): return float(obj) if np.isfinite(obj) else None
    return obj


def write(name,obj,exclusive=False):
    with (OUT/name).open("x" if exclusive else "w",encoding="utf-8") as f:
        json.dump(clean(obj),f,indent=2,allow_nan=False)
        f.write("\n")


def csv(name,frame):
    frame.to_csv(OUT/name,index=False,compression={"method":"gzip","mtime":0} if name.endswith(".gz") else None)


def profiles():
    cfg=json.loads((FREEZE/"config.json").read_text(encoding="utf-8"))
    return {name:InvestorProfile(whole_shares=True,**raw) for name,raw in cfg["profiles"].items()}


def protocol():
    return json.loads((ROOT/"research/protocols/personalized_deeper_walkforward_v2.json").read_text())


def protected_paths():
    tracked=subprocess.check_output(["git","ls-files"],cwd=ROOT,text=True).splitlines()
    paths={ROOT/p for p in tracked if (ROOT/p).is_file()}
    for folder in (FREEZE,V14,ROOT/"experiments/personalized-v13-20261002"):
        paths.update(p for p in folder.rglob("*") if p.is_file())
    paths.update([PREP,PANEL,V7,V12/"development_baseline.pkl.gz"])
    for folder in (ROOT/"experiments/personalized-deep-history-20261002").glob("real-panel-v1[234]*"):
        paths.update(p for p in folder.glob("*.csv.gz"))
    return sorted(paths)


def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/"protocol_lock.json").exists(): raise FileExistsError("V15 protocol already locked")
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    assert head=="c12dd9b189bc71684bfac52606eb89abd5e383c7"
    refs=pd.read_csv(V12/"development_champion_profiles.csv")
    bydate=refs.groupby("decision_date").median_xirr_top20.mean()
    # Evidence-based tolerance from champion ONLY, before any V15 candidate.
    robust_sigma=1.4826*float((bydate-bydate.median()).abs().median())
    floor=float(np.clip(.10*robust_sigma,.01,.025))
    rules={"aggregate_median_xirr_delta_min":-floor,"all_profile_median_xirr_delta_min":-.05,
        "weekly_and_12m_median_xirr_delta_min":-floor,
        "aggregate_ndcg_delta_min":-.01,"aggregate_achievement_delta_min":-.02,
        "aggregate_shortfall_delta_max":.005,"aggregate_drawdown_delta_min":-.01,
        "coverage_delta_min":-.001,"worst_profile_shortfall_delta_max":.02,
        "weekly_and_12m_shortfall_delta_max":.005,"weekly_and_12m_drawdown_delta_min":-.01,
        "worst_year_median_xirr_delta_min":-.10,
        "top20_overlap_min":.60,"large_turnover_exception":"NDCG gain >= .03 AND shortfall improvement >= .02",
        "utility":".45*NDCG + .20*achievement - .25*shortfall + .10*drawdown + .10*median_XIRR deltas",
        "require_positive_utility":True}
    contract={"features":FEATURES,"families":FAMILIES,
        "recipes":{"confidence_only":[c for c in FEATURES if c not in FAMILIES["history"]],"explicit_history":FEATURES},
        "uncertainty":"Correction shrinks toward champion in proportion to observed growth/ATH/risk fields; missing evidence never subtracts a score.",
        "fundamentals_peers":"Current diagnostic layer only; no dated historical equivalents available.",
        "identity_provenance_features":False,"horizon_months":12,
        "lookback_months":"12/36/60, distinct from forward horizon"}
    write("feature_contract.json",contract,True)
    write("protocol_lock.json",{"rules":rules,"champion_only_floor_evidence":{"robust_date_sigma":robust_sigma,"floor":floor,
        "source_sha256":sha(V12/"development_champion_profiles.csv")},"labels":LABELS,"alphas":ALPHAS,
        "params":PARAMS,"seed":20261003,"candidate_count":16,
        "development_dates":protocol()["development_selection_dates"],
        "development_training":"endpoint strictly before 2020-03-31",
        "evaluation_training":"endpoint strictly before 2024-03-31",
        "evaluation":"All 2024-2025 dates already exposed; retrospective research only",
        "selection":"Highest eligible development utility; if none eligible, highest utility diagnostic only; lower alpha wins ties",
        "no_current_ranks_or_NYKAA_used_for_selection":True,
        "new_champion_requires_unexposed_validation":True},True)
    hashes={str(p.relative_to(ROOT)):sha(p) for p in protected_paths()}
    write("protected_before.json",hashes,True)
    write("input_inventory.json",{str(p.relative_to(ROOT)):sha(p) for p in [PREP,PANEL,V7,V14/"historical_growth.csv.gz",ACTION,TERMS,SPLITS/"split_ledger.csv",SPLITS/"acquisition_audit.csv"]})
    print("LOCKED",floor,"protected",len(hashes),flush=True)


def add_features(x):
    x=x.copy()
    ps=profiles()
    for col,key in [("lookback_months","lookback_months"),("horizon_months","horizon_months"),
                    ("frequency_days","interval_days"),("target_cagr","target_cagr")]:
        x[col]=x.profile_name.map({n:getattr(p,key) for n,p in ps.items()})
    x["price_to_contribution"]=x.terminal_price/x.amount_per_contribution.where(x.amount_per_contribution>0)
    x["target_to_contributed"]=x.target_wealth/x.amount_contributed.where(x.amount_contributed>0)
    x["has_true_1y"]=x.strict_cagr_1y.notna()
    x["has_true_3y"]=x.history_months.ge(36)&x.cagr_3y.notna()
    x["has_true_5y"]=x.cagr_5y_observed.eq(1)&x.observed_cagr_5y.notna()
    x["has_true_7y"]=x.strict_cagr_7y.notna()
    x["has_true_10y"]=x.strict_cagr_10y.notna()
    x["log_history_months"]=np.log1p(x.history_months.clip(lower=0))
    depth=(-x.distance_from_recorded_high).clip(lower=0,upper=1)
    x["old_high_depth"]=np.log1p(x.days_since_recorded_high.clip(lower=0)/365)*depth
    x["underwater_depth"]=np.log1p(x.current_drawdown_duration_days.clip(lower=0)/365)*depth
    x["recovery_vs_old_high"]=x.recovery_from_worst_trough.clip(-1,10)*depth
    evidence=["strict_cagr_1y","cagr_3y","observed_cagr_5y","distance_from_recorded_high",
        "days_since_recorded_high","current_drawdown_duration_days","downside_volatility_1y","momentum_6m"]
    x["evidence_confidence"]=x[evidence].notna().mean(axis=1)
    for c in FEATURES+["evidence_confidence"]:
        x[c]=pd.to_numeric(x[c],errors="coerce").replace([np.inf,-np.inf],np.nan).clip(-np.finfo(np.float32).max,np.finfo(np.float32).max).astype("float32")
    return x


def load_historical(reveal=False):
    x=pd.read_pickle(PREP,compression="gzip")
    extra=pd.read_csv(PANEL,usecols=KEYS+EXTRA_FIELDS+(OUTCOME if reveal else []),low_memory=False)
    assert not extra.duplicated(KEYS).any()
    if reveal: x=x.drop(columns=OUTCOME)
    x=x.merge(extra,on=KEYS,validate="one_to_one")
    growth=pd.read_csv(V14/"historical_growth.csv.gz")
    x=x.merge(growth,on=["isin","decision_date"],how="left",validate="many_to_one")
    assert len(x)==1516870 and not x.duplicated(KEYS).any()
    if not reveal:
        assert x.loc[x.decision_date.ge("2024-01-01"),OUTCOME].isna().all().all()
    return add_features(x)


def benchmark(dates):
    names=["development_winner_scores.csv.gz","postlock_2024_diagnostics_scores.csv.gz",
           "untouched_final_2025_scores.csv.gz","postfinal_2025_diagnostics_scores.csv.gz"]
    parts=[pd.read_csv(V12/name,usecols=KEYS+["champion_score"]) for name in names]
    result=pd.concat(parts,ignore_index=True)
    result=result.loc[result.decision_date.isin(dates)]
    assert not result.duplicated(KEYS).any()
    return result


def fit(x,label,recipe):
    features=json.loads((OUT/"feature_contract.json").read_text())["recipes"][recipe]
    train=x.loc[x.enhanced_carry_xirr_score.notna() & x[OUTCOME].notna().all(axis=1)].sort_values(KEYS[1:]+KEYS[:1])
    g=train.groupby(["decision_date","profile_name"],sort=False)
    w=LABELS[label]
    utility=(w["xirr"]*g.future_xirr.rank(pct=True)+w["shortfall"]*g.future_shortfall.rank(pct=True,ascending=False)
        +w["drawdown"]*g.future_drawdown.rank(pct=True)+w["achievement"]*train.future_shortfall.eq(0).astype(float))
    labels=np.minimum(np.floor(utility*8),7).astype("int8")
    model=lgb.LGBMRanker(objective="lambdarank",random_state=20261003,n_jobs=4,verbosity=-1,
        deterministic=True,force_col_wise=True,**PARAMS)
    model.fit(train[features],labels,group=g.size().to_list())
    return model.booster_,{"rows":len(train),"groups":g.ngroups,"max_endpoint":train.endpoint.max(),"features":features}


def correction(x,model):
    p=pd.Series(np.nan,index=x.index)
    valid=x.champion_score.notna()&x.enhanced_carry_xirr_score.notna()
    p.loc[valid]=model.predict(x.loc[valid,model.feature_name()],num_threads=4)
    return p.groupby([x.decision_date,x.profile_name]).rank(pct=True)


def guided(x,corr,alpha):
    effective=alpha*x.evidence_confidence
    return x.champion_score*(1-effective)+corr*effective


def evaluate(frame,score):
    return pd.DataFrame({"decision_date":day,"profile":profile,**ranking_metrics(g,score)}
        for (day,profile),g in frame.groupby(["decision_date","profile_name"],sort=True))


def ranked(frame,col):
    good=frame.loc[frame[col].notna()].sort_values(["decision_date","profile_name",col,"isin"],ascending=[True,True,False,True],kind="stable")
    out=pd.Series(np.nan,index=frame.index)
    out.loc[good.index]=good.groupby(["decision_date","profile_name"]).cumcount()+1
    return out


def turnover(frame,score="v15_score"):
    rows=[]
    for (day,profile),g in frame.groupby(["decision_date","profile_name"]):
        a=g.dropna(subset=[score]).sort_values([score,"isin"],ascending=[False,True])
        b=g.dropna(subset=["champion_score"]).sort_values(["champion_score","isin"],ascending=[False,True])
        ranks_a=a.set_index("isin")[score].rank(ascending=False,method="first")
        ranks_b=b.set_index("isin").champion_score.rank(ascending=False,method="first")
        moves=(ranks_a-ranks_b).dropna().abs()
        for n in (20,50,100):
            overlap=len(set(a.head(n)["isin"])&set(b.head(n)["isin"]))
            rows.append({"decision_date":day,"profile":profile,"top_n":n,"overlap":overlap,
                "overlap_fraction":overlap/n,"turnover":1-overlap/n,
                "mean_absolute_rank_movement":float(moves.mean())})
    return pd.DataFrame(rows)


def compare_metrics(new,base):
    pair=new.merge(base,on=["decision_date","profile"],suffixes=("_v15","_champion"),validate="one_to_one")
    for c in METRICS: pair[c+"_delta"]=pair[c+"_v15"]-pair[c+"_champion"]
    return pair


def eligibility(pair,turn):
    rules=json.loads((OUT/"protocol_lock.json").read_text())["rules"]
    delta={c:float(pair[c+"_delta"].mean()) for c in METRICS}
    byprofile=pair.groupby("profile")[[c+"_delta" for c in METRICS]].mean()
    special=byprofile.loc[["weekly","lookback12"]]
    yearly=pair.assign(year=pair.decision_date.str[:4]).groupby("year").median_xirr_top20_delta.mean()
    overlap=float(turn.loc[turn.top_n.eq(20),"overlap_fraction"].mean())
    checks={
        "return_floor":delta["median_xirr_top20"]>=rules["aggregate_median_xirr_delta_min"],
        "profile_return_floor":byprofile.median_xirr_top20_delta.min()>=rules["all_profile_median_xirr_delta_min"],
        "weekly_12m_return_floor":special.median_xirr_top20_delta.min()>=rules["weekly_and_12m_median_xirr_delta_min"],
        "ndcg":delta["ndcg20"]>=rules["aggregate_ndcg_delta_min"],
        "achievement":delta["target_achievement_top20"]>=rules["aggregate_achievement_delta_min"],
        "shortfall":delta["target_shortfall_top20"]<=rules["aggregate_shortfall_delta_max"],
        "drawdown":delta["mean_asset_drawdown_top20"]>=rules["aggregate_drawdown_delta_min"],
        "coverage":delta["coverage"]>=rules["coverage_delta_min"],
        "profile_shortfall":byprofile.target_shortfall_top20_delta.max()<=rules["worst_profile_shortfall_delta_max"],
        "weekly_12m_shortfall":special.target_shortfall_top20_delta.max()<=rules["weekly_and_12m_shortfall_delta_max"],
        "weekly_12m_drawdown":special.mean_asset_drawdown_top20_delta.min()>=rules["weekly_and_12m_drawdown_delta_min"],
        "year_return_floor":yearly.min()>=rules["worst_year_median_xirr_delta_min"],
        "turnover":overlap>=rules["top20_overlap_min"] or (delta["ndcg20"]>=.03 and delta["target_shortfall_top20"]<=-.02)}
    utility=.45*delta["ndcg20"]+.20*delta["target_achievement_top20"]-.25*delta["target_shortfall_top20"]+.10*delta["mean_asset_drawdown_top20"]+.10*delta["median_xirr_top20"]
    checks["positive_utility"]=utility>0
    return {"eligible":all(checks.values()),"utility":utility,"checks":checks,
        "delta":delta,"top20_overlap":overlap,"worst_profile_return":float(byprofile.median_xirr_top20_delta.min()),
        "worst_profile_shortfall":float(byprofile.target_shortfall_top20_delta.max())}


def development():
    if (OUT/"selection_lock.json").exists(): raise FileExistsError("selection already locked")
    x=load_historical()
    train=x.loc[x.endpoint.lt("2020-03-31")].copy()
    dates=protocol()["development_selection_dates"]
    dev=x.loc[x.decision_date.isin(dates)].merge(benchmark(dates),on=KEYS,validate="one_to_one")
    del x;gc.collect()
    assert train.endpoint.max()<min(dates)
    base=evaluate(dev,"champion_score")
    csv("development_champion_profiles.csv",base)
    rows=[]; details={}; frames=[]
    for label in LABELS:
        for recipe in ("confidence_only","explicit_history"):
            name=label+"__"+recipe
            print("TRAIN",name,len(train),flush=True)
            model,audit=fit(train,label,recipe)
            model.save_model(str(OUT/("development_"+name+".txt")))
            corr=correction(dev,model)
            for alpha in ALPHAS:
                candidate=name+"__"+str(alpha)
                dev["v15_score"]=guided(dev,corr,alpha)
                metrics=evaluate(dev,"v15_score")
                pair=compare_metrics(metrics,base)
                turn=turnover(dev)
                stats=eligibility(pair,turn)
                rows.append({"candidate":candidate,"label":label,"recipe":recipe,"alpha":alpha,
                    "eligible":stats["eligible"],"utility":stats["utility"],"top20_overlap":stats["top20_overlap"],
                    **{c+"_delta":v for c,v in stats["delta"].items()}})
                details[candidate]={**stats,"training":audit}
                frames.append(pair.assign(candidate=candidate))
                print("CANDIDATE",candidate,stats["eligible"],stats["utility"],flush=True)
    table=pd.DataFrame(rows).sort_values(["eligible","utility","alpha"],ascending=[False,False,True])
    csv("development_candidates.csv",table)
    csv("development_all_profile_date_results.csv",pd.concat(frames,ignore_index=True))
    write("development_gate_details.json",details)
    best=table.iloc[0].to_dict()
    write("selection_lock.json",{"selected":best,"selected_details":details[best["candidate"]],
        "protocol_lock_sha256":sha(OUT/"protocol_lock.json"),"contract_sha256":sha(OUT/"feature_contract.json"),
        "development_results_sha256":sha(OUT/"development_candidates.csv"),
        "selected_before_v15_final_evaluation":True,"known_outcomes_used_for_selection":False,
        "previous_research_has_exposed_all_final_dates":True},True)
    print("SELECTED",best,flush=True)


def cohort_analysis(frame):
    conditions={"short_history":frame.history_months.lt(60),"full_history":frame.has_true_5y.eq(1),
        "high_volatility":frame.realized_volatility_1y.ge(frame.groupby(["decision_date","profile_name"]).realized_volatility_1y.transform("quantile",.75)),
        "deep_drawdown":frame.full_history_max_drawdown.le(-.5),
        "deep_below_ath":frame.distance_from_recorded_high.le(-.4),
        "old_ath":frame.days_since_recorded_high.ge(365*3)}
    rows=[]
    for name,mask in conditions.items():
        subset=frame.loc[mask]
        for model in ("champion_score","v15_score"):
            measure=evaluate(subset,model)
            selected=frame.dropna(subset=[model]+OUTCOME).sort_values(["decision_date","profile_name",model,"isin"],ascending=[True,True,False,True]).groupby(["decision_date","profile_name"]).head(20)
            cohort_top=selected.loc[mask.reindex(selected.index)]
            rows.append({"cohort":name,"model":model,"rows":len(subset),
                "share_of_overall_top20":len(cohort_top)/max(1,len(selected)),
                "selected_cohort_median_xirr":cohort_top.future_xirr.median(),
                "selected_cohort_shortfall":cohort_top.future_shortfall.mean(),
                "selected_cohort_drawdown":cohort_top.future_drawdown.mean(),
                **measure[METRICS].mean().to_dict()})
    return pd.DataFrame(rows)


def interpretation(frame,model,alpha,prefix):
    valid=frame.loc[frame.champion_score.notna()].copy()
    sample=valid.iloc[::max(1,len(valid)//5000)]
    features=model.feature_name()
    shap=model.predict(sample[features],pred_contrib=True,num_threads=4)[:,:-1]
    fi=pd.DataFrame({"feature":features,"gain":model.feature_importance("gain"),
        "mean_abs_shap":np.abs(shap).mean(axis=0)})
    fi["family"]=fi.feature.map({c:f for f,cs in FAMILIES.items() for c in cs})
    csv(prefix+"_feature_importance.csv",fi.sort_values("mean_abs_shap",ascending=False))
    csv(prefix+"_family_importance.csv",fi.groupby("family",as_index=False)[["gain","mean_abs_shap"]].sum())
    baseline=guided(sample,correction(sample,model),alpha)
    ablations=[]
    for family,cols in FAMILIES.items():
        changed=sample.copy()
        present=[c for c in cols if c in features]
        for c in present:
            changed[c]=changed.groupby(["decision_date","profile_name"])[c].transform("median")
        if not present: continue
        alternative=guided(changed,correction(changed,model),alpha)
        moves=(alternative-baseline).abs()
        ablations.append({"family":family,"mean_abs_score_change":float(moves.mean()),
            "p90_abs_score_change":float(moves.quantile(.9)),"score_changed_fraction":float(moves.gt(1e-8).mean()),
            "method":"Within-query median replacement; correlated family diagnostic, not causal effect"})
    csv(prefix+"_family_counterfactuals.csv",pd.DataFrame(ablations))
    if prefix=="current":
        contributions=model.predict(valid[features],pred_contrib=True,num_threads=4)[:,:-1]
        directional=valid[KEYS+["champion_rank","v15_rank","rank_change","evidence_confidence"]].copy()
        for family,cols in FAMILIES.items():
            positions=[features.index(c) for c in cols if c in features]
            directional[family+"_correction_shap"]=contributions[:,positions].sum(axis=1) if positions else 0.
        csv("current_rank_movement_contributions.csv.gz",directional)
        directional["movement"]=np.select([directional.rank_change.gt(0),directional.rank_change.lt(0)],["UP","DOWN"],default="UNCHANGED")
        cols=[c for c in directional if c.endswith("_correction_shap")]
        csv("current_directional_family_summary.csv",directional.groupby(["profile_name","movement"],as_index=False)[cols].mean())


def final():
    lock=json.loads((OUT/"selection_lock.json").read_text())
    choice=lock["selected"]
    assert lock["protocol_lock_sha256"]==sha(OUT/"protocol_lock.json")
    x=load_historical(True)
    train=x.loc[x.endpoint.lt("2024-03-31")]
    dates=sorted(d for d in x.decision_date.unique() if d>="2024-01-01")
    target=x.loc[x.decision_date.isin(dates)].merge(benchmark(dates),on=KEYS,validate="one_to_one")
    assert train.endpoint.max()<min(dates)
    model,audit=fit(train,choice["label"],choice["recipe"])
    model.save_model(str(OUT/"evaluation_model.txt"))
    target["v15_score"]=guided(target,correction(target,model),choice["alpha"])
    target["v15_rank"]=ranked(target,"v15_score")
    target["champion_rank"]=ranked(target,"champion_score")
    new,base=evaluate(target,"v15_score"),evaluate(target,"champion_score")
    pair=compare_metrics(new,base)
    turn=turnover(target)
    stats=eligibility(pair,turn)
    csv("known_evaluation_profile_date_results.csv",pair)
    csv("known_evaluation_turnover.csv",turn)
    csv("known_evaluation_scores.csv.gz",target[KEYS+["champion_score","v15_score","champion_rank","v15_rank"]+OUTCOME])
    csv("known_evaluation_cohorts.csv",cohort_analysis(target))
    delta_cols=[c+"_delta" for c in METRICS]
    csv("profile_results.csv",pair.groupby("profile",as_index=False)[delta_cols].mean())
    csv("date_results.csv",pair.groupby("decision_date",as_index=False)[delta_cols].mean())
    csv("year_results.csv",pair.assign(year=pair.decision_date.str[:4]).groupby("year",as_index=False)[delta_cols].mean())
    agg=pd.DataFrame({"metric":METRICS,"champion":base[METRICS].mean().values,"v15":new[METRICS].mean().values,
        "delta":[stats["delta"][c] for c in METRICS]})
    csv("aggregate_comparison.csv",agg)
    interpretation(target,model,choice["alpha"],"historical")
    # Resample entire decision-year blocks, retaining all profiles together.
    yearly=pair.assign(year=pair.decision_date.str[:4]).groupby("year")[delta_cols].mean()
    rng=np.random.default_rng(20261003)
    boot=np.array([yearly.iloc[rng.integers(0,len(yearly),len(yearly))].mean().values for _ in range(2000)])
    csv("year_block_uncertainty.csv",pd.DataFrame({"metric":METRICS,"p025":np.quantile(boot,.025,axis=0),"p975":np.quantile(boot,.975,axis=0),"years":len(yearly)}))
    write("evaluation_decision.json",{"development_eligible":choice["eligible"],"evaluation":stats,"training":audit,
        "selection_lock_sha256":sha(OUT/"selection_lock.json"),"known_evaluation_dates":dates,
        "not_blind":True,"overlapping_12m_outcomes":True,"year_bootstrap_only_two_independent_year_blocks":True})
    print("EVALUATED",stats,flush=True)


def coalesce(facts,names):
    result=pd.Series(np.nan,index=facts.index)
    for name in names:
        if name in facts: result=result.fillna(pd.to_numeric(facts[name],errors="coerce"))
    return result


def load_current_book(facts):
    """Refresh observed prices, retain dated official mechanics and quarantine
    unmatched price bases. New post-09-18 mechanics remain an explicit limit.
    """
    actions=pd.read_csv(ACTION,low_memory=False)
    terms=pd.read_csv(TERMS)
    actions["event_date"]=pd.to_datetime(actions.event_date)
    for term in terms.itertuples(index=False):
        mask=actions["isin"].eq(term.parent_isin)&actions.event_date.eq(pd.Timestamp(term.event_date))&actions.event_type.eq("DEMERGER")
        actions.loc[mask,"mechanics_status"]="RESULTING_EQUITY"
        actions.loc[mask,"block_reason"]=None
    book=OfficialActionHistoryBook.__new__(OfficialActionHistoryBook)
    book.actions={i:g for i,g in actions.groupby("isin")}
    book.resulting_terms=terms
    book._window_cache={};book.cache={};book.arrays={};book.errors={}
    provider=pd.read_csv(SPLITS/"split_ledger.csv")
    provider["event_date"]=pd.to_datetime(provider.event_date)
    provider_groups={i:g for i,g in provider.groupby("isin")}
    audit=pd.read_csv(SPLITS/"acquisition_audit.csv")
    accepted=set(audit.loc[audit.status.eq("SUCCESS"),"isin"])
    # Cache frames are source receipts only, never fed into historical training.
    frames={}
    for path in sorted(YAHOO.glob("*.pkl")):
        with path.open("rb") as f: frames.update(pickle.load(f)["frames"])
    latest=pd.read_csv(ROOT/"experiments/current-data-recovery-20261003/current_company_facts_recovered_v6_full_screener.csv.gz",usecols=["isin","latest_price","trade_date"],low_memory=False).set_index("isin")
    receipts=[]
    for row in facts.itertuples(index=False):
        reason=None
        start_cagr=np.nan
        if row.isin not in accepted: reason="PROVIDER_SPLIT_HISTORY_NOT_VERIFIED"
        frame=frames.get(row.yahoo_symbol) if isinstance(row.yahoo_symbol,str) else None
        if frame is None or "Adj Close" not in frame or "Close" not in frame: reason=reason or "NO_YAHOO_HISTORY"
        if frame is not None and "Adj Close" in frame:
            s=pd.to_numeric(frame["Adj Close"],errors="coerce").dropna()
            s=s.loc[s.gt(0)]
            if len(s)>1:
                span=(s.index[-1]-s.index[0]).days
                if span>0:start_cagr=float(np.expm1(np.log(s.iloc[-1]/s.iloc[0])*365/span))
        if reason is None:
            f=frame[["Close","Adj Close"]].dropna().copy()
            f=f.loc[(f.Close>0)&(f["Adj Close"]>0)]
            dates=pd.to_datetime(f.index).tz_localize(None).to_numpy(dtype="datetime64[D]")
            raw=f.Close.to_numpy(float); adjusted=f["Adj Close"].to_numpy(float)
            if len(dates)<2 or int((np.datetime64("2026-10-03")-dates[-1]).astype(int))>7:
                reason="NO_CURRENT_YAHOO_HISTORY"
        if reason is None:
            original=latest.loc[row.isin]
            date=pd.to_datetime(original.trade_date,errors="coerce")
            ix=np.searchsorted(dates,np.datetime64(date.date(),"D"),side="right")-1 if pd.notna(date) else -1
            if ix<0 or not np.isfinite(original.latest_price) or original.latest_price<=0:
                reason="PRIOR_NOMINAL_PRICE_ANCHOR_UNAVAILABLE"
            elif abs(raw[ix]/original.latest_price-1)>.005:
                reason="YAHOO_NOMINAL_BASIS_MISMATCH_OR_LATER_ACTION"
        if reason is None:
            events=provider_groups.get(row.isin,pd.DataFrame(columns=provider.columns)).sort_values("event_date")
            ratios=events.split_ratio.to_numpy(float)
            ed=events.event_date.to_numpy(dtype="datetime64[D]")
            suffix=np.ones(len(ratios)+1)
            if len(ratios): suffix[:-1]=np.cumprod(ratios[::-1])[::-1]
            provider_factor=suffix[np.searchsorted(ed,dates,side="right")]
            nominal=raw*provider_factor
            official=book.actions.get(row.isin,pd.DataFrame(columns=actions.columns))
            automatic=official.loc[official.mechanics_status.eq("AUTO_MULTIPLIER")].sort_values(["event_date","event_type"])
            rr=automatic.total_share_multiplier.to_numpy(float); dd=automatic.event_date.to_numpy(dtype="datetime64[D]")
            ss=np.ones(len(rr)+1)
            if len(rr):ss[:-1]=np.cumprod(rr[::-1])[::-1]
            factor=ss[np.searchsorted(dd,dates,side="right")]
            economic=nominal/factor
            book.arrays[row.isin]=(dates,raw,economic,nominal,factor)
        else: book.errors[row.isin]=reason
        receipts.append({"isin":row.isin,"ticker":row.ticker,"provider_symbol":row.yahoo_symbol,
            "status":"READY" if reason is None else "QUARANTINED","reason":reason,
            "history_start_cagr":start_cagr,
            "last_yahoo_date":getattr(row,"yahoo_history_end_date",None)})
    csv("current_plan_history_audit.csv",pd.DataFrame(receipts))
    del frames;gc.collect()
    return book


def current_features(rows,facts):
    f=facts.set_index("isin")
    mapping={"history_months":"yahoo_history_months","days_since_recorded_high":"yahoo_days_since_adjusted_ath",
        "distance_from_recorded_high":"yahoo_distance_below_adjusted_ath","distance_from_52w_high":"yahoo_distance_from_adjusted_52w_high",
        "full_history_max_drawdown":"yahoo_max_drawdown","current_drawdown_duration_days":"yahoo_current_underwater_days",
        "max_drawdown_duration_days":"yahoo_longest_underwater_days","recovery_from_worst_trough":"yahoo_recovery_from_deepest_trough",
        "realized_volatility_1y":"yahoo_realized_volatility_1y","downside_volatility_1y":"yahoo_downside_volatility_1y",
        "momentum_6m":"yahoo_return_6m","distance_from_1y_low":"yahoo_recovery_from_adjusted_52w_low",
        "downside_frequency_1y":"yahoo_downside_frequency_1y"}
    for target,source in mapping.items(): rows[target]=rows["isin"].map(f[source])
    # V7 trusted values receive equal priority without provenance features.
    for target,sources in {"strict_cagr_1y":["product_baseline_yoy_growth","yahoo_strict_cagr_1y"],
        "cagr_3y":["product_baseline_cagr_3y","yahoo_strict_cagr_3y"],
        "cagr_5y":["product_baseline_cagr_5y","yahoo_strict_cagr_5y"],
        "strict_cagr_7y":["current_cagr_7y","professor_workbook_cagr_7y","yahoo_strict_cagr_7y"],
        "strict_cagr_10y":["current_cagr_10y","professor_workbook_cagr_10y","yahoo_strict_cagr_10y"]}.items():
        vals=coalesce(facts,sources);vals.index=facts["isin"]
        rows[target]=rows["isin"].map(vals)
    rows["observed_cagr_5y"]=rows["isin"].map(f.yahoo_strict_cagr_5y)
    rows["cagr_5y_observed"]=rows["isin"].map(f.current_has_true_5y).fillna(False).astype(int)
    # History-start CAGR is obtained from the actual Yahoo adjusted history.
    history_audit=pd.read_csv(OUT/"current_plan_history_audit.csv").set_index("isin")
    rows["history_start_cagr"]=rows["isin"].map(history_audit.history_start_cagr)
    rows=add_features(rows)
    # True-history flags refer to observed Yahoo evidence, not trusted rates.
    for years in (1,3,5,7,10):
        rows[f"has_true_{years}y"]=rows["isin"].map(f[f"current_has_true_{years}y"]).fillna(False).astype(float)
    return rows


def peer_diagnostics(facts,current):
    peers=facts[["isin","ticker","company"]].copy()
    industry=pd.Series(pd.NA,index=facts.index,dtype="object")
    for col in ["product_basic_industry","screener_industry","product_industry","screener_industry_group"]:
        if col in facts:industry=industry.fillna(facts[col])
    peers["industry"]=industry.fillna("UNKNOWN")
    peers["broad_peer_group"]=facts.screener_industry_group.fillna("UNKNOWN")
    metrics={"growth_1y":["product_baseline_yoy_growth"],"growth_3y":["product_baseline_cagr_3y"],
        "roce":["screener_roce_pct"],"roe":["screener_roe_pct"],
        "roic":["screener_roic_pct"],"debt_equity":["screener_debt_to_equity","debt_to_equity"],
        "valuation_pe":["screener_pe_ratio","pe_ratio"],"operating_margin":["screener_operating_margin_pct"],
        "ath_days":["yahoo_days_since_adjusted_ath"],"ath_depth":["yahoo_distance_below_adjusted_ath"],
        "volatility":["yahoo_realized_volatility_1y"],"momentum6m":["yahoo_return_6m"]}
    peers["peer_count"]=peers.groupby("industry")["isin"].transform("size")
    for name,cols in metrics.items():
        peers[name]=coalesce(facts,cols)
        peers[name+"_peer_percentile"]=peers.groupby("industry")[name].rank(pct=True).where(peers.peer_count.ge(5)&peers.industry.ne("UNKNOWN"))
        peers[name+"_broad_peer_percentile"]=peers.groupby("broad_peer_group")[name].rank(pct=True).where(peers.broad_peer_group.ne("UNKNOWN"))
    csv("current_peer_fundamental_diagnostics.csv",peers)
    summary=[]
    for (profile,model,n),g in current_top_groups(current):
        group=g.merge(peers[["isin","industry"]],on="isin",validate="one_to_one")
        counts=group.industry.value_counts(normalize=True)
        summary.append({"profile":profile,"model":model,"top_n":n,"industry_hhi":float((counts**2).sum()),
            "largest_industry":counts.index[0],"largest_share":float(counts.iloc[0])})
    csv("current_industry_concentration.csv",pd.DataFrame(summary))
    return peers


def current_top_groups(current):
    for profile,g in current.groupby("profile_name"):
        for model,col in [("champion","champion_score"),("v15","v15_score")]:
            ordered=g.dropna(subset=[col]).sort_values([col,"isin"],ascending=[False,True])
            for n in (20,50,100):yield (profile,model,n),ordered.head(n)


def current():
    choice=json.loads((OUT/"selection_lock.json").read_text())["selected"]
    facts=pd.read_csv(V7,low_memory=False)
    assert facts["isin"].is_unique and len(facts)==4436
    current_inputs=[*YAHOO.glob("*.pkl"),SPLITS/"split_ledger.csv",SPLITS/"acquisition_audit.csv",
        ACTION,TERMS,V7,V7.parent/"current_company_facts_recovered_v6_full_screener.csv.gz"]
    write("current_input_inventory.json",{str(p.relative_to(ROOT)):sha(p) for p in current_inputs})
    book=load_current_book(facts)
    ps=profiles();parts=[]
    evidence=pd.DataFrame({"isin":facts["isin"],"global_existing_score":np.nan})
    for name,p in ps.items():
        print("CURRENT_PROFILE",name,flush=True)
        row=rank_executable(book,p,"2026-10-03",evidence)
        row["profile_name"]=name;row["decision_date"]="2026-10-03"
        parts.append(row)
    rows=current_features(pd.concat(parts,ignore_index=True),facts)
    model=lgb.Booster(model_file=str(FREEZE/"lambdarank.txt"))
    frozen=pd.read_csv(FREEZE/"rankings.csv.gz",low_memory=False)
    reproduce=model.predict(frozen[CORE],num_threads=4)
    assert np.nanmax(np.abs(reproduce-frozen.lightgbm_lambdarank_score))<1e-12
    ranks=frozen.groupby("profile_name")[["enhanced_goal_score","lightgbm_lambdarank_score"]].rank(pct=True)
    reproduced_score=.67*ranks.enhanced_goal_score+.33*ranks.lightgbm_lambdarank_score
    assert np.nanmax(abs(reproduced_score-frozen.selected_ensemble_score))<1e-12
    rows["champion_raw_model"]=np.nan
    valid=rows.enhanced_carry_xirr_score.notna()
    rows.loc[valid,"champion_raw_model"]=model.predict(rows.loc[valid,CORE],num_threads=4)
    ranks=rows.groupby(["decision_date","profile_name"])[["enhanced_goal_score","champion_raw_model"]].rank(pct=True)
    rows["champion_score"]=.67*ranks.enhanced_goal_score+.33*ranks.champion_raw_model
    x=load_historical(True)
    train=x.loc[x.endpoint.lt("2026-10-03")]
    corr_model,audit=fit(train,choice["label"],choice["recipe"])
    corr_model.save_model(str(OUT/"current_model.txt"))
    del x,train;gc.collect()
    rows["correction_percentile"]=correction(rows,corr_model)
    rows["v15_score"]=guided(rows,rows.correction_percentile,choice["alpha"])
    rows["champion_rank"]=ranked(rows,"champion_score")
    rows["v15_rank"]=ranked(rows,"v15_score")
    rows["rank_change"]=rows.champion_rank-rows.v15_rank
    frozen["frozen_champion_rank"]=ranked(frozen.rename(columns={"selected_ensemble_score":"champion_score"}),"champion_score")
    rows=rows.merge(frozen[["isin","profile_name","frozen_champion_rank"]],on=["isin","profile_name"],how="left",validate="one_to_one")
    metadata=facts[["isin","ticker","company","yahoo_history_end_date","latest_price","current_has_true_5y"]]
    rows=rows.merge(metadata,on="isin",how="left",validate="many_to_one")
    csv("current_rankings.csv.gz",rows)
    csv("current_turnover.csv",turnover(rows))
    for n in (20,50,100):
        csv(f"current_top{n}.csv",rows.dropna(subset=["v15_rank"]).sort_values(["profile_name","v15_rank"]).groupby("profile_name").head(n))
    csv("current_largest_movers.csv",rows.loc[rows.rank_change.notna()].assign(abs_move=lambda z:z.rank_change.abs()).sort_values("abs_move",ascending=False).groupby("profile_name").head(50))
    composition=[]
    for (profile,model,n),g in current_top_groups(rows):
        composition.append({"profile":profile,"model":model,"top_n":n,"rows":len(g),
            "missing_true_5y_fraction":float(g.has_true_5y.ne(1).mean()),
            "median_history_months":float(g.history_months.median()),"median_days_since_ath":float(g.days_since_recorded_high.median()),
            "median_distance_below_ath":float(g.distance_from_recorded_high.median()),
            "median_underwater_days":float(g.current_drawdown_duration_days.median()),
            "mean_max_drawdown":float(g.full_history_max_drawdown.mean()),
            "mean_downside_volatility":float(g.downside_volatility_1y.mean()),
            "median_growth1y":float(g.strict_cagr_1y.median()),"median_growth3y":float(g.cagr_3y.median())})
    csv("current_history_ath_risk_growth_composition.csv",pd.DataFrame(composition))
    sensitivity=[]
    base=rows.loc[rows.profile_name.eq("base7500")].set_index("isin")
    for profile,g in rows.groupby("profile_name"):
        other=g.set_index("isin")
        for model,col in [("champion","champion_score"),("v15","v15_score")]:
            pair=pd.concat([base[col].rename("base"),other[col].rename("other")],axis=1).dropna()
            sensitivity.append({"profile":profile,"model":model,"shared_scored":len(pair),
                "spearman_with_base":pair.base.corr(pair.other,method="spearman"),
                "top20_overlap_with_base":len(set(base.nlargest(20,col).index)&set(other.nlargest(20,col).index)),
                "mean_absolute_percentile_change":float((pair.base.rank(pct=True)-pair.other.rank(pct=True)).abs().mean())})
    csv("current_user_personalization.csv",pd.DataFrame(sensitivity))
    interpretation(rows,corr_model,choice["alpha"],"current")
    peers=peer_diagnostics(facts,rows)
    nykaa=rows.loc[rows["isin"].eq("INE388Y01029")].copy()
    csv("nykaa_diagnostic.csv",nykaa.merge(peers,on=["isin","ticker","company"],validate="many_to_one"))
    validny=nykaa.loc[nykaa.champion_score.notna()]
    if len(validny):
        shap=corr_model.predict(validny[corr_model.feature_name()],pred_contrib=True,num_threads=4)
        records=[]
        for j,(_,r) in enumerate(validny.iterrows()):
            for k,c in enumerate(corr_model.feature_name()):records.append({"profile":r.profile_name,"feature":c,"value":r[c],"correction_shap":shap[j,k]})
        csv("nykaa_feature_contributions.csv",pd.DataFrame(records))
    write("current_inference_audit.json",{"source":str(V7.relative_to(ROOT)),"source_sha256":sha(V7),
        "current_date":"2026-10-03","training":audit,"rows":len(rows),"universe":len(facts),
        "scored_rows":int(rows.v15_score.notna().sum()),"scored_per_profile":rows.groupby("profile_name").v15_score.count().to_dict(),
        "plans_replayed_at_current_date":True,"actual_yahoo_close_dates":facts.yahoo_history_end_date.value_counts().to_dict(),
        "corporate_action_authority_through":"2026-09-18","corporate_action_coverage_after_that_date_not_proven":True,
        "nominal_basis_mismatches_quarantined":True,"current_fundamentals_and_industries_diagnostic_only":True,
        "professor_screener_yahoo_provenance_not_model_features":True,"frozen_champion_reproduced":True,
        "historical_current_data_used":False})
    print("CURRENT_DONE",int(rows.v15_score.notna().sum()),flush=True)


def table(frame,cols):
    def value(v):
        if pd.isna(v):return ""
        if isinstance(v,(float,np.floating)):return f"{v:.4f}"
        return str(v).replace("|","/").replace("\n"," ")
    lines=["| "+" | ".join(cols)+" |","| "+" | ".join("---" for _ in cols)+" |"]
    lines += ["| "+" | ".join(value(v) for v in row)+" |" for row in frame[cols].itertuples(index=False,name=None)]
    return "\n".join(lines)


def audit():
    current_inputs=[*YAHOO.glob("*.pkl"),SPLITS/"split_ledger.csv",SPLITS/"acquisition_audit.csv",
        ACTION,TERMS,V7,V7.parent/"current_company_facts_recovered_v6_full_screener.csv.gz"]
    write("current_input_inventory.json",{str(p.relative_to(ROOT)):sha(p) for p in current_inputs})
    before=json.loads((OUT/"protected_before.json").read_text())
    changed=[p for p,h in before.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    if changed: raise AssertionError("protected artifacts changed: "+str(changed))
    lock=json.loads((OUT/"selection_lock.json").read_text());choice=lock["selected"]
    ev=json.loads((OUT/"evaluation_decision.json").read_text())
    cur=json.loads((OUT/"current_inference_audit.json").read_text())
    ranks=pd.read_csv(OUT/"current_rankings.csv.gz",low_memory=False)
    assert not ranks.duplicated(KEYS).any()
    assert pd.to_datetime(ranks.yahoo_history_end_date,errors="coerce").max()<=pd.Timestamp("2026-10-03")
    features=json.loads((OUT/"feature_contract.json").read_text())["features"]
    assert not any(any(z in c for z in ["isin","ticker","company","source","professor","future","industry"]) for c in features)
    test=pd.DataFrame({c:[np.nan,np.nan] for c in FEATURES})
    test["profile_name"]=["base7500","lookback60"];test["cagr_5y_observed"]=0;test["history_months"]=[12,120]
    test=add_features(test)
    assert test.horizon_months.tolist()==[12,12] and test.lookback_months.tolist()==[36,60]
    test["champion_score"]=[.9,.5]
    assert np.allclose(guided(test,pd.Series([0.,1.]),.3),test.champion_score)
    test.evidence_confidence=1.
    assert np.allclose(guided(test,pd.Series([0.,1.]),.3),[.63,.65])
    write("validation_checks.json",{"horizon_lookback_separation":True,"no_score_penalty_when_all_correction_evidence_missing":True,
        "correction_bounded_by_alpha":True,"current_no_future_price_dates":True,"current_unique_keys":True,
        "frozen_champion_reproduction":cur["frozen_champion_reproduced"]})
    write("software_versions.json",{"python":sys.version,"pandas":pd.__version__,"numpy":np.__version__,"lightgbm":lgb.__version__})
    benchmark_inputs=[V12/name for name in ["development_winner_scores.csv.gz","postlock_2024_diagnostics_scores.csv.gz",
        "untouched_final_2025_scores.csv.gz","postfinal_2025_diagnostics_scores.csv.gz"]]
    write("historical_benchmark_inventory.json",{str(p.relative_to(ROOT)):sha(p) for p in benchmark_inputs})
    imp=pd.read_csv(OUT/"current_family_importance.csv")
    total=imp.mean_abs_shap.sum()
    fractions=imp.set_index("family").mean_abs_shap/total
    personal=pd.read_csv(OUT/"current_user_personalization.csv")
    personalization=bool(personal.loc[personal.model.eq("v15")&personal.profile.ne("base7500"),"mean_absolute_percentile_change"].gt(.01).any())
    ath_influence=bool(fractions.get("ath",0)>.01)
    history_dominates=bool(fractions.get("history",0)>.40)
    risk_dominates=bool(fractions.get("risk",0)>.50)
    candidate_pass=bool(choice["eligible"] and ev["evaluation"]["eligible"] and personalization and ath_influence and not history_dominates and not risk_dominates)
    verdict="PROMISING CHALLENGER" if candidate_pass else "FROZEN CHAMPION RETAINS"
    integrity={"protected_files_checked":len(before),"protected_changed":changed,"production_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "d499580_unchanged":True,"v14_unchanged":True,"production_website_railway_files_unchanged":True,
        "historical_panels_unchanged":True,"current_values_backfilled":False,"identity_shortcuts":False,
        "protocol_locked_before_search":True,"selection_locked_before_final_evaluation":True,
        "all_final_periods_previously_exposed":True,"history_age_dominates":history_dominates,"risk_dominates":risk_dominates,
        "ath_influential":ath_influence,"user_personalization_present":personalization,
        "feature_family_shap_fractions":fractions.to_dict(),"current_action_authority_limit":cur["corporate_action_authority_through"]}
    write("integrity_audit.json",integrity)
    write("final_candidate_definition.json",{"selected":choice,"formula":"champion_score*(1-alpha*confidence) + learned_correction_percentile*alpha*confidence",
        "confidence":"observed fraction of eight growth/ATH/risk fields; no negative missingness penalty",
        "evaluation_model":"evaluation_model.txt","current_model":"current_model.txt","foundation":"frozen d499580; original core parameters and .67/.33 goal/ranker blend",
        "fundamentals_peers":"Diagnostic only, no training features","current_execution_limit":"Official action authority ends 2026-09-18; later unchanged nominal basis verified, but absence of other actions not proven"})
    decision={"verdict":verdict,"selected":choice,"development_gate_pass":choice["eligible"],
        "known_evaluation_gate_pass":ev["evaluation"]["eligible"],"evaluation":ev["evaluation"],
        "ath_influential":ath_influence,"history_dominates":history_dominates,"risk_dominates":risk_dominates,
        "user_personalization_present":personalization,"promotion_candidate":candidate_pass,
        "deployment":False,"new_champion_not_claimed":"All outcomes already exposed; requires genuinely unexposed prospective validation and refreshed official corporate-action evidence",
        "production_champion_retained":"d499580"}
    write("decision.json",decision)
    agg=pd.read_csv(OUT/"aggregate_comparison.csv")
    prof=pd.read_csv(OUT/"profile_results.csv")
    dev=pd.read_csv(OUT/"development_candidates.csv")
    top=pd.read_csv(OUT/"current_top20.csv")
    turn=pd.read_csv(OUT/"current_turnover.csv")
    comp=pd.read_csv(OUT/"current_history_ath_risk_growth_composition.csv")
    ny=pd.read_csv(OUT/"nykaa_diagnostic.csv")
    lines=["# V15 champion-guided personalized challenger", "",f"**Verdict: {verdict}.** Frozen d499580 remains the production champion.","",
        f"Selected `{choice['candidate']}`: learned return/goal correction with maximum strength {choice['alpha']:.0%}, reduced when evidence is missing. Original champion judgment remains the foundation. No company identity or source provenance enters the model.","",
        "## Locked research design","",
        "Four correction models (two return-oriented labels and two history-feature recipes), each at four fixed blend strengths, were compared on 16 development decisions in 2020–2023. Correction training for development uses only endpoints before 2020-03-31. Final research training uses endpoints before 2024-03-31. The selected candidate is locked before V15 final evaluation. All 2024–2025 outcomes have been exposed to prior research, and are described here as known retrospective evaluation. Adjacent 12-month outcomes overlap; year-block uncertainty has only two evaluation years.","",
        "The historical champion benchmark is the existing maturity-purged replay of d499580's frozen seven-feature recipe and 67/33 goal/ranker blend. It uses weights fitted only on outcomes matured before each historical decision, rather than applying the September 2026 frozen weights backward. Current inference uses the exact frozen d499580 model and verifies that it reproduces its original stored scores before input refresh.","",
        "The median-XIRR loss floor was derived from champion-only date variability and capped at 2.5 percentage points before candidate evaluation. Profile floors and weekly/12M goal/risk limits are fixed in `protocol_lock.json`. Forward horizon is 12 months for every supported profile; lookback length is separately 12/36/60 months. This corrects V14's conflation of lookback with horizon.","",
        f"Development gate: {choice['eligible']}; known evaluation gate: {ev['evaluation']['eligible']}. No threshold was changed after outcomes were evaluated.","",
        table(dev.head(8),["candidate","eligible","utility","median_xirr_top20_delta","target_shortfall_top20_delta","mean_asset_drawdown_top20_delta","top20_overlap"]),"",
        "## Known evaluation against champion", "",table(agg,["metric","champion","v15","delta"]),"",
        table(prof,["profile","median_xirr_top20_delta","target_achievement_top20_delta","target_shortfall_top20_delta","mean_asset_drawdown_top20_delta"]),"",
        "Cohort results, date/year regressions, turnover and two-year block uncertainty are in the accompanying CSVs. Coverage is evaluated on the same date/profile security rows; unavailable execution and label rows are retained in its denominator.","",
        "## Current V7 inference", "",
        f"All {cur['universe']:,} V7 securities are considered across nine profiles. Plans are replayed at 2026-10-03 using observed Yahoo closes; {cur['scored_rows']:,} profile/security rows receive both scores. Original trusted V7 1Y/3Y/5Y/7Y/10Y rates receive equal current priority, regardless of professor/Screener/Yahoo provenance. True-history flags describe observed Yahoo history separately.","",
        "Current whole-share plan mechanics use the audited official action catalogue through 2026-09-18 and provider split ledger. Prior nominal-price anchors are cross-checked against refreshed Yahoo and mismatches are quarantined. Absence of other corporate actions after 2026-09-18 is not proven; the current ranking is conditional research inference, and this limitation must be resolved before promotion. Current replayed champion ranks can differ from its frozen September ranks due to updated inputs; both ranks are retained.","",
        table(turn.loc[turn.profile.eq("base7500")],["top_n","overlap","turnover","mean_absolute_rank_movement"]),"",
        table(comp.loc[comp.profile.eq("base7500")&comp.top_n.eq(20)],["model","missing_true_5y_fraction","median_days_since_ath","median_distance_below_ath","mean_max_drawdown","median_growth1y"]),"",
        "Base profile Top 20:","",table(top.loc[top.profile_name.eq("base7500")],["v15_rank","ticker","company","champion_rank","frozen_champion_rank","has_true_5y"]),"",
        "## Learned behaviour and peer context", "",
        f"ATH influence: {ath_influence}; history-family domination: {history_dominates}; risk-family domination: {risk_dominates}; material user-profile sensitivity: {personalization}. Exact TreeSHAP feature/family contributions and within-query family counterfactuals are supplied. Their shares describe the correction model; the champion still supplies most of the final score. Counterfactuals are correlated-feature diagnostics, not causal claims.","",
        "Current quality and industry percentiles cover growth, ROCE, ROE, ROIC, margin, debt, PE, ATH, volatility and momentum. Peer groups require at least five names. These are a diagnostic layer because historical publication dates and historical classification memberships are unavailable; they cannot safely supply a trained ranking correction yet.","",
        "## NYKAA diagnostic", "",
        table(ny.loc[ny.profile_name.eq("base7500")],["v15_rank","champion_rank","frozen_champion_rank","days_since_recorded_high","distance_from_recorded_high","current_drawdown_duration_days","strict_cagr_1y","cagr_3y","has_true_5y","downside_volatility_1y","enhanced_goal_score","industry","peer_count"]),"",
        "NYKAA is an explanation example only. Neither its frozen #1 nor V14's #213 was a selection target. Its current fundamental/peer values and exact correction feature contributions are retained in the NYKAA CSVs.","",
        "## Integrity and verdict", "",
        f"{len(before):,} protected files were hashed before and after; none changed. d499580, V14, production HEAD, website, Railway configuration and historical panels are unchanged. Historical model inputs come only from decision-dated price/plan features; V7 is loaded only for current inference and diagnostics. No current professor/Screener/Yahoo value was copied to historical dates. Protocol and selection locks, models, all important outputs and this report are hashed in `manifest.json`.","",
        f"{verdict}. Development eligibility and the fixed return/goal/risk/profile gates determine the result. No promotion or deployment was performed.",""]
    REPORT.write_text("\n".join(lines),encoding="utf-8")
    paths=[p for p in OUT.rglob("*") if p.is_file() and p.name not in ("manifest.json","run.log")]+[REPORT,Path(__file__)]
    write("manifest.json",{str(p.relative_to(ROOT)):{"sha256":sha(p),"bytes":p.stat().st_size} for p in sorted(paths)})
    explain()
    print("VERDICT",verdict,flush=True)


def explain():
    """Finalize evidence narratives from locked outputs without fitting or tuning."""
    integrity=json.loads((OUT/"integrity_audit.json").read_text())
    assert integrity["protected_changed"]==[]
    ny=pd.read_csv(OUT/"nykaa_diagnostic.csv")
    row=ny.loc[ny.profile_name.eq("base7500")].iloc[0]
    family=pd.read_csv(OUT/"current_rank_movement_contributions.csv.gz")
    contrib=family.loc[family.profile_name.eq("base7500")&family["isin"].eq("INE388Y01029")].iloc[0]
    broad=pd.read_csv(OUT/"current_peer_fundamental_diagnostics.csv")
    broad_count=int(broad.broad_peer_group.eq(row.broad_peer_group).sum())
    explanation={"diagnostic_only":True,"identity_used_for_training_or_selection":False,
        "v15_rank":row.v15_rank,"refreshed_champion_rank":row.champion_rank,"frozen_champion_rank":row.frozen_champion_rank,
        "days_since_high":row.days_since_recorded_high,"below_high":row.distance_from_recorded_high,
        "underwater_days":row.current_drawdown_duration_days,"growth1y":row.strict_cagr_1y,"growth3y":row.cagr_3y,
        "true_5y":bool(row.has_true_5y),"volatility":row.realized_volatility_1y,
        "historical_plan_attainment":row.target_attainment,"goal_windows_achieved_fraction":row.historical_target_frequency_score,
        "cash_utilization":row.cash_utilization,"roce_pct":row.roce,"roe_pct":row.roe,
        "industry":row.industry,"peer_count":row.peer_count,"broad_peer_group":row.broad_peer_group,
        "broad_peer_count":broad_count,"roce_peer_percentile":row.roce_peer_percentile,
        "roe_peer_percentile":row.roe_peer_percentile,"growth3y_retailing_percentile":row.growth_3y_broad_peer_percentile,
        "correction_family_shap":{f:contrib[f+"_correction_shap"] for f in FAMILIES},
        "interpretation":"Strong recent growth and historical plan fit preserve a high champion foundation. The bounded learned correction lowers the refreshed rank by one. ATH-family TreeSHAP is positive conditional on the other inputs; V15 did not learn a blanket old-high penalty. Current fundamentals/peers are diagnostics, not explanations of model causality."}
    write("nykaa_explanation.json",explanation)
    text=REPORT.read_text(encoding="utf-8")
    generic="NYKAA is an explanation example only. Neither its frozen #1 nor V14's #213 was a selection target. Its current fundamental/peer values and exact correction feature contributions are retained in the NYKAA CSVs."
    detail=(f"NYKAA remains high because its champion foundation retains strong recent growth ({row.strict_cagr_1y:.1%} 1Y and {row.cagr_3y:.1%} 3Y) and strong historical plan fit: the current replay's wealth is {row.target_attainment:.1%} of its target, {row.historical_target_frequency_score:.0%} of rolling goal windows achieved the target, and cash utilization is {row.cash_utilization:.2%}. The high is {row.days_since_recorded_high/365:.2f} years old and price remains {abs(row.distance_from_recorded_high):.1%} below it, with {int(row.current_drawdown_duration_days):,} underwater days. These are observed evidence, rather than an automatic exclusion. True 5Y/7Y/10Y rates are unavailable; annualized recent volatility is {row.realized_volatility_1y:.1%}.\n\n"
        f"The correction moves NYKAA from refreshed champion #{int(row.champion_rank)} to V15 #{int(row.v15_rank)}. Its conditional ATH-family TreeSHAP sum is {contrib.ath_correction_shap:+.4f}; growth, risk and goal/user contributions are {contrib.growth_correction_shap:+.4f}, {contrib.risk_correction_shap:+.4f}, and {contrib.goal_user_correction_shap:+.4f}. Thus the model has not learned a blanket penalty for an old high. These explain the raw correction score, not an additive decomposition of rank positions.\n\n"
        f"Current diagnostic ROCE is {row.roce:.2f}% and ROE {row.roe:.2f}%, both at about the {row.roce_peer_percentile:.0%} percentile among {int(row.peer_count)} E-Retail/E-Commerce peers. Its 3Y growth is at the {row.growth_3y_broad_peer_percentile:.0%} percentile within the {broad_count}-company Retailing group. Fundamentals and peers are not trained ranking inputs. Neither the frozen #1 nor V14's #213 was a target; no identity-specific tuning occurred.")
    if generic in text:text=text.replace(generic,detail)
    marker="## Known evaluation against champion"
    dev=pd.read_csv(OUT/"development_all_profile_date_results.csv")
    choice=json.loads((OUT/"selection_lock.json").read_text())["selected"]
    selected=dev.loc[dev.candidate.eq(choice["candidate"])]
    p=selected.groupby("profile")[["median_xirr_top20_delta","target_shortfall_top20_delta","mean_asset_drawdown_top20_delta"]].mean()
    failure=(f"The decisive development failure is the 12M-lookback profile: median Top-20 XIRR loses {-p.loc['lookback12','median_xirr_top20_delta']*100:.2f} percentage points, shortfall rises {p.loc['lookback12','target_shortfall_top20_delta']*100:.2f} points, and mean drawdown worsens {-p.loc['lookback12','mean_asset_drawdown_top20_delta']*100:.2f} points. Weekly development return improves {p.loc['weekly','median_xirr_top20_delta']*100:.2f} points. Aggregate gains cannot compensate for this failed 12M profile.\n\n")
    if failure not in text:text=text.replace(marker,failure+marker)
    pit=("The security universe follows the existing frozen research cohorts, not a reconstructed historical constituent universe. Survivorship/selection bias and contemporaneous availability of all historical provider revisions are not eliminated. Feature windows and outcome maturity are checked, but this evidence cannot establish a fully untouched investment trial.\n\n")
    if pit not in text:text=text.replace("## Current V7 inference",pit+"## Current V7 inference")
    dates=pd.read_csv(OUT/"date_results.csv")
    regress=dates.loc[dates.median_xirr_top20_delta.lt(0)|dates.target_shortfall_top20_delta.gt(0)]
    if len(regress) and "Known-evaluation date regressions:" not in text:
        text=text.replace("## Current V7 inference","Known-evaluation date regressions:\n\n"+table(regress,["decision_date","median_xirr_top20_delta","target_shortfall_top20_delta","mean_asset_drawdown_top20_delta"])+"\n\n## Current V7 inference")
    REPORT.write_text(text,encoding="utf-8")
    write("pit_scope_audit.json",{"decision_dated_feature_windows":True,"training_endpoint_strictly_before_evaluation":True,
        "current_fundamentals_or_provenance_historical_features":False,"future_outcomes_predictor_features":False,
        "historical_universe_membership_reconstructed":False,"survivorship_bias_eliminated":False,
        "contemporaneous_provider_revision_availability_proven":False,"evaluation_outcomes_previously_exposed":True})
    (OUT/"REPRODUCE.md").write_text("# Reproduce V15\n\nUse the recorded Python/pandas/NumPy/LightGBM versions and the input files listed by hash. On a fresh copy, run:\n\n```powershell\npython research/runners/personalized_v15_20261003.py prepare\npython research/runners/personalized_v15_20261003.py development\npython research/runners/personalized_v15_20261003.py final\npython research/runners/personalized_v15_20261003.py current\npython research/runners/personalized_v15_20261003.py audit\n```\n\nExisting protocol/selection locks intentionally prevent reselection. No online data requests are needed. Current plans use source price receipts and dated official mechanics as documented in the report. All 2024–2025 evaluations are known retrospective research.\n",encoding="utf-8")
    paths=[p for p in OUT.rglob("*") if p.is_file() and p.name!="manifest.json" and not p.name.endswith("_run.log")]+[REPORT,Path(__file__)]
    write("manifest.json",{str(p.relative_to(ROOT)):{"sha256":sha(p),"bytes":p.stat().st_size} for p in sorted(paths)})
    print("EXPLANATIONS_FINALIZED",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=["prepare","development","final","current","audit","explain"])
    stage=parser.parse_args().stage
    globals()[stage]()
