"""Isolated retrospective experiment; never strict PIT or production evidence.

User-authorized vendor restatement risk is accepted here only. Screener values
retain their actual observation time alongside the official financial-period
clock. No current value is labelled as originally published.
"""
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd

from stock_ranker.screener_historical_fundamentals import official_clock_from_availability

FEATURES = ["derived_net_margin", "derived_debt_to_equity",
            "derived_roe_closing_equity", "derived_cfo_to_assets"]
RISK = "VENDOR_RESTATEMENT_RISK_ACCEPTED_NOT_STRICT_PIT"


def select_features(observations, clocks, dates):
    """Select newest public filing BEFORE testing feature completeness."""
    keys = ["isin", "period_end", "feature"]
    obs = observations.copy()
    obs["period_end"] = pd.to_datetime(obs.period_end).dt.strftime("%Y-%m-%d")
    conflict = obs.groupby(keys).value.nunique().gt(1)
    bad = conflict[conflict].reset_index()[keys]
    obs = obs.merge(bad.assign(conflict=True), on=keys, how="left")
    obs = obs.loc[obs.conflict.isna()].drop(columns="conflict")
    obs = obs.sort_values([*keys, "available_at", "source_hash"], kind="stable").drop_duplicates(keys, keep="last")
    clock = clocks.copy()
    clock["period_end"] = pd.to_datetime(clock.period_end, utc=True).dt.strftime("%Y-%m-%d")
    clock["official_available_at"] = pd.to_datetime(clock.official_available_at, utc=True)
    rows = []
    for date in sorted(dates):
        cutoff = pd.Timestamp(date, tz="Asia/Kolkata") + pd.Timedelta(hours=15, minutes=30)
        chosen = clock.loc[clock.official_available_at.le(cutoff) & clock.period_end.le(date)]
        chosen = chosen.sort_values(["period_end", "official_available_at", "filing_id"], kind="stable").drop_duplicates("isin", keep="last")
        joined = chosen.merge(obs, on=["isin", "period_end"], how="left", validate="one_to_many")
        joined["ranking_date"] = date
        joined["research_status"] = RISK
        rows.append(joined)
    return pd.concat(rows, ignore_index=True), bad


def test_models(panel, outcomes):
    """Fixed factors and alpha=1 ridge, train-only scaling, matured labels only."""
    keys = ["ranking_date", "isin", "ticker"]
    labels = outcomes.loc[outcomes.horizon_months.eq(12), keys + ["future_adjusted_return", "actual_endpoint_date"]]
    data = panel.merge(labels, on=keys, validate="one_to_one")
    if len(data) != len(panel):
        raise ValueError("missing exact outcome identity")
    if not np.isfinite(data.future_adjusted_return).all():
        raise ValueError("nonfinite outcome")
    data["maturity"] = pd.to_datetime(data.actual_endpoint_date)
    if data.maturity.le(pd.to_datetime(data.ranking_date)).any():
        raise ValueError("outcome is not future dated")
    data["maturity"] = data.groupby(["ranking_date", "sector"]).maturity.transform("max")
    data["target"] = data.groupby(["ranking_date", "sector"]).future_adjusted_return.rank(pct=True)
    data["ridge"] = np.nan
    data["training_rows"] = 0
    data["latest_training_endpoint"] = ""
    columns = FEATURES + ["mom12m_signal"]
    for date in sorted(data.ranking_date.unique()):
        train = data.loc[data.ranking_date.lt(date) & data.maturity.lt(pd.Timestamp(date))]
        mask = data.ranking_date.eq(date)
        if len(train) < 3:
            continue
        x = train[columns].to_numpy(float)
        mu, scale = x.mean(0), x.std(0)
        scale[scale == 0] = 1
        design = np.column_stack([np.ones(len(x)), (x-mu)/scale])
        penalty = np.eye(design.shape[1]); penalty[0, 0] = 0
        beta = np.linalg.solve(design.T @ design + penalty, design.T @ train.target.to_numpy())
        data.loc[mask, "ridge"] = np.column_stack([np.ones(mask.sum()), (data.loc[mask, columns]-mu)/scale]) @ beta
        data.loc[mask, "training_rows"] = len(train)
        data.loc[mask, "latest_training_endpoint"] = train.maturity.max().date().isoformat()
    metrics = []
    models = ["baseline_signal", "research_v2_signal", "mom12m_signal", "quality", "quality_momentum", "ridge"]
    for (date, sector), group in data.groupby(["ranking_date", "sector"], sort=True):
        if len(group) < 3:
            continue
        for model in models:
            if group[model].isna().any():
                continue
            a, b = group[model].rank(), group.future_adjusted_return.rank()
            ic = float(a.corr(b)) if a.nunique() > 1 and b.nunique() > 1 else None
            metrics.append(dict(ranking_date=date, sector=sector, model=model, peers=len(group), rank_ic=ic))
    return data, pd.DataFrame(metrics)


