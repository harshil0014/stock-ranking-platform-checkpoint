"""Build and evaluate a fixed, broad, chronological price-model panel."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

CONTROLS = {"PYTHONHASHSEED":"20260730", "OMP_NUM_THREADS":"1", "OPENBLAS_NUM_THREADS":"1",
            "MKL_NUM_THREADS":"1", "NUMEXPR_NUM_THREADS":"1"}
FEATURES = ["mom12_1","mom6_1","reversal1m","mom24m","mom36m","low_vol_6m","low_vol_12m",
            "shallow_drawdown_12m","shallow_drawdown_36m","distance_52w_high","trend_consistency_12m"]


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _index_at_or_before(date_values, target, np, pd, tolerance=20):
    target64 = np.datetime64(pd.Timestamp(target).to_datetime64())
    index = int(np.searchsorted(date_values, target64, side="right") - 1)
    if index < 0 or (pd.Timestamp(target) - pd.Timestamp(date_values[index])).days > tolerance:
        return None
    return index


def _drawdown(values, np):
    peak=np.maximum.accumulate(values)
    return float(np.min(values/peak-1))


def build_panel(state_root: Path, histories: Path, pd, np):
    from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
    loaded=load_company_fact_snapshot(resolve_company_fact_snapshot(state_root))
    facts=loaded.facts.loc[:,["ticker","isin","company","product_sector","listing_date"]].copy()
    facts=facts.dropna(subset=["ticker","isin","product_sector"]).drop_duplicates("isin")
    decisions=pd.date_range("2020-08-31","2025-08-31",freq="ME")
    rows=[]; failures=[]; hashes={}
    for item in facts.sort_values("ticker",kind="stable").itertuples(index=False):
        path=histories/f"{item.ticker}.csv"
        if not path.is_file():
            failures.append({"ticker":item.ticker,"isin":item.isin,"reason":"HISTORY_FILE_MISSING"}); continue
        try:
            raw=path.read_bytes(); h=pd.read_csv(path,usecols=["date","adjusted_close"])
            h.date=pd.to_datetime(h.date,errors="raise"); h.adjusted_close=pd.to_numeric(h.adjusted_close,errors="coerce")
            h=h.dropna().sort_values("date",kind="stable").drop_duplicates("date",keep=False)
            if h.empty or (~np.isfinite(h.adjusted_close) | h.adjusted_close.le(0)).any(): raise ValueError("invalid prices")
            hashes[item.ticker]=sha256(raw).hexdigest()
        except Exception as exc:
            failures.append({"ticker":item.ticker,"isin":item.isin,"reason":f"INVALID_HISTORY:{type(exc).__name__}"}); continue
        date_values=h.date.to_numpy(dtype="datetime64[ns]"); prices=h.adjusted_close.to_numpy(float)
        first=h.date.iloc[0]; listing=pd.to_datetime(item.listing_date,errors="coerce")
        for decision in decisions:
            if first > decision or (pd.notna(listing) and listing > decision): continue
            now=_index_at_or_before(date_values,decision,np,pd)
            anchors={m:_index_at_or_before(date_values,decision-pd.DateOffset(months=m),np,pd) for m in (1,6,12,13,24,36,60)}
            endpoints={m:_index_at_or_before(date_values,decision+pd.DateOffset(months=m),np,pd) for m in (3,6,12)}
            if now is None or any(endpoints[m] is None for m in endpoints): continue
            start12=int(np.searchsorted(date_values,np.datetime64((decision-pd.DateOffset(months=12)).to_datetime64()),side="left"))
            start36=int(np.searchsorted(date_values,np.datetime64((decision-pd.DateOffset(months=36)).to_datetime64()),side="left"))
            window12=prices[start12:now+1]; window36=prices[start36:now+1]
            ret=np.diff(window12)/window12[:-1]
            month_indices=[_index_at_or_before(date_values,decision-pd.DateOffset(months=m),np,pd) for m in range(12,-1,-1)]
            month_prices=np.array([prices[x] for x in month_indices if x is not None],dtype=float)
            def ratio(months):
                a=anchors[months]; return float(prices[now]/prices[a]-1) if a is not None else np.nan
            row={"decision_date":decision.date().isoformat(),"ticker":item.ticker,"isin":item.isin,
                 "company":item.company,"sector":item.product_sector,"price":float(prices[now]),
                 "mom12_1":float(prices[anchors[1]]/prices[anchors[12]]-1) if anchors[1] is not None and anchors[12] is not None else np.nan,
                 "mom6_1":float(prices[anchors[1]]/prices[anchors[6]]-1) if anchors[1] is not None and anchors[6] is not None else np.nan,
                 "reversal1m":-ratio(1),"mom24m":ratio(24),"mom36m":ratio(36),
                 "low_vol_6m":-float(np.std(np.diff(prices[anchors[6]:now+1])/prices[anchors[6]:now],ddof=1)*np.sqrt(252)) if anchors[6] is not None else np.nan,
                 "low_vol_12m":-float(np.std(ret,ddof=1)*np.sqrt(252)),
                 "shallow_drawdown_12m":_drawdown(window12,np),
                 "shallow_drawdown_36m":_drawdown(window36,np),
                 "distance_52w_high":float(prices[now]/window12.max()),
                 "trend_consistency_12m":float((np.diff(month_prices)/month_prices[:-1]>0).mean()) if len(month_prices)>=10 else np.nan,
                 "return_1y":ratio(12),"cagr_3y":(float(prices[now]/prices[anchors[36]])**(1/3)-1) if anchors[36] is not None else np.nan,
                 "cagr_5y":(float(prices[now]/prices[anchors[60]])**(1/5)-1) if anchors[60] is not None else np.nan,
                 "days_since_high":int((decision-pd.Timestamp(date_values[int(np.argmax(prices[:now+1]))])).days),
                 **{f"future_{m}m":float(prices[endpoints[m]]/prices[now]-1) for m in endpoints},
                 **{f"endpoint_{m}m":pd.Timestamp(date_values[endpoints[m]]).date().isoformat() for m in endpoints}}
            rows.append(row)
    panel=pd.DataFrame(rows)
    # Reproduce the immutable Baseline formula on complete rows only.
    complete=panel[["return_1y","cagr_3y","cagr_5y","days_since_high"]].notna().all(axis=1)
    panel["baseline_score"]=np.nan
    blocks=[]
    for _,g in panel.loc[complete].groupby(["decision_date","sector"],sort=True):
        ranks=pd.concat([g.return_1y.rank(ascending=False,method="min"),g.cagr_3y.rank(ascending=False,method="min"),
                         g.cagr_5y.rank(ascending=False,method="min"),g.days_since_high.rank(ascending=True,method="min")],axis=1)
        blocks.append(pd.Series(ranks.mean(axis=1),index=g.index))
    if blocks: panel.loc[complete,"baseline_score"]=pd.concat(blocks).sort_index()
    panel["baseline_signal"]=panel.groupby(["decision_date","sector"])["baseline_score"].rank(ascending=False,pct=True)
    panel["target"]=panel.groupby(["decision_date","sector"])["future_12m"].rank(pct=True)
    return panel, pd.DataFrame(failures), hashes, loaded.manifest


def _metric(frame, column, pd, np):
    rows=[]
    for (date,sector),g in frame.dropna(subset=[column,"future_12m"]).groupby(["decision_date","sector"],sort=True):
        if len(g)<3: continue
        ic=g[column].rank().corr(g.future_12m.rank())
        if np.isfinite(ic): rows.append({"decision_date":date,"sector":sector,"model":column,"peers":len(g),"rank_ic":float(ic)})
    return pd.DataFrame(rows)


def run(state_root:Path,histories:Path,protocol_path:Path,output:Path):
    if output.exists(): raise ValueError("fresh output required")
    if {k:os.environ.get(k) for k in CONTROLS} != CONTROLS: raise ValueError("deterministic controls mismatch")
    if any(k.startswith("MLFLOW_") for k in os.environ): raise ValueError("MLflow environment is forbidden")
    protocol_bytes=protocol_path.read_bytes(); protocol=json.loads(protocol_bytes)
    import numpy as np
    import pandas as pd
    import lightgbm as lgb
    from sklearn.ensemble import ExtraTreesRegressor
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    np.random.seed(20260730)
    panel,failures,history_hashes,manifest=build_panel(state_root,histories,pd,np)
    if panel.empty: raise ValueError("empty broad panel")
    core=["mom12_1","mom6_1","reversal1m","low_vol_6m","low_vol_12m","shallow_drawdown_12m","distance_52w_high","trend_consistency_12m"]
    eligible=panel[core].notna().all(axis=1) & panel.baseline_signal.notna()
    for feature in core:
        panel[feature+"_pct"]=panel.groupby(["decision_date","sector"])[feature].rank(pct=True)
    panel["mom12_1_signal"]=panel.mom12_1_pct; panel["mom6_1_signal"]=panel.mom6_1_pct
    panel["price_multifactor_signal"]=panel[[x+"_pct" for x in core]].mean(axis=1)
    model_predictions=[]; execution=[]
    configs={
      "ridge":lambda: Ridge(alpha=10.0),
      "extra_trees":lambda: ExtraTreesRegressor(n_estimators=200,min_samples_leaf=10,max_features=0.75,n_jobs=1,random_state=20260730),
    }
    lgb_params={"objective":"regression","metric":"l2","verbosity":-1,"learning_rate":.03,"num_leaves":15,
      "max_depth":4,"min_data_in_leaf":20,"feature_fraction":.8,"bagging_fraction":.8,"bagging_freq":1,
      "num_threads":1,"seed":20260730,"feature_fraction_seed":20260730,"bagging_seed":20260730,
      "data_random_seed":20260730,"deterministic":True,"force_col_wise":True}
    prediction_dates=sorted(panel.loc[panel.decision_date.ge("2023-09-01"),"decision_date"].unique())
    for date in prediction_dates:
        cutoff=pd.Timestamp(date); maturity=pd.to_datetime(panel.endpoint_12m)
        train=panel.loc[eligible & pd.to_datetime(panel.decision_date).lt(cutoff) & maturity.lt(cutoff)].copy()
        test=panel.loc[eligible & panel.decision_date.eq(date)].copy()
        if len(train)<100 or test.empty: continue
        xtrain=train[core].to_numpy(float); xtest=test[core].to_numpy(float); y=train.target.to_numpy(float)
        scaler=StandardScaler().fit(xtrain); xs=scaler.transform(xtrain); xt=scaler.transform(xtest)
        for name,factory in configs.items():
            model=factory(); model.fit(xs, y); pred=model.predict(xt)
            model_predictions.extend({"decision_date":date,"ticker":r.ticker,"isin":r.isin,"model":name,"prediction":float(v)} for r,v in zip(test.itertuples(),pred))
        booster=lgb.train(lgb_params,lgb.Dataset(xtrain,label=y),num_boost_round=100)
        pred=booster.predict(xtest)
        model_predictions.extend({"decision_date":date,"ticker":r.ticker,"isin":r.isin,"model":"lightgbm_regression","prediction":float(v)} for r,v in zip(test.itertuples(),pred))
        order=train.sort_values(["decision_date","sector","ticker"],kind="stable"); groups=order.groupby(["decision_date","sector"],sort=False).size().tolist()
        relevance=np.floor(order.target.clip(0,1)*20).astype(int)
        rank_params={**lgb_params,"objective":"lambdarank","metric":"ndcg","label_gain":list(range(21))}
        ranker=lgb.train(rank_params,lgb.Dataset(order[core],label=relevance,group=groups),num_boost_round=100)
        pred=ranker.predict(test[core])
        model_predictions.extend({"decision_date":date,"ticker":r.ticker,"isin":r.isin,"model":"lightgbm_lambdarank","prediction":float(v)} for r,v in zip(test.itertuples(),pred))
        execution.append({"date":date,"training_rows":len(train),"test_rows":len(test),"latest_training_endpoint":str(maturity.loc[train.index].max().date())})
    predictions=pd.DataFrame(model_predictions)
    base=panel.loc[eligible,["decision_date","ticker","isin","sector","future_12m","baseline_signal","mom12_1_signal","mom6_1_signal","price_multifactor_signal"]]
    wide=predictions.pivot(index=["decision_date","ticker","isin"],columns="model",values="prediction").reset_index()
    evaluated=base.merge(wide,on=["decision_date","ticker","isin"],how="left",validate="one_to_one")
    candidates=["mom12_1_signal","mom6_1_signal","price_multifactor_signal","ridge","extra_trees","lightgbm_regression","lightgbm_lambdarank"]
    validation=evaluated.loc[evaluated.decision_date.between("2023-09-01","2024-08-31")]
    validation_scores={c:float(_metric(validation,c,pd,np).rank_ic.mean()) for c in candidates}
    selected=[name for name,value in sorted(validation_scores.items(),key=lambda x:(-x[1],x[0])) if np.isfinite(value) and value>0][:2]
    if not selected: raise ValueError("no positive validation challenger")
    for col in selected:
        evaluated[col+"_ensemble_pct"]=evaluated.groupby(["decision_date","sector"])[col].rank(pct=True)
    evaluated["selected_ensemble"]=evaluated[[c+"_ensemble_pct" for c in selected]].mean(axis=1)
    test=evaluated.loc[evaluated.decision_date.between("2024-09-01","2025-08-31")]
    metric_parts=[]
    for name in ["baseline_signal",*candidates,"selected_ensemble"]:
        metric_parts.append(_metric(test,name,pd,np))
    metrics=pd.concat(metric_parts,ignore_index=True)
    summary_models={m:{"cells":len(g),"mean_rank_ic":float(g.rank_ic.mean()),"median_rank_ic":float(g.rank_ic.median()),
                       "positive_fraction":float(g.rank_ic.gt(0).mean())} for m,g in metrics.groupby("model",sort=True)}
    summary={"schema_version":"broad_chronological_price_ml_result_v1","status":"LOCKED_TEST_COMPLETE",
      "panel_rows":len(panel),"panel_issuers":int(panel["isin"].nunique()),"eligible_rows":int(eligible.sum()),
      "validation_scores":validation_scores,"selected_before_locked_test":selected,"locked_test_models":summary_models,
      "product_default_changed":False,"promotion_permitted":False,
      "limitation":"Current-survivor universe and current sector labels; no delisted-security history. Comparative result is supplementary until prospectively confirmed.",
      "accepted_company_fingerprint":manifest["fingerprint"],"accepted_market_fingerprint":manifest["market_fingerprint"],
      "protocol_sha256":sha256(protocol_bytes).hexdigest(),"history_files":len(history_hashes)}
    output.mkdir(parents=True)
    panel.to_csv(output/"panel.csv",index=False,float_format="%.17g",lineterminator="\n")
    failures.to_csv(output/"history_failures.csv",index=False,lineterminator="\n")
    predictions.to_csv(output/"model_predictions.csv",index=False,float_format="%.17g",lineterminator="\n")
    evaluated.to_csv(output/"evaluated_rows.csv",index=False,float_format="%.17g",lineterminator="\n")
    metrics.to_csv(output/"locked_test_metrics.csv",index=False,float_format="%.17g",lineterminator="\n")
    (output/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    (output/"execution.json").write_text(json.dumps({"controls":CONTROLS,"runs":execution,"history_hashes":history_hashes},indent=2,sort_keys=True)+"\n",encoding="utf-8")
    artifacts=[]
    for path in sorted(output.iterdir()): artifacts.append({"path":path.name,"sha256":_hash(path),"size":path.stat().st_size})
    fp=sha256(json.dumps(artifacts,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
    (output/"manifest.json").write_text(json.dumps({"fingerprint":fp,"artifacts":artifacts},indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return summary|{"fingerprint":fp}


def main():
    p=argparse.ArgumentParser(); p.add_argument("--output",type=Path,required=True)
    p.add_argument("--state-root",type=Path,default=ROOT/"data/company_facts")
    p.add_argument("--history-root",type=Path,default=ROOT/"data/live_market/history_cache")
    p.add_argument("--protocol",type=Path,default=ROOT/"research/specifications/broad_chronological_price_ml_v1.json")
    a=p.parse_args(); print(json.dumps(run(a.state_root,a.history_root,a.protocol,a.output),sort_keys=True))
if __name__=="__main__": main()
