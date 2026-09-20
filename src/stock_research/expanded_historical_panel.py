"""Largest local historical NIFTY panel; supplementary, outcome-revealed evidence."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd

from stock_ranker.research_v2 import ResearchV2Inputs, calculate_research_v2
from stock_ranker.screener_data_bundle import load_accepted_screener_data_bundle
from stock_ranker.screener_historical_fundamentals import official_clock_from_availability
from stock_ranker.v2_config import ResearchV2Config
from stock_research.exploratory_benchmark import strict_price_factors
from stock_research.vendor_risk_experiment import FEATURES, RISK, select_features

DATES = ("2022-08-05", "2023-08-07", "2024-08-07", "2025-08-07")
GROUPS = {
    "profit_margin": ["derived_net_margin"],
    "profitability": ["derived_net_margin", "derived_roe_closing_equity"],
    "quality_leverage": ["derived_net_margin", "derived_roe_closing_equity", "derived_debt_to_equity"],
    "quality_full": FEATURES,
}


def _hash(path: Path) -> str:
    with path.open("rb") as stream:
        import hashlib
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _identity_map(path: Path) -> tuple[dict[str, dict], set[str]]:
    frame = pd.read_csv(path)
    frame = frame.loc[frame.screener_exact_isin_match.astype(str).str.lower().eq("true")]
    frame.reference_nse_code = frame.reference_nse_code.fillna("").astype(str).str.strip().str.upper()
    pairs = frame.loc[frame.reference_nse_code.ne(""), ["reference_nse_code", "isin", "company"]].drop_duplicates()
    ambiguous = set(pairs.groupby("reference_nse_code").isin.nunique().loc[lambda x: x.gt(1)].index)
    pairs = pairs.loc[~pairs.reference_nse_code.isin(ambiguous)].drop_duplicates("reference_nse_code")
    return pairs.set_index("reference_nse_code").to_dict("index"), ambiguous


def build_membership(blind: Path, identity_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    identities, ambiguous = _identity_map(identity_path)
    rows, rejected = [], []
    for date in DATES:
        root = blind / date
        universe = pd.read_csv(root / "historical_universe.csv", dtype=str)
        universe = universe.loc[universe.investable.astype(str).str.lower().eq("true")]
        baseline = pd.read_csv(root / "baseline_full.csv").drop_duplicates("ticker").set_index("ticker")
        prices = pd.read_csv(root / "predictor_prices.csv", usecols=["ticker", "date", "pit_adjusted_price"])
        for record in universe.sort_values("historical_symbol", kind="stable").to_dict("records"):
            ticker = str(record["historical_symbol"]).upper()
            reasons = []
            if ticker in ambiguous or ticker not in identities:
                reasons.append("NO_UNAMBIGUOUS_EXACT_ISIN_FOR_HISTORICAL_SYMBOL")
            ticker_prices = prices.loc[prices.ticker.astype(str).eq(ticker), ["date", "pit_adjusted_price"]].rename(columns={"pit_adjusted_price":"adjusted_close"})
            try:
                factors = strict_price_factors(ticker_prices, date)
            except ValueError as exc:
                reasons.append("PRICE_FACTOR_UNAVAILABLE: " + str(exc))
                factors = {}
            if reasons:
                rejected.append({"ranking_date":date,"ticker":ticker,"stage":"BASE_PANEL","reason":"; ".join(reasons)})
                continue
            ident = identities[ticker]
            if ticker in baseline.index:
                baseline_score=float(baseline.loc[ticker].baseline_score)
                baseline_rank=float(baseline.loc[ticker].sector_rank)
            else:
                baseline_score=baseline_rank=np.nan
                rejected.append({"ranking_date":date,"ticker":ticker,"stage":"MODEL_INPUT","reason":"BASELINE_UNAVAILABLE"})
            rows.append({"ranking_date":date,"ticker":ticker,"isin":ident["isin"],"company":record["company"],
                         "sector":record["historical_sector"],"baseline_score":baseline_score,
                         "baseline_sector_rank":baseline_rank,**factors})
    return pd.DataFrame(rows), pd.DataFrame(rejected)


def _vendor_observations(root: Path) -> pd.DataFrame:
    use = ["isin","period_end","feature","value","available_at","source_hash"]
    parts = []
    for chunk in pd.read_csv(root / "data/analysis/vendor_financial_features_v2_run_01/observations.csv", usecols=use, chunksize=100000):
        keep = chunk.feature.isin([*FEATURES,"annual_pat"])
        if keep.any(): parts.append(chunk.loc[keep])
    raw = pd.concat(parts, ignore_index=True)
    pat=_derive_pat_growth(raw.loc[raw.feature.eq("annual_pat")])
    raw=pd.concat([raw.loc[raw.feature.ne("annual_pat")],pat],ignore_index=True)
    bundle = load_accepted_screener_data_bundle(root / "data/company_facts/providers/screener_bundle/accepted_state.json")
    direct = bundle.normalized_history.copy()
    rows = []
    for feature, source in [("reported_roce","roce"),("reported_debt_to_equity","debt_to_equity"),
                            ("reported_profit_growth_yoy","profit_growth_yoy")]:
        block = direct[["isin","period_end",source,"source_observed_at","source_workbook_sha256"]].rename(
            columns={source:"value","source_observed_at":"available_at","source_workbook_sha256":"source_hash"})
        block["feature"] = feature
        rows.append(block.dropna(subset=["value"]))
    return pd.concat([raw,*rows], ignore_index=True)


def _derive_pat_growth(pat: pd.DataFrame) -> pd.DataFrame:
    """Derive YoY growth only within one workbook and consecutive annual periods."""
    use=["isin","period_end","feature","value","available_at","source_hash"]
    pat=pat.sort_values(["isin","source_hash","period_end"],kind="stable").copy()
    grouped=pat.groupby(["isin","source_hash"],sort=True)
    pat["prior_pat"]=grouped.value.shift(1)
    pat["prior_period"]=grouped.period_end.shift(1)
    gap=(pd.to_datetime(pat.period_end)-pd.to_datetime(pat.prior_period)).dt.days
    growth=pat.loc[gap.between(300,430)&pat.prior_pat.ne(0)].copy()
    growth["value"]=growth.value/growth.prior_pat-1
    growth["feature"]="screener_profit_growth_yoy"
    return growth[use]


def _outcomes(base: pd.DataFrame, histories: Path) -> tuple[pd.DataFrame,pd.DataFrame,dict]:
    rows, rejected, hashes = [], [], {}
    for record in base.sort_values(["ranking_date","ticker"]).to_dict("records"):
        path = histories / f"{record['ticker']}.csv"
        try:
            digest = _hash(path); history = pd.read_csv(path, usecols=["date","adjusted_close"])
            history.date = pd.to_datetime(history.date, errors="raise")
            history.adjusted_close = pd.to_numeric(history.adjusted_close, errors="coerce")
            if history.date.duplicated().any() or (~np.isfinite(history.adjusted_close) | history.adjusted_close.le(0)).any():
                raise ValueError("invalid or duplicate adjusted history")
            start = pd.Timestamp(record["ranking_date"]); target = start + pd.DateOffset(months=12)
            first = history.loc[history.date.eq(start)]
            end = history.loc[history.date.le(target)].sort_values("date").tail(1)
            if len(first)!=1 or len(end)!=1 or end.iloc[0].date < start: raise ValueError("outcome endpoint unavailable")
            rows.append({"ranking_date":record["ranking_date"],"ticker":record["ticker"],"isin":record["isin"],
                         "actual_endpoint_date":end.iloc[0].date.date().isoformat(),
                         "future_adjusted_return":float(end.iloc[0].adjusted_close/first.iloc[0].adjusted_close-1)})
            hashes[path.name]=digest
        except (OSError,ValueError) as exc:
            rejected.append({"ranking_date":record["ranking_date"],"ticker":record["ticker"],"stage":"OUTCOME","reason":str(exc)})
    return pd.DataFrame(rows), pd.DataFrame(rejected), hashes


def _factor_score(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    ranks=[]
    for col in columns:
        ascending = col == "derived_debt_to_equity"
        ranks.append(frame.groupby(["ranking_date","sector"])[col].rank(pct=True,ascending=not ascending))
    return pd.concat(ranks,axis=1).mean(axis=1,skipna=False)


def _metrics(panel: pd.DataFrame, model: str, signal: str) -> pd.DataFrame:
    rows=[]
    for (date,sector), g in panel.dropna(subset=[signal]).groupby(["ranking_date","sector"],sort=True):
        if len(g)<3: continue
        x,y=g[signal].rank(),g.future_adjusted_return.rank()
        if x.nunique()>1 and y.nunique()>1:
            rows.append({"ranking_date":date,"sector":sector,"model":model,"peers":len(g),"rank_ic":float(x.corr(y))})
    return pd.DataFrame(rows)


def run(output: str|Path) -> dict:
    root=Path(__file__).resolve().parents[2]; dest=Path(output)
    if dest.exists(): raise ValueError("fresh output required")
    blind=root/"data/walk_forward/blind_predictions_v1_run_01"
    identity=root/"data/marketdata/screener-premium-reference-20260831/identity_matches.csv"
    availability=root/"data/marketdata/screener-historical-targeted-prep-run-02-20260902/augmented_official_availability.csv"
    protected=[identity,availability,root/"data/company_facts/providers/screener_bundle/accepted_state.json",
               root/"data/analysis/vendor_financial_features_v2_run_01/observations.csv"]
    for date in DATES:
        protected.extend([blind/date/"historical_universe.csv",blind/date/"baseline_full.csv",blind/date/"predictor_prices.csv"])
    protected_hashes={p.relative_to(root).as_posix():_hash(p) for p in protected}
    base, losses=build_membership(blind,identity)
    outcome,outcome_losses,history_hashes=_outcomes(base,root/"data/live_market/history_cache")
    base=base.merge(outcome,on=["ranking_date","ticker","isin"],validate="one_to_one")
    clocks=official_clock_from_availability(pd.read_csv(availability))
    selected, conflicts=select_features(_vendor_observations(root),clocks,DATES)
    wide=selected.pivot(index=["ranking_date","isin"],columns="feature",values="value").reset_index()
    clock_meta=selected[["ranking_date","isin","period_end","official_available_at"]].drop_duplicates()
    if clock_meta.duplicated(["ranking_date","isin"]).any():
        raise ValueError("selected vendor period is not unique per company-date")
    wide=wide.merge(clock_meta,on=["ranking_date","isin"],validate="one_to_one")
    panel=base.merge(wide,on=["ranking_date","isin"],how="left",validate="one_to_one")
    clock_keys=set(map(tuple,selected[["ranking_date","isin"]].drop_duplicates().to_numpy()))
    feature_gaps=[]
    for row in panel.to_dict("records"):
        key=(row["ranking_date"],row["isin"])
        for group,columns in GROUPS.items():
            missing=[name for name in columns if pd.isna(row.get(name))]
            if missing:
                reason=("NO_VERIFIED_OFFICIAL_PERIOD_CLOCK" if key not in clock_keys else
                        "MISSING_SAME_PERIOD_WORKBOOK_COMPONENTS")
                feature_gaps.append({"ranking_date":row["ranking_date"],"ticker":row["ticker"],"isin":row["isin"],
                                     "feature_group":group,"missing_features":"|".join(missing),"reason":reason})
    # Baseline score/rank is lower-is-better; canonical signals are higher-is-better.
    panel["baseline_signal"]=panel.groupby(["ranking_date","sector"]).baseline_score.rank(
        pct=True, ascending=False
    )
    panel["momentum_signal"]=panel.groupby(["ranking_date","sector"]).mom12m.rank(pct=True)
    baseline_complete = panel["baseline_signal"].notna()
    metrics=[
        _metrics(panel,"baseline","baseline_signal"),
        _metrics(panel,"mom12m","momentum_signal"),
        _metrics(panel.loc[baseline_complete],"mom12m_on_baseline","momentum_signal"),
    ]
    coverage=[]
    for name,columns in GROUPS.items():
        complete=panel[columns].notna().all(axis=1); signal=name+"_signal"
        panel[signal]=np.nan; panel.loc[complete,signal]=_factor_score(panel.loc[complete],columns)
        metrics.append(_metrics(panel,name,signal))
        metrics.append(_metrics(panel.loc[complete],"baseline_on_"+name,"baseline_signal"))
        blend=name+"_momentum_signal"; panel[blend]=np.nan
        panel.loc[complete,blend]=(panel.loc[complete,signal]+panel.loc[complete,"momentum_signal"])/2
        metrics.append(_metrics(panel,name+"_momentum",blend))
        metrics.append(_metrics(panel.loc[complete],"baseline_on_"+name+"_momentum","baseline_signal"))
        coverage.append({"feature_group":name,"required_features":"|".join(columns),"company_dates":int(complete.sum()),
                         "issuers":int(panel.loc[complete,"isin"].nunique())})
    # Existing V2 engine, unchanged, on direct Screener values and official period clocks.
    vendor_v2=[]
    for date in DATES:
        d=panel.loc[panel.ranking_date.eq(date)]
        fundamentals=d[["ticker","period_end","official_available_at","reported_roce","reported_debt_to_equity","screener_profit_growth_yoy"]].rename(
            columns={"official_available_at":"available_date","reported_roce":"roce","reported_debt_to_equity":"debt_to_equity","screener_profit_growth_yoy":"profit_growth_yoy"}).dropna()
        fundamentals["available_date"]=pd.to_datetime(fundamentals.available_date,utc=True).dt.strftime("%Y-%m-%d")
        prices=pd.read_csv(blind/date/"predictor_prices.csv",usecols=["ticker","date","pit_adjusted_price"]).rename(columns={"pit_adjusted_price":"adjusted_close"})
        universe=d[["ticker","company","sector"]]
        result=calculate_research_v2(ResearchV2Inputs(universe,prices,fundamentals),ResearchV2Config(ranking_date=pd.Timestamp(date).date()))
        ranked=result.rankings[["ticker","research_v2_score"]].copy(); ranked["ranking_date"]=date
        vendor_v2.append(ranked)
    vendor_v2=pd.concat(vendor_v2,ignore_index=True)
    panel=panel.merge(vendor_v2,on=["ranking_date","ticker"],how="left",validate="one_to_one")
    panel["vendor_v2_signal"]=panel.groupby(["ranking_date","sector"]).research_v2_score.rank(pct=True)
    metrics.append(_metrics(panel,"vendor_risk_v2","vendor_v2_signal"))
    metrics.append(_metrics(panel.loc[panel.vendor_v2_signal.notna()],"baseline_on_vendor_risk_v2","baseline_signal"))
    metrics=pd.concat(metrics,ignore_index=True)
    # Fixed ridge on the broadest two accounting features plus momentum.
    ridge_features=GROUPS["profitability"]+["mom12m"]
    eligible=panel[ridge_features].notna().all(axis=1); panel["ridge_signal"]=np.nan
    panel["target"]=panel.groupby(["ranking_date","sector"]).future_adjusted_return.rank(pct=True)
    panel["maturity"]=pd.to_datetime(panel.actual_endpoint_date)
    panel["maturity"]=panel.groupby(["ranking_date","sector"]).maturity.transform("max")
    for date in DATES:
        train=panel.loc[eligible & panel.ranking_date.lt(date) & panel.maturity.lt(pd.Timestamp(date))]
        test=panel.loc[eligible & panel.ranking_date.eq(date)]
        if len(train)<3: continue
        x=train[ridge_features].to_numpy(float); mu=x.mean(0); scale=x.std(0); scale[scale==0]=1
        design=np.column_stack([np.ones(len(x)),(x-mu)/scale]); penalty=np.eye(design.shape[1]);penalty[0,0]=0
        beta=np.linalg.solve(design.T@design+penalty,design.T@train.target.to_numpy())
        panel.loc[test.index,"ridge_signal"]=np.column_stack([np.ones(len(test)),(test[ridge_features]-mu)/scale])@beta
    metrics=pd.concat([metrics,_metrics(panel,"ridge_profitability_momentum","ridge_signal"),
                       _metrics(panel.loc[panel.ridge_signal.notna()],"baseline_on_ridge_profitability_momentum","baseline_signal")],ignore_index=True)
    losses=pd.concat([losses,outcome_losses],ignore_index=True)
    dest.mkdir(parents=True)
    gaps=pd.DataFrame(feature_gaps)
    for name,frame in [("panel",panel),("coverage",pd.DataFrame(coverage)),("losses",losses),("feature_gaps",gaps),("conflicts",conflicts),("metrics",metrics)]:
        frame.to_csv(dest/f"{name}.csv",index=False,float_format="%.17g",lineterminator="\n")
    results={m:{"valid_sector_dates":len(g),"mean_rank_ic":float(g.rank_ic.mean())} for m,g in metrics.groupby("model")}
    summary={"status":RISK,"membership_slots":200,"base_company_dates":len(base),"base_by_date":base.groupby("ranking_date").size().to_dict(),
             "losses":len(losses),"losses_by_stage":losses.stage.value_counts().sort_index().to_dict(),
             "feature_group_coverage":coverage,
             "full_quality_gap_reasons":gaps.loc[gaps.feature_group.eq("quality_full")].reason.value_counts().sort_index().to_dict(),
             "model_results":results,"strict_pit_additions":0,
             "product_default_changed":False,"vendor_v2_formula_changed":False,"outcome_status":"PREVIOUSLY_REVEALED_NOT_UNSEEN",
             "input_hashes":{**protected_hashes,**history_hashes}}
    if protected_hashes!={p.relative_to(root).as_posix():_hash(p) for p in protected}:
        raise ValueError("protected input changed during panel construction")
    for name,digest in history_hashes.items():
        if _hash(root/"data/live_market/history_cache"/name)!=digest:
            raise ValueError("outcome history changed during panel construction")
    summary["artifacts"]={p.name:_hash(p) for p in sorted(dest.glob("*.csv"))}
    summary["fingerprint"]=sha256(json.dumps(summary,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    (dest/"summary.json").write_text(json.dumps(summary,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return summary
