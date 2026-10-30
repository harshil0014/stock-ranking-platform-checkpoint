"""Independent, research-only V14 LambdaRank experiment.

No frozen model score, company identity, current professor value, or future
outcome is a model input. The older V12 prepared matrix supplies PIT history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"

import lightgbm as lgb
import numpy as np
import pandas as pd
from research.runners import personalized_deeper_championship_v2 as deep
from research.runners import personalized_history_challenger as hist

OUT = ROOT / "experiments/personalized-v14-ml-20261003"
PREP = deep.OUT / "prepared.pkl.gz"
PANEL = deep.PANEL
KEYS = ["isin", "decision_date", "profile_name"]
BASE = [
    "amount_per_contribution", "contribution_count", "target_wealth",
    "shares_bought", "amount_contributed", "amount_invested", "residual_cash",
    "cash_utilization", "unaffordable_contributions", "unaffordable_rate",
    "execution_count", "terminal_price", "price_drawdown", "cagr_3y",
    "original_cagr_5y", "enhanced_carry_xirr_score", "enhanced_goal_score",
    "target_attainment", "target_shortfall", "historical_target_frequency_score",
]
HISTORY = [
    "history_months", "history_start_cagr", "days_since_recorded_high",
    "distance_from_recorded_high", "distance_from_52w_high",
    "full_history_max_drawdown", "current_drawdown_duration_days",
    "max_drawdown_duration_days", "recovery_from_worst_trough",
    "realized_volatility_1y", "downside_volatility_1y", "observed_cagr_5y",
    "cagr_5y_observed", "strict_cagr_1y", "strict_cagr_7y", "strict_cagr_10y",
    "momentum_6m", "distance_from_1y_low", "downside_frequency_1y",
]
DERIVED = ["horizon_months", "frequency_months", "target_return_required",
           "has_true_1y", "has_true_3y", "has_true_5y", "has_true_7y",
           "has_true_10y", "missing_5y", "short_history",
           "price_to_contribution", "recorded_high_price_derived"]
PCT = ["enhanced_goal_score", "strict_cagr_1y", "cagr_3y", "observed_cagr_5y",
       "history_months", "days_since_recorded_high", "distance_from_recorded_high",
       "full_history_max_drawdown", "downside_volatility_1y"]
FEATURES = BASE + HISTORY + DERIVED + ["pct_" + c for c in PCT]
FORBIDDEN = ("future", "endpoint", "resulting_", "champion", "professor_excel", "ticker", "isin", "sector")
LABELS = {
    "balanced": {"xirr": .40, "shortfall": .25, "drawdown": .20, "achievement": .15},
    "goal": {"xirr": .25, "shortfall": .40, "drawdown": .15, "achievement": .20},
    "risk": {"xirr": .30, "shortfall": .20, "drawdown": .35, "achievement": .15},
    "return": {"xirr": .75, "shortfall": .10, "drawdown": .10, "achievement": .05},
}
PARAMS = {
    "compact": dict(n_estimators=80, learning_rate=.045, num_leaves=7, max_depth=3,
                    min_child_samples=150, reg_lambda=15, colsample_bytree=.85,
                    lambdarank_truncation_level=30),
    "regularized": dict(n_estimators=120, learning_rate=.035, num_leaves=11, max_depth=4,
                        min_child_samples=250, reg_lambda=30, colsample_bytree=.8,
                        lambdarank_truncation_level=30),
}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def check_contract():
    if len(FEATURES) != len(set(FEATURES)) or any(any(x in f for x in FORBIDDEN) for f in FEATURES):
        raise ValueError("V14 feature contract contains duplicate or forbidden feature")


def add_features(frame):
    """Only decision-time fields. Missing percentiles remain missing."""
    check_contract()
    x = frame.copy()
    x["horizon_months"] = x.profile_name.map({"lookback12": 12., "lookback60": 60.}).fillna(36.)
    x["frequency_months"] = x.profile_name.map({"weekly": .25, "quarterly": 3.}).fillna(1.)
    contribution = pd.to_numeric(x["amount_per_contribution"], errors="coerce")
    price = pd.to_numeric(x["terminal_price"], errors="coerce")
    x["price_to_contribution"] = price.div(contribution.where(contribution.gt(0)))
    x["target_return_required"] = (pd.to_numeric(x.target_wealth, errors="coerce")
        .div(pd.to_numeric(x.amount_contributed, errors="coerce").where(lambda s: s.gt(0)))
        .clip(.01, 100).pow(12 / x.horizon_months) - 1)
    x["has_true_1y"] = x.strict_cagr_1y.notna()
    x["has_true_3y"] = x.history_months.ge(36) & x.cagr_3y.notna()
    x["has_true_5y"] = x.cagr_5y_observed.eq(1) & x.observed_cagr_5y.notna()
    x["has_true_7y"] = x.strict_cagr_7y.notna()
    x["has_true_10y"] = x.strict_cagr_10y.notna()
    x["missing_5y"] = ~x.has_true_5y
    x["short_history"] = x.history_months.lt(60) | x.history_months.isna()
    x["recorded_high_price_derived"] = price.div((1 + x.distance_from_recorded_high).where(lambda s:s.gt(0)))
    for c in PCT:
        x["pct_" + c] = x.groupby(["decision_date", "profile_name"], sort=False)[c].rank(pct=True)
    for c in FEATURES:
        x[c] = pd.to_numeric(x[c], errors="coerce").astype("float32")
    return x


def relevance(frame, mode):
    group = frame.groupby(["decision_date", "profile_name"], sort=False)
    pct = lambda name, ascending=True: group[name].rank(pct=True, ascending=ascending)
    weights = LABELS[mode]
    utility = (weights["xirr"] * pct("future_xirr")
        + weights["shortfall"] * pct("future_shortfall", False)
        + weights["drawdown"] * pct("future_drawdown")
        + weights["achievement"] * pct("future_shortfall", False).where(frame.future_shortfall.gt(0), 1.0))
    return np.minimum(np.floor(utility * 4), 3).astype("int8")


def train_model(frame, mode, params):
    ordered = frame.loc[frame.enhanced_carry_xirr_score.notna()
        & frame[["future_xirr", "future_shortfall", "future_drawdown"]].notna().all(axis=1)]
    ordered = ordered.sort_values(KEYS[1:] + KEYS[:1], kind="stable")
    groups = ordered.groupby(["decision_date", "profile_name"], sort=False).size().to_list()
    assert sum(groups) == len(ordered) and min(groups) > 20
    y = relevance(ordered, mode)
    model = lgb.LGBMRanker(objective="lambdarank", random_state=20261003, n_jobs=4,
        verbosity=-1, deterministic=True, force_col_wise=True, **params)
    model.fit(ordered[FEATURES], y, group=groups)
    return model, len(ordered), len(groups)


def score(frame, model):
    result = frame[KEYS].copy()
    result["v14_score"] = np.nan
    valid = frame.enhanced_carry_xirr_score.notna()
    result.loc[valid, "v14_score"] = model.predict(frame.loc[valid, FEATURES])
    result["v14_rank"] = result.groupby(["decision_date", "profile_name"]).v14_score.rank(ascending=False, method="first")
    return result


def blend_independent_ranker(frame, scored, goal_weight):
    """Percentile blend with the historical goal feature, never champion score."""
    if goal_weight == 0:
        return scored
    result=scored.copy()
    ranker=result.groupby(["decision_date","profile_name"]).v14_score.rank(pct=True)
    goal=frame.groupby(["decision_date","profile_name"]).enhanced_goal_score.rank(pct=True)
    result["v14_score"]=goal_weight*goal.to_numpy()+(1-goal_weight)*ranker.to_numpy()
    result["v14_rank"]=result.groupby(["decision_date","profile_name"]).v14_score.rank(ascending=False,method="first")
    return result


def load_data():
    prepared = pd.read_pickle(PREP, compression="gzip")
    # Prepared V12 features contain no current professor data. Outcome values
    # for 2024/25 are admitted from the now-exposed V12 panel solely for eval.
    more = [c for c in BASE if c not in prepared.columns]
    outcome = pd.read_csv(PANEL, usecols=KEYS + more + ["future_xirr", "future_shortfall", "future_drawdown"], low_memory=False)
    assert not outcome.duplicated(KEYS).any()
    x = prepared.drop(columns=["future_xirr", "future_shortfall", "future_drawdown"])
    x = x.merge(outcome, on=KEYS, validate="one_to_one")
    assert len(x) == len(prepared) == 1516870
    x = x.merge(historical_growth(x),on=["isin","decision_date"],how="left",validate="many_to_one")
    return add_features(x)


def historical_growth(frame):
    """Supplement V12 PIT history with strict horizon ratios from adjusted prices."""
    cache = OUT / "historical_growth.csv.gz"
    if cache.exists():
        return pd.read_csv(cache)
    from stock_ranker.company_facts import resolve_company_fact_snapshot
    from research.runners.personalized_history_challenger import load_company_fact_snapshot
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    ticker = facts.drop_duplicates("isin").set_index("isin").ticker.to_dict()
    wanted = frame[["isin","decision_date"]].drop_duplicates()
    records=[]
    root=ROOT / "data/live_market/history_cache"
    recovery=ROOT / "experiments/history-enrichment-20261002/recovery_overlay_frozen_v1"
    for identity, group in wanted.groupby("isin",sort=False):
        symbol=ticker.get(identity)
        path=root / f"{symbol}.csv"
        if not path.is_file(): path=recovery / f"{symbol}.csv"
        if not path.is_file(): continue
        try:
            source=pd.read_csv(path,usecols=["date","adjusted_close"])
            dates=pd.to_datetime(source.date,errors="coerce").to_numpy(dtype="datetime64[D]")
            prices=pd.to_numeric(source.adjusted_close,errors="coerce").to_numpy(float)
            valid=~np.isnat(dates)&np.isfinite(prices)&(prices>0)
            dates,prices=dates[valid],prices[valid]
            if len(dates)<2 or np.any(np.diff(dates).astype(int)<=0):continue
        except (OSError,ValueError):continue
        for day in group.decision_date:
            cutoff=np.datetime64(day,"D")
            k=np.searchsorted(dates,cutoff,side="right")
            if k<2 or int((cutoff-dates[k-1]).astype(int))>7: continue
            d,p=dates[:k],prices[:k]
            row={"isin":identity,"decision_date":day}
            for years in (1,7,10):
                anchor=np.datetime64((pd.Timestamp(day)-pd.DateOffset(years=years)).date(),"D")
                ix=np.searchsorted(d,anchor,side="right")-1
                good=ix>=0 and 0<=int((anchor-d[ix]).astype(int))<=7 and ix<k-1
                row[f"strict_cagr_{years}y"]=(float(np.expm1(np.log(p[-1]/p[ix])*365/int((d[-1]-d[ix]).astype(int)))) if good else np.nan)
            anchor=cutoff-np.timedelta64(183,"D")
            ix=np.searchsorted(d,anchor,side="right")-1
            row["momentum_6m"]=float(p[-1]/p[ix]-1) if ix>=0 and int((anchor-d[ix]).astype(int))<=7 else np.nan
            start=np.searchsorted(d,cutoff-np.timedelta64(365,"D"))
            yp=p[start:]
            row["distance_from_1y_low"]=float(p[-1]/np.min(yp)-1) if len(yp)>1 else np.nan
            returns=np.diff(np.log(yp))
            row["downside_frequency_1y"]=float(np.mean(returns<0)) if len(returns)>5 else np.nan
            records.append(row)
    out=pd.DataFrame(records)
    out.to_csv(cache,index=False,compression={"method":"gzip","mtime":0})
    return out


def compare(frame, scores, benchmark):
    merged = frame.merge(scores, on=KEYS, validate="one_to_one").merge(
        benchmark[KEYS + ["champion_score"]], on=KEYS, validate="one_to_one")
    a = hist.evaluate(merged, "v14_score")
    b = hist.evaluate(merged, "champion_score")
    return a, b, merged


def summary(a, b):
    delta = a[hist.METRICS].mean() - b[hist.METRICS].mean()
    joined = a.merge(b, on=["decision_date", "profile"], suffixes=("_v14", "_champion"))
    weekly = joined.loc[joined.profile.eq("weekly")]
    fail = (delta.coverage < -.001 or delta.target_shortfall_top20 > .005
        or delta.mean_asset_drawdown_top20 < -.01
        or (weekly.target_shortfall_top20_v14-weekly.target_shortfall_top20_champion).mean() > .005
        or (weekly.mean_asset_drawdown_top20_v14-weekly.mean_asset_drawdown_top20_champion).mean() < -.01)
    utility = (delta.ndcg20 + delta.target_achievement_top20
        - 2*delta.target_shortfall_top20 + delta.median_xirr_top20
        + delta.mean_asset_drawdown_top20 + .3*delta.rank_ic)
    return {"utility": float(utility), "robustness_failed": bool(fail),
            **{f"delta_{k}":float(v) for k,v in delta.items()},
            "worst_profile_shortfall_delta": float((joined.groupby("profile").target_shortfall_top20_v14.mean()
                - joined.groupby("profile").target_shortfall_top20_champion.mean()).max()),
            "weekly_shortfall_delta": float((weekly.target_shortfall_top20_v14-weekly.target_shortfall_top20_champion).mean()),
            "weekly_drawdown_delta": float((weekly.mean_asset_drawdown_top20_v14-weekly.mean_asset_drawdown_top20_champion).mean())}


def benchmark_scores(dates):
    files = ["development_winner_scores.csv.gz", "postlock_2024_diagnostics_scores.csv.gz",
             "untouched_final_2025_scores.csv.gz", "postfinal_2025_diagnostics_scores.csv.gz"]
    blocks = [pd.read_csv(deep.OUT / f, usecols=KEYS+["champion_score"]) for f in files]
    all_scores = pd.concat(blocks, ignore_index=True)
    all_scores = all_scores.loc[all_scores.decision_date.isin(dates)]
    assert not all_scores.duplicated(KEYS).any()
    return all_scores


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "development", "development_blend", "development_return", "final", "current", "manifest"])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.stage == "prepare":
        if (OUT / "feature_contract.json").exists():
            raise FileExistsError("feature contract already frozen")
        write_json(OUT / "feature_contract.json", {"features": FEATURES, "families": {"base":BASE,"history":HISTORY,
            "derived":DERIVED,"same_date_percentiles":["pct_"+c for c in PCT]},
            "forbidden":FORBIDDEN,"missing_policy":"native NaN; rank percentiles missing; explicit flags",
            "historical_current_professor_values_used":False,"historical_current_sectors_used":False})
        write_json(OUT / "split_definition.json", {"train_for_development":"endpoint < 2020-03-31 and decision < 2020-03-31",
            "development":"2020-03-31 through 2023-12-31", "train_for_final":"endpoint < 2024-03-31 and decision < 2024-03-31",
            "known_retrospective":"2024-03-31 through 2025-08-31", "known_dates_are_blind":False})
        write_json(OUT / "label_definition.json", {"weights":LABELS,"formula":"weighted within-date/profile percentiles; 4 relevance buckets",
            "future_labels_only_used_for_training_labels_and_evaluation":True})
        print("feature contract locked", sha(OUT / "feature_contract.json"), flush=True)
        return
    if args.stage == "development":
        if (OUT / "selection_lock.json").exists(): raise FileExistsError("V14 selection already locked")
        x = load_data()
        dates = deep.protocol()["development_selection_dates"]
        train = x.loc[pd.to_datetime(x.endpoint).lt("2020-03-31") & x.decision_date.lt("2020-03-31")]
        dev = x.loc[x.decision_date.isin(dates)]
        assert pd.to_datetime(train.endpoint).max() < pd.Timestamp(min(dates))
        base = benchmark_scores(dates)
        rows = []
        for mode in LABELS:
            for name, params in PARAMS.items():
                print("training", mode, name, len(train), flush=True)
                model, n, groups = train_model(train, mode, params)
                scored = score(dev, model)
                a,b,_ = compare(dev, scored, base)
                result = {"label":mode,"params":name,"train_rows":n,"train_groups":groups,**summary(a,b)}
                rows.append(result)
                pd.DataFrame(rows).to_csv(OUT / "development_tournament.partial.csv", index=False)
        tournament = pd.DataFrame(rows).sort_values(["robustness_failed","utility"], ascending=[True,False])
        tournament.to_csv(OUT / "development_tournament.csv", index=False)
        best = tournament.iloc[0].to_dict()
        write_json(OUT / "selection_lock.json", {"selected":best,"feature_contract_sha256":sha(OUT / "feature_contract.json"),
            "panel_sha256":sha(PANEL),"prepared_sha256":sha(PREP),"tournament_sha256":sha(OUT / "development_tournament.csv"),
            "selection_dates":dates,"known_evaluation_not_used_for_selection":True,
            "promotion_predetermined":"Reject if coverage decreases >0.1pp, shortfall increases >0.5pp, drawdown worsens >1pp, or weekly shortfall/drawdown breaches those limits; require aggregate and profile breadth."})
        print("selected",best,flush=True)
        return
    if args.stage == "development_blend":
        if (OUT/"selection_lock_v2.json").exists():raise FileExistsError("blend selection already locked")
        assert not (OUT/"known_evaluation_scores.csv.gz").exists()
        x=load_data();dates=deep.protocol()["development_selection_dates"]
        train=x.loc[pd.to_datetime(x.endpoint).lt("2020-03-31") & x.decision_date.lt("2020-03-31")]
        dev=x.loc[x.decision_date.isin(dates)]
        base=benchmark_scores(dates)
        configs=[("goal","compact"),("balanced","regularized"),("goal","regularized")]
        rows=[]
        for mode,name in configs:
            print("blend training",mode,name,flush=True)
            model,n,groups=train_model(train,mode,PARAMS[name])
            raw=score(dev,model)
            for w in (0,.25,.50,.67,.80):
                scored=blend_independent_ranker(dev,raw,w)
                a,b,_=compare(dev,scored,base)
                stats=summary(a,b)
                eligible=(not stats["robustness_failed"] and stats["delta_ndcg20"]>=-.01
                    and stats["delta_target_achievement_top20"]>=-.02
                    and stats["delta_median_xirr_top20"]>=-.025
                    and stats["worst_profile_shortfall_delta"]<=.02)
                rows.append({"label":mode,"params":name,"goal_weight":w,"train_rows":n,
                    "train_groups":groups,"eligible":eligible,**stats})
                pd.DataFrame(rows).to_csv(OUT/"development_blend.partial.csv",index=False)
        tournament=pd.DataFrame(rows).sort_values(["eligible","utility"],ascending=[False,False])
        tournament.to_csv(OUT/"development_blend.csv",index=False)
        best=tournament.iloc[0].to_dict()
        write_json(OUT/"selection_lock_v2.json",{"selected":best,"feature_contract_sha256":sha(OUT/"feature_contract.json"),
            "panel_sha256":sha(PANEL),"prepared_sha256":sha(PREP),"development_blend_sha256":sha(OUT/"development_blend.csv"),
            "predecessor_lock_sha256":sha(OUT/"selection_lock.json"),"selection_dates":dates,
            "known_evaluation_not_used_for_selection":True,"model_input_excludes_champion_score":True,
            "eligibility":"coverage, shortfall, drawdown, weekly; NDCG >= -0.01, achievement >= -0.02, median XIRR >= -0.025; worst profile shortfall <= +0.02"})
        print("blend selected",best,flush=True)
        return
    if args.stage == "development_return":
        if (OUT/"selection_lock_v3.json").exists():raise FileExistsError("return extension already locked")
        assert not (OUT/"known_evaluation_scores.csv.gz").exists()
        extension=OUT/"label_extension_return.json"
        if not extension.exists():
            write_json(extension,{"reason":"development median-XIRR regression in balanced/goal/risk variants",
                "return_relevance_weights":LABELS["return"],"planned_parameters":list(PARAMS),
                "planned_goal_weights":[0,.25,.50,.67],"selection_dates":deep.protocol()["development_selection_dates"],
                "postdevelopment_outcomes_used":False})
        x=load_data();dates=deep.protocol()["development_selection_dates"]
        train=x.loc[pd.to_datetime(x.endpoint).lt("2020-03-31") & x.decision_date.lt("2020-03-31")]
        dev=x.loc[x.decision_date.isin(dates)];base=benchmark_scores(dates)
        rows=[]
        for name in PARAMS:
            print("return training",name,flush=True)
            model,n,groups=train_model(train,"return",PARAMS[name])
            raw=score(dev,model)
            for w in (0,.25,.50,.67):
                a,b,_=compare(dev,blend_independent_ranker(dev,raw,w),base)
                stats=summary(a,b)
                eligible=(not stats["robustness_failed"] and stats["delta_ndcg20"]>=-.01
                    and stats["delta_target_achievement_top20"]>=-.02
                    and stats["delta_median_xirr_top20"]>=-.025
                    and stats["worst_profile_shortfall_delta"]<=.02)
                rows.append({"label":"return","params":name,"goal_weight":w,"train_rows":n,
                    "train_groups":groups,"eligible":eligible,**stats})
                pd.DataFrame(rows).to_csv(OUT/"development_return.partial.csv",index=False)
        old=pd.read_csv(OUT/"development_blend.csv")
        tournament=pd.concat([old,pd.DataFrame(rows)],ignore_index=True).sort_values(
            ["eligible","utility"],ascending=[False,False])
        tournament.to_csv(OUT/"development_full.csv",index=False)
        best=tournament.iloc[0].to_dict()
        write_json(OUT/"selection_lock_v3.json",{"selected":best,"feature_contract_sha256":sha(OUT/"feature_contract.json"),
            "panel_sha256":sha(PANEL),"prepared_sha256":sha(PREP),"development_full_sha256":sha(OUT/"development_full.csv"),
            "predecessor_lock_sha256":sha(OUT/"selection_lock_v2.json"),"label_extension_sha256":sha(extension),
            "selection_dates":dates,"known_evaluation_not_used_for_selection":True,"model_input_excludes_champion_score":True,
            "eligibility":"coverage, shortfall, drawdown, weekly; NDCG >= -0.01, achievement >= -0.02, median XIRR >= -0.025; worst profile shortfall <= +0.02"})
        print("final development selected",best,flush=True)
        return
    if args.stage == "final":
        lock = json.loads((OUT / "selection_lock_v3.json").read_text())
        assert sha(OUT / "feature_contract.json") == lock["feature_contract_sha256"]
        x = load_data()
        train = x.loc[pd.to_datetime(x.endpoint).lt("2024-03-31") & x.decision_date.lt("2024-03-31")]
        eval_dates = deep.protocol()["postlock_2024_diagnostics"] + deep.protocol()["untouched_final_dates"] + deep.protocol()["postfinal_2025_diagnostics"]
        target = x.loc[x.decision_date.isin(eval_dates)]
        assert pd.to_datetime(train.endpoint).max() < pd.Timestamp(min(eval_dates))
        choice = lock["selected"]
        model,n,groups = train_model(train, choice["label"], PARAMS[choice["params"]])
        model.booster_.save_model(str(OUT / "lambdarank.txt"))
        scores = blend_independent_ranker(target,score(target,model),choice["goal_weight"])
        scores.to_csv(OUT / "known_evaluation_scores.csv.gz", index=False, compression={"method":"gzip","mtime":0})
        a,b,m = compare(target,scores,benchmark_scores(eval_dates))
        a.to_csv(OUT / "known_evaluation_v14_profiles.csv",index=False)
        b.to_csv(OUT / "known_evaluation_champion_profiles.csv",index=False)
        joined = a.merge(b,on=["decision_date","profile"],suffixes=("_v14","_champion"))
        joined.to_csv(OUT / "known_evaluation_comparison.csv",index=False)
        imp = pd.DataFrame({"feature":FEATURES,"gain":model.booster_.feature_importance("gain"),
            "split":model.booster_.feature_importance("split")}).sort_values("gain",ascending=False)
        imp.to_csv(OUT / "feature_importance.csv",index=False)
        result = summary(a,b)
        result.update({"train_rows":n,"train_groups":groups,"known_evaluation_dates":eval_dates,
                       "verdict":"FROZEN CHAMPION RETAINS" if (not choice["eligible"] or result["robustness_failed"] or result["utility"] <= 0) else "PROMISING CHALLENGER",
                       "promotion_requires_new_unexposed_validation":True})
        write_json(OUT / "decision.json",result)
        print(result,flush=True)
        return
    if args.stage == "current":
        current_inference()
        return
    if args.stage == "manifest":
        external=[PANEL,PREP,ROOT/"research/runners/personalized_v14_ml_20261003.py",
            ROOT/"research/runners/finalize_personalized_v14_ml_20261003.py",
            ROOT/"research/reports/personalized_v14_ml_20261003.md",
            ROOT/"research/freezes/personalized-d499580/manifest.json",
            ROOT/"research/freezes/personalized-d499580/lambdarank.txt",
            ROOT/"research/freezes/personalized-d499580/rankings.csv.gz",
            ROOT/"experiments/professor-current-fallback-20261003/equal-priority-v2/current_company_facts_equal_priority.csv.gz",
            ROOT/"experiments/history-enrichment-20261002/final-data-quality-v3/history_enrichment.csv.gz"]
        files=[p for p in sorted(OUT.rglob("*")) if p.is_file() and p.name!="manifest.json"]+external
        write_json(OUT / "manifest.json", {str(p.relative_to(ROOT)):sha(p) for p in files})


def current_inference():
    """Infer only on frozen current plan rows; professor fills are equal priority."""
    source = ROOT / "research/freezes/personalized-d499580/rankings.csv.gz"
    overlay = ROOT / "experiments/professor-current-fallback-20261003/equal-priority-v2/current_company_facts_equal_priority.csv.gz"
    current_hist = ROOT / "experiments/history-enrichment-20261002/final-data-quality-v3/history_enrichment.csv.gz"
    refreshed_champion = ROOT / "experiments/professor-current-fallback-20261003/champion-data-refresh-research-v1/all_profile_rank_comparison.csv.gz"
    rows = pd.read_csv(source, low_memory=False)
    facts = pd.read_csv(overlay, usecols=["isin","ticker","company","product_baseline_yoy_growth",
        "product_baseline_cagr_3y","product_baseline_cagr_5y","professor_workbook_cagr_7y",
        "professor_workbook_cagr_10y"],low_memory=False)
    history = pd.read_csv(current_hist, usecols=["isin","history_path","adjusted_history_available",
        "history_quality","high_metric_source","risk_metric_source","raw_risk_fallback_used",
        "history_months","history_start_cagr","strict_cagr_1y",
        "days_since_recorded_high","distance_from_recorded_high","distance_from_52w_high",
        "full_history_max_drawdown","current_drawdown_duration_days","max_drawdown_duration_days",
        "recovery_from_worst_trough","realized_volatility_1y","downside_volatility_1y",
        "strict_cagr_5y","cagr_5y_observed","strict_cagr_3y","recorded_high_price"])
    assert facts["isin"].is_unique and history["isin"].is_unique
    extras=current_adjusted_extras(history,"2026-09-18")
    rows = rows.merge(facts,on="isin",how="left",validate="many_to_one").merge(history,on="isin",how="left",validate="many_to_one")
    rows=rows.merge(extras,on="isin",how="left",validate="many_to_one")
    raw_only=rows.history_quality.eq("RAW_RISK_ONLY")|rows.raw_risk_fallback_used.eq(True)
    risk_columns=["days_since_recorded_high","distance_from_recorded_high",
        "distance_from_52w_high","full_history_max_drawdown","current_drawdown_duration_days",
        "max_drawdown_duration_days","recovery_from_worst_trough","realized_volatility_1y",
        "downside_volatility_1y"]
    rows.loc[raw_only,risk_columns]=np.nan
    write_json(OUT/"current_provenance_audit.json",{"raw_risk_only_profile_rows_quarantined":int(raw_only.sum()),
        "raw_risk_only_identities":int(rows.loc[raw_only,"isin"].nunique()),
        "risk_only_raw_values_used_as_model_features":False,"current_adjusted_extras_rows":len(extras)})
    rows["cagr_3y"] = rows.cagr_3y.fillna(rows.product_baseline_cagr_3y).fillna(rows.strict_cagr_3y)
    rows["original_cagr_5y"] = rows.cagr_5y.fillna(rows.product_baseline_cagr_5y)
    rows["observed_cagr_5y"] = rows.strict_cagr_5y
    rows["strict_cagr_1y"] = rows.product_baseline_yoy_growth.fillna(rows.strict_cagr_1y)
    rows["strict_cagr_7y"] = rows.professor_workbook_cagr_7y.fillna(rows.adjusted_cagr_7y)
    rows["strict_cagr_10y"] = rows.professor_workbook_cagr_10y.fillna(rows.adjusted_cagr_10y)
    rows["decision_date"] = rows.decision_date.astype(str)
    rows = add_features(rows)
    model = lgb.Booster(model_file=str(OUT / "lambdarank.txt"))
    assert model.feature_name() == FEATURES
    # Small deterministic current sample; LightGBM's exact TreeSHAP additive
    # contributions are diagnostic only and never influence selection.
    sample=rows.iloc[::20]
    contributions=model.predict(sample[FEATURES],pred_contrib=True)
    pd.DataFrame({"feature":FEATURES,"mean_abs_shap":np.abs(contributions[:,:-1]).mean(axis=0)}).sort_values(
        "mean_abs_shap",ascending=False).to_csv(OUT/"current_shap_importance.csv",index=False)
    lock=json.loads((OUT/"selection_lock_v3.json").read_text())
    pred=blend_independent_ranker(rows,score(rows,model),lock["selected"]["goal_weight"])
    result = rows[KEYS+["profile_name","has_true_5y","history_months","days_since_recorded_high",
        "distance_from_recorded_high","downside_volatility_1y"]].loc[:,~rows[KEYS+["profile_name","has_true_5y","history_months","days_since_recorded_high","distance_from_recorded_high","downside_volatility_1y"]].columns.duplicated()].copy()
    result = result.merge(pred,on=KEYS,validate="one_to_one")
    result = result.merge(facts[["isin","ticker","company"]],on="isin",validate="many_to_one")
    prior=pd.read_csv(refreshed_champion,usecols=KEYS+["new_rank","new_score"])
    result=result.merge(prior.rename(columns={"new_rank":"champion_rank","new_score":"champion_score"}),
        on=KEYS,validate="one_to_one")
    result["rank_change"] = result.champion_rank-result.v14_rank
    result.to_csv(OUT / "current_rankings.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    for n in (20,50,100):
        result.sort_values(["profile_name","v14_rank"]).groupby("profile_name").head(n).to_csv(OUT / f"current_top{n}.csv",index=False)
    result.loc[result["isin"].eq("INE388Y01029")].to_csv(OUT / "nykaa_diagnostic.csv",index=False)
    result.sort_values("rank_change",key=lambda s:s.abs(),ascending=False).head(200).to_csv(OUT / "current_largest_moves.csv",index=False)
    print("current scored",len(result),flush=True)


def current_adjusted_extras(history, cutoff):
    cache=OUT/"current_adjusted_extras.csv.gz"
    if cache.exists():return pd.read_csv(cache)
    day=np.datetime64(cutoff,"D")
    records=[]
    for row in history.itertuples(index=False):
        if not row.adjusted_history_available or not isinstance(row.history_path,str):continue
        path=Path(row.history_path)
        if not path.is_file():continue
        try:
            data=pd.read_csv(path,usecols=["date","adjusted_close"])
            d=pd.to_datetime(data.date,errors="coerce").to_numpy(dtype="datetime64[D]")
            p=pd.to_numeric(data.adjusted_close,errors="coerce").to_numpy(float)
            good=~np.isnat(d)&np.isfinite(p)&(p>0)
            d,p=d[good],p[good]
            k=np.searchsorted(d,day,side="right")
            if k<2 or int((day-d[k-1]).astype(int))>21:continue
            d,p=d[:k],p[:k]
            if np.any(np.diff(d).astype(int)<=0):continue
        except (OSError,ValueError):continue
        values={"isin":row.isin}
        for years in (7,10):
            anchor=np.datetime64((pd.Timestamp(cutoff)-pd.DateOffset(years=years)).date(),"D")
            ix=np.searchsorted(d,anchor,side="right")-1
            good=ix>=0 and 0<=int((anchor-d[ix]).astype(int))<=7 and ix<k-1
            values[f"adjusted_cagr_{years}y"]=(float(np.expm1(np.log(p[-1]/p[ix])*365/int((d[-1]-d[ix]).astype(int)))) if good else np.nan)
        anchor=day-np.timedelta64(183,"D")
        ix=np.searchsorted(d,anchor,side="right")-1
        values["momentum_6m"]=float(p[-1]/p[ix]-1) if ix>=0 and int((anchor-d[ix]).astype(int))<=7 else np.nan
        start=np.searchsorted(d,day-np.timedelta64(365,"D"))
        yp=p[start:]
        values["distance_from_1y_low"]=float(p[-1]/np.min(yp)-1) if len(yp)>1 else np.nan
        returns=np.diff(np.log(yp))
        values["downside_frequency_1y"]=float(np.mean(returns<0)) if len(returns)>5 else np.nan
        records.append(values)
    result=pd.DataFrame(records)
    result.to_csv(cache,index=False,compression={"method":"gzip","mtime":0})
    return result


if __name__ == "__main__":
    main()