def run(output):
    root = Path(__file__).resolve().parents[2]
    dest = Path(output)
    if dest.exists():
        raise ValueError("fresh output required")
    sources = {
        "observations": root / "data/analysis/vendor_financial_features_v2_run_01/observations.csv",
        "clocks": root / "data/marketdata/screener-historical-targeted-prep-run-02-20260902/augmented_official_availability.csv",
        "membership": root / "data/walk_forward/screener_historical_readiness_v1_targeted_run_04/cohort_membership.csv",
        "signals": root / "data/walk_forward/exploratory_model_benchmark_v3_run_03/signals.csv",
        "outcomes": root / "data/walk_forward/screener_historical_evaluation_v1_run_04/future_returns.csv",
    }
    def digest(p):
        with p.open("rb") as stream:
            import hashlib
            return hashlib.file_digest(stream, "sha256").hexdigest()
    hashes = {k: digest(p) for k,p in sources.items()}
    obs = pd.read_csv(sources["observations"])
    clocks = official_clock_from_availability(pd.read_csv(sources["clocks"]))
    member = pd.read_csv(sources["membership"])
    dates = sorted(member.ranking_date.unique())
    selected, conflicts = select_features(obs, clocks, dates)
    subset = selected.loc[selected.feature.isin(FEATURES)]
    wide = subset.pivot(index=["ranking_date", "isin"], columns="feature", values="value").reindex(columns=FEATURES).reset_index()
    candidates = member.merge(wide, on=["ranking_date", "isin"], how="left", validate="one_to_one")
    exclusions = candidates.loc[candidates[FEATURES].isna().any(axis=1)].copy()
    exclusions["reason"] = "MISSING_LATEST_OFFICIAL_PERIOD_OR_REQUIRED_SCREENER_COMPONENT"
    panel = candidates.dropna(subset=FEATURES).copy()
    signals = pd.read_csv(sources["signals"])
    panel = panel.merge(signals[["ranking_date", "isin", "ticker", "baseline_signal", "research_v2_signal", "mom12m_signal"]], on=["ranking_date", "isin", "ticker"], validate="one_to_one")
    # Common complete-case sector cohorts for every model, no zero-fill.
    groups = panel.groupby(["ranking_date", "sector"])
    ranks = groups[FEATURES].rank(pct=True)
    ranks["derived_debt_to_equity"] = groups.derived_debt_to_equity.rank(pct=True, ascending=False)
    panel["quality"] = ranks.mean(axis=1)
    panel["quality_momentum"] = (panel.quality + groups.mom12m_signal.rank(pct=True)) / 2
    contract = dict(status=RISK, features=FEATURES, ridge_alpha=1, imputation=False,
                    source_preference="SCREENER", conflicts="QUARANTINE", promotion_allowed=False,
                    outcome_status="PREVIOUSLY_REVEALED_NOT_UNSEEN", input_hashes=hashes)
    dest.mkdir(parents=True)
    (dest/"contract.json").write_text(json.dumps(contract, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    # The experiment specification and selected features exist before label loading.
    panel.to_csv(dest/"features.csv", index=False, float_format="%.17g", lineterminator="\n")
    predictions, metrics = test_models(panel, pd.read_csv(sources["outcomes"]))
    for name,frame in [("all_clocked_observations",selected), ("conflicts",conflicts),
                       ("exclusions",exclusions), ("predictions",predictions), ("metrics",metrics)]:
        frame.to_csv(dest/f"{name}.csv", index=False, float_format="%.17g", lineterminator="\n")
    results = {}
    for model,g in metrics.groupby("model"):
        valid = g.dropna(subset=["rank_ic"])
        results[model] = {"valid_cells":len(valid), "mean_rank_ic":float(valid.rank_ic.mean()) if len(valid) else None}
    summary = dict(status=RISK, model_results=results, selected_company_dates=len(panel), excluded_company_dates=len(exclusions),
                   broad_clocked_issuers=int(selected.loc[selected.value.notna(),"isin"].nunique()),
                   broad_clocked_company_dates=int(selected.loc[selected.value.notna(),["ranking_date","isin"]].drop_duplicates().shape[0]),
                   cohort_by_date=panel.groupby("ranking_date").size().to_dict(),
                   product_default_changed=False, strict_pit_additions=0,
                   warning="Small, revealed cohort; vendor restatement and selection risk; not promotion evidence")
    # Ridge and comparators must be compared on identical cells.
    pivot = metrics.pivot(index=["ranking_date","sector"], columns="model", values="rank_ic")
    summary["ridge_paired_deltas"] = {}
    if "ridge" in pivot:
        for other in ["baseline_signal","research_v2_signal","mom12m_signal"]:
            pair = pivot[["ridge",other]].dropna()
            summary["ridge_paired_deltas"][other] = dict(cells=len(pair), mean_delta=float((pair.ridge-pair[other]).mean()) if len(pair) else None)
    if hashes != {k:digest(p) for k,p in sources.items()}:
        raise ValueError("inputs changed during experiment")
    summary["artifact_hashes"] = {p.name:digest(p) for p in sorted(dest.iterdir())}
    summary["fingerprint"] = sha256(json.dumps(summary,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    (dest/"summary.json").write_text(json.dumps(summary,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return summary
