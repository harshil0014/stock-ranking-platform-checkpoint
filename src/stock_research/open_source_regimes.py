"""Causal adapters for the preregistered open-source regime tournament.

The estimators live in their upstream packages.  This module only prepares the
research authors' example features, enforces the temporal boundary, and joins
the resulting market context to the existing stock-ranking panel.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


BASE_FEATURES = [
    "enhanced_carry_xirr_score", "enhanced_goal_score", "price_drawdown",
    "cagr_3y", "cagr_5y", "cash_utilization", "unaffordable_rate",
]
FROZEN_CONTROL_GOAL_SHORTFALL = 0.07627221047547905


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_yahoo_close(path: str | Path, cutoff: str) -> pd.Series:
    """Load a yfinance CSV without silently filling missing prices."""
    raw = pd.read_csv(path, header=[0, 1], index_col=0, parse_dates=True)
    close = raw["Close"].iloc[:, 0].rename("close")
    close.index = pd.to_datetime(close.index, errors="raise").tz_localize(None)
    close = pd.to_numeric(close, errors="raise").sort_index()
    close = close.loc[~close.index.duplicated(keep="last")]
    close = close.loc[close.index <= pd.Timestamp(cutoff)].dropna()
    if len(close) < 1000 or (close <= 0).any() or close.index.max() > pd.Timestamp(cutoff):
        raise ValueError("invalid or post-cutoff market history")
    return close


def author_example_features(returns: pd.Series) -> pd.DataFrame:
    """Exact v0 feature recipe from jump-models examples/nasdaq/feature.py."""
    values: dict[str, pd.Series] = {}
    for half_life in (5, 20, 60):
        ewm_return = returns.ewm(halflife=half_life).mean()
        downside = np.minimum(returns, 0.0).pow(2).ewm(halflife=half_life).mean().pow(0.5)
        values[f"ret_{half_life}"] = ewm_return
        values[f"DD-log_{half_life}"] = np.log(downside)
        values[f"sortino_{half_life}"] = ewm_return.div(downside)
    frame = pd.DataFrame(values).replace([np.inf, -np.inf], np.nan).dropna()
    if frame.empty:
        raise ValueError("market feature engineering produced no complete rows")
    return frame


@dataclass(frozen=True)
class RegimeResult:
    snapshots: pd.DataFrame
    daily: pd.DataFrame
    audit: dict


def _last_on_or_before(frame: pd.DataFrame, date: str | pd.Timestamp) -> pd.Series:
    eligible = frame.loc[frame.index <= pd.Timestamp(date)]
    if eligible.empty:
        raise ValueError(f"no market state available by {date}")
    return eligible.iloc[-1]


def fit_causal_regimes(close: pd.Series, decision_dates: Iterable[str], *,
                       calibration_start: str = "2010-01-01",
                       calibration_end: str = "2015-12-31",
                       online_start: str = "2016-01-01",
                       seed: int = 20260923) -> RegimeResult:
    """Fit upstream systems once, then infer only from expanding past prefixes."""
    from hmmlearn.hmm import GaussianHMM
    from jumpmodels.jump import JumpModel
    from jumpmodels.preprocess import DataClipperStd, StandardScalerPD
    from river.drift import ADWIN
    from sklearn.mixture import GaussianMixture

    returns = close.pct_change(fill_method=None).dropna().rename("market_return")
    features = author_example_features(returns)
    train = features.loc[calibration_start:calibration_end]
    online = features.loc[online_start:]
    if train.empty or online.empty or train.index.max() > pd.Timestamp(calibration_end):
        raise ValueError("invalid causal market partition")

    clipper = DataClipperStd(mul=3.0)
    scaler = StandardScalerPD()
    train_x = scaler.fit_transform(clipper.fit_transform(train))
    online_x = scaler.transform(clipper.transform(online))

    jump = JumpModel(n_components=2, jump_penalty=50.0, cont=False)
    jump.fit(train_x, returns.loc[train_x.index], sort_by="cumret")
    jump_state = pd.Series(
        np.asarray(jump.predict_online(online_x), dtype=int),
        index=online.index, name="jump_bear_state",
    )

    vol_column = "DD-log_20"
    vol = GaussianMixture(n_components=2, covariance_type="full", n_init=10, random_state=seed)
    vol.fit(train_x[[vol_column]])
    high_vol_component = int(np.argmax(vol.means_.reshape(-1)))
    vol_probability = pd.Series(
        vol.predict_proba(online_x[[vol_column]])[:, high_vol_component],
        index=online.index, name="vol_high_probability",
    )

    hmm = GaussianHMM(n_components=2, covariance_type="diag", n_iter=200, tol=0.01,
                      random_state=seed)
    hmm.fit(np.asarray(train_x, dtype=float))
    train_post = hmm.predict_proba(np.asarray(train_x, dtype=float))
    weighted_return = np.array([
        np.average(returns.loc[train_x.index], weights=train_post[:, state])
        for state in range(2)
    ])
    hmm_bear_component = int(np.argmin(weighted_return))

    adwin = ADWIN(delta=0.002, clock=32, max_buckets=5, min_window_length=5, grace_period=10)
    adwin_rows = []
    for day, value in returns.loc[calibration_start:].items():
        adwin.update(abs(float(value)))
        adwin_rows.append({
            "date": day, "adwin_estimation": float(adwin.estimation),
            "adwin_variance": float(adwin.variance), "adwin_width": float(adwin.width),
            "adwin_drift_count": int(adwin.n_detections),
            "adwin_drift_detected": int(adwin.drift_detected),
        })
    adwin_daily = pd.DataFrame(adwin_rows).set_index("date")

    # hmmlearn returns smoothed posteriors for a sequence.  At the last row of
    # each truncated prefix there is no future observation, so that row is the
    # causal filtered posterior needed at the decision date.
    snapshots = []
    for requested in sorted({pd.Timestamp(value).normalize() for value in decision_dates}):
        prefix = online_x.loc[online_x.index <= requested]
        if prefix.empty:
            raise ValueError(f"decision {requested.date()} predates online inference")
        observed = prefix.index[-1]
        hmm_probability = float(
            hmm.predict_proba(np.asarray(prefix, dtype=float))[-1, hmm_bear_component]
        )
        adwin_row = _last_on_or_before(adwin_daily, requested)
        snapshots.append({
            "decision_date": requested.date().isoformat(),
            "market_observation_date": observed.date().isoformat(),
            "jump_bear_state": int(jump_state.loc[observed]),
            "vol_high_probability": float(vol_probability.loc[observed]),
            "vol_high_state": int(vol_probability.loc[observed] >= 0.5),
            "hmm_bear_probability": hmm_probability,
            "hmm_bear_state": int(hmm_probability >= 0.5),
            **{key: adwin_row[key] for key in adwin_row.index},
        })
    snapshots = pd.DataFrame(snapshots)
    if (pd.to_datetime(snapshots.market_observation_date) > pd.to_datetime(snapshots.decision_date)).any():
        raise AssertionError("future market observation crossed a decision boundary")

    daily = pd.concat([
        jump_state, vol_probability, (vol_probability >= .5).astype(int).rename("vol_high_state"),
        adwin_daily,
    ], axis=1).loc[online.index.min():]
    audit = {
        "calibration_first": train.index.min().date().isoformat(),
        "calibration_last": train.index.max().date().isoformat(),
        "calibration_rows": int(len(train)),
        "online_first": online.index.min().date().isoformat(),
        "online_last": online.index.max().date().isoformat(),
        "online_rows": int(len(online)),
        "jump_centers": np.asarray(jump.centers_).tolist(),
        "jump_state_order": {"0": "higher calibration cumulative return", "1": "bear"},
        "vol_high_component": high_vol_component,
        "vol_means": vol.means_.reshape(-1).tolist(),
        "hmm_bear_component": hmm_bear_component,
        "hmm_state_weighted_returns": weighted_return.tolist(),
        "hmm_converged": bool(hmm.monitor_.converged),
        "hmm_iterations": int(hmm.monitor_.iter),
        "adwin_detection_count": int(adwin.n_detections),
    }
    return RegimeResult(snapshots=snapshots, daily=daily, audit=audit)


def add_market_context(panel: pd.DataFrame, snapshots: pd.DataFrame) -> pd.DataFrame:
    left = panel.copy()
    left["decision_date"] = left["decision_date"].astype(str)
    right = snapshots.copy()
    right["decision_date"] = right["decision_date"].astype(str)
    result = left.merge(right, on="decision_date", how="left", validate="many_to_one")
    required = [column for column in right if column not in {"decision_date", "market_observation_date"}]
    if result[required].isna().any().any():
        raise ValueError("market context missing for stock panel rows")
    return result


def fit_ranker(training: pd.DataFrame, target: pd.DataFrame, features: list[str], parameters: dict):
    from lightgbm import LGBMRanker

    ordered = training.loc[
        training.future_xirr.notna() & training.enhanced_carry_xirr_score.notna()
    ].sort_values(["decision_date", "profile_name", "isin"], kind="stable")
    labels = ordered.groupby(["decision_date", "profile_name"]).future_xirr.rank(
        pct=True
    ).mul(4).clip(upper=3).astype(int)
    sizes = ordered.groupby(["decision_date", "profile_name"], sort=False).size().to_list()
    model = LGBMRanker(**parameters)
    model.fit(ordered[features], labels, group=sizes)
    valid = target.enhanced_carry_xirr_score.notna()
    prediction = pd.Series(np.nan, index=target.index, dtype=float)
    prediction.loc[valid] = model.predict(target.loc[valid, features])
    model_text = model.booster_.model_to_string()
    return prediction, {
        "training_rows": int(len(ordered)),
        "feature_importance": dict(zip(features, model.feature_importances_.astype(int).tolist())),
        "model_sha256": sha256(model_text.encode("utf-8")).hexdigest(),
    }


def blended_score(frame: pd.DataFrame, ranker_score: str) -> pd.Series:
    ranks = frame.groupby(["decision_date", "profile_name"])[
        ["enhanced_goal_score", ranker_score]
    ].rank(pct=True)
    return ranks.iloc[:, 0] * .67 + ranks.iloc[:, 1] * .33


def comprehensive_metrics(frame: pd.DataFrame, score: str, top_k: int = 20) -> dict:
    columns = [score, "future_xirr", "future_shortfall", "future_drawdown", "isin"]
    usable = frame[columns].dropna()
    if len(usable) < 3:
        return {"n": int(len(usable)), "coverage": len(usable) / max(len(frame), 1)}
    ranked = usable.sort_values([score, "isin"], ascending=[False, True], kind="stable")
    predicted = ranked.head(top_k)
    actual = usable.sort_values(["future_xirr", "isin"], ascending=[False, True], kind="stable").head(top_k)
    overlap = len(set(predicted["isin"]) & set(actual["isin"]))
    x, y = usable[score].to_numpy(), usable.future_xirr.to_numpy()
    sample = np.linspace(0, len(usable) - 1, min(len(usable), 400), dtype=int)
    dx, dy = x[sample, None] - x[None, sample], y[sample, None] - y[None, sample]
    mask = np.triu(np.ones_like(dx, dtype=bool), 1) & (dy != 0)
    pairs = np.where(dx * dy > 0, 1., np.where(dx == 0, .5, 0.))[mask]
    relevance = usable.future_xirr.rank(pct=True)
    gains = relevance.loc[predicted.index].to_numpy()
    ideal = relevance.nlargest(len(predicted)).to_numpy()
    discount = np.log2(np.arange(2, len(predicted) + 2))
    return {
        "n": int(len(usable)), "coverage": float(len(usable) / max(len(frame), 1)),
        "precision_at_20": float(overlap / max(len(predicted), 1)),
        "recall_at_20": float(overlap / max(len(actual), 1)),
        "ndcg_at_20": float((gains / discount).sum() / (ideal / discount).sum()),
        "pairwise_accuracy": float(pairs.mean()) if len(pairs) else np.nan,
        "rank_ic": float(usable[score].rank().corr(usable.future_xirr.rank())),
        "goal_attainment_top20": float(predicted.future_shortfall.eq(0).mean()),
        "goal_shortfall_top20": float(predicted.future_shortfall.mean()),
        "mean_xirr_top20": float(predicted.future_xirr.mean()),
        "median_xirr_top20": float(predicted.future_xirr.median()),
        "mean_drawdown_top20": float(predicted.future_drawdown.mean()),
    }


def verify_regime_run(directory: str | Path) -> dict:
    """Verify compact artifacts and the immutable research boundaries."""
    root = Path(directory).resolve()
    import json
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    artifacts = manifest["artifacts"]
    expected_set = sha256(json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if expected_set != manifest["artifact_set_sha256"]:
        raise ValueError("artifact inventory fingerprint mismatch")
    for item in artifacts:
        path = (root / item["path"]).resolve()
        if path.parent != root or not path.is_file():
            raise ValueError("unsafe or missing regime artifact")
        if path.stat().st_size != item["bytes"] or file_sha256(path) != item["sha256"]:
            raise ValueError(f"regime artifact changed: {item['path']}")
    leakage = json.loads((root / "leakage_audit.json").read_text(encoding="utf-8"))
    conclusion = json.loads((root / "conclusion.json").read_text(encoding="utf-8"))
    if leakage.get("status") != "PASS" or leakage.get("frozen_control_prediction_max_abs_error", 1) > 1e-12:
        raise ValueError("causal or frozen-control audit failed")
    if conclusion.get("production_changed") is not False or conclusion.get("frozen_control_changed") is not False:
        raise ValueError("immutable boundary failed")
    if abs(conclusion.get("control_goal_shortfall_top20", np.inf) - FROZEN_CONTROL_GOAL_SHORTFALL) > 1e-12:
        raise ValueError("frozen control aggregate did not reproduce")
    if not str(manifest.get("frozen_control_commit", "")).startswith("d499580"):
        raise ValueError("frozen control identity changed")
    return conclusion
