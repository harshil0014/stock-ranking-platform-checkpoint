"""Run fixed LightGBM and official Qlib DoubleEnsemble chronologically."""
from __future__ import annotations

import argparse
import json
import os
from hashlib import sha256
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_research.chronological_ml_benchmark import (  # noqa: E402
    ARTIFACTS, FEATURES, SCHEMA_VERSION, eligible_training_rows, file_hash,
    score_sector_metrics, validate_panel,
)


CONTROLS = {
    "PYTHONHASHSEED": "20260730", "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
}


def _require_controls() -> None:
    observed = {key: os.environ.get(key) for key in CONTROLS}
    if observed != CONTROLS:
        raise ValueError(f"deterministic child controls mismatch: {observed}")
    forbidden = [key for key in os.environ if key.startswith("MLFLOW_")]
    if forbidden:
        raise ValueError(f"MLflow configuration is forbidden: {sorted(forbidden)}")


class _Dataset:
    def __init__(self, train, valid, test):
        self.parts = {"train": train, "valid": valid, "test": test}

    def prepare(self, segment, col_set=None, data_key=None):
        del data_key
        if isinstance(segment, (list, tuple)):
            return tuple(self.prepare(item, col_set=col_set) for item in segment)
        frame = self.parts[segment]
        if col_set == "feature":
            return frame["feature"]
        return frame


def _qlib_frame(frame, np, pd):
    index = pd.MultiIndex.from_arrays(
        [pd.to_datetime(frame.ranking_date), frame.ticker], names=["datetime", "instrument"]
    )
    x = frame.loc[:, FEATURES].apply(pd.to_numeric, errors="coerce")
    # Official DoubleEnsemble ultimately delegates missing values to LightGBM.
    x.index = index
    y = pd.DataFrame({"LABEL0": frame.target.to_numpy(float)}, index=index)
    return pd.concat({"feature": x, "label": y}, axis=1)


def run(panel_path: Path, output: Path) -> str:
    if output.exists():
        raise ValueError("fresh output directory required")
    _require_controls()
    panel_bytes = panel_path.read_bytes()
    panel_hash = sha256(panel_bytes).hexdigest()

    import numpy as np
    import pandas as pd
    import lightgbm as lgb
    import qlib
    from qlib.contrib.model.double_ensemble import DEnsembleModel

    np.random.seed(20260730)
    panel = pd.read_csv(panel_path)
    panel["baseline_rank_signal"] = panel.groupby(
        ["ranking_date", "sector"], sort=True
    )["baseline_sector_rank"].rank(method="average", ascending=False, pct=True)
    validate_panel(panel)
    panel["target"] = panel.groupby(["ranking_date", "sector"])["future_adjusted_return"].rank(pct=True)
    predictions = []
    execution = {"controls": CONTROLS, "panel_sha256": panel_hash, "runs": []}
    lgb_params = {
        "objective": "regression", "metric": "l2", "verbosity": -1,
        "learning_rate": 0.05, "num_leaves": 7, "max_depth": 3,
        "min_data_in_leaf": 5, "feature_fraction": 1.0, "bagging_fraction": 1.0,
        "num_threads": 1, "seed": 20260730, "feature_fraction_seed": 20260730,
        "bagging_seed": 20260730, "data_random_seed": 20260730,
        "deterministic": True, "force_col_wise": True,
    }
    dates = sorted(panel.ranking_date.astype(str).unique())
    for date in dates:
        train_mask = eligible_training_rows(panel, date)
        test = panel.loc[panel.ranking_date.eq(date)].copy()
        train = panel.loc[train_mask].copy()
        if train.empty:
            continue
        model = lgb.train(lgb_params, lgb.Dataset(train.loc[:, FEATURES], label=train.target), num_boost_round=64)
        values = model.predict(test.loc[:, FEATURES])
        predictions.extend({"ranking_date": date, "ticker": row.ticker, "isin": row.isin,
                            "model": "fixed_lightgbm", "prediction": float(value)}
                           for row, value in zip(test.itertuples(), values))
        execution["runs"].append({"model": "fixed_lightgbm", "test_date": date,
                                  "training_rows": len(train), "training_dates": sorted(train.ranking_date.unique()),
                                  "trees": model.num_trees()})

        matured_dates = sorted(train.ranking_date.unique())
        if len(matured_dates) < 2:
            continue
        valid_date = matured_dates[-1]
        de_train = train.loc[train.ranking_date.ne(valid_date)].copy()
        de_valid = train.loc[train.ranking_date.eq(valid_date)].copy()
        if len(de_train) < 10 or len(de_valid) < 10:
            continue
        np.random.seed(20260730)
        dataset = _Dataset(_qlib_frame(de_train, np, pd), _qlib_frame(de_valid, np, pd), _qlib_frame(test, np, pd))
        de = DEnsembleModel(
            base_model="gbm", loss="mse", num_models=3, enable_sr=True, enable_fs=True,
            alpha1=1.0, alpha2=1.0, bins_sr=10, bins_fs=5, decay=0.5,
            sample_ratios=[0.8, 0.7, 0.6, 0.5, 0.4], sub_weights=[1.0, 1.0, 1.0],
            epochs=28, early_stopping_rounds=None, **lgb_params,
        )
        try:
            de.fit(dataset)
            values = de.predict(dataset, segment="test")
            predictions.extend({"ranking_date": date, "ticker": ticker, "isin": isin,
                                "model": "official_qlib_doubleensemble", "prediction": float(value)}
                               for ticker, isin, value in zip(test.ticker, test["isin"], values.to_numpy()))
            execution["runs"].append({"model": "official_qlib_doubleensemble", "test_date": date,
                                      "training_rows": len(de_train), "validation_rows": len(de_valid),
                                      "training_dates": sorted(de_train.ranking_date.unique()),
                                      "validation_date": valid_date,
                                      "submodels": len(de.ensemble),
                                      "tree_counts": [item.num_trees() for item in de.ensemble]})
        except Exception as exc:  # retain the official small-sample compatibility result
            execution["runs"].append({"model": "official_qlib_doubleensemble", "test_date": date,
                                      "status": "BLOCKED", "error": f"{type(exc).__name__}: {exc}"})

    result = pd.DataFrame(predictions)
    if result.empty:
        raise ValueError("no chronological ML predictions produced")
    metrics = score_sector_metrics(panel, result)
    output.mkdir(parents=True)
    result.to_csv(output / "predictions.csv", index=False, float_format="%.17g", lineterminator="\n")
    metrics.to_csv(output / "sector_metrics.csv", index=False, float_format="%.17g", lineterminator="\n")
    aggregates = {name: {"valid_sector_dates": len(group), "mean_rank_ic": float(group.rank_ic.mean())}
                  for name, group in metrics.groupby("model", sort=True)}
    summary = {
        "schema_version": SCHEMA_VERSION, "status": "SUPPLEMENTARY_RETROSPECTIVE_ONLY",
        "outcome_status": "PREVIOUSLY_REVEALED_NOT_UNSEEN", "panel_sha256": panel_hash,
        "feature_set": list(FEATURES), "prediction_rows": int(len(result)),
        "models": aggregates, "product_default": "baseline_v1", "product_default_changed": False,
        "promotion_permitted": False,
        "scientific_limit": "Four revealed dates and sparse clock-linked accounting history cannot establish superiority.",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    execution.update({"python": sys.version, "qlib": qlib.__version__, "lightgbm": lgb.__version__})
    (output / "execution.json").write_text(json.dumps(execution, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    if sha256(panel_path.read_bytes()).hexdigest() != panel_hash:
        raise ValueError("frozen panel changed during model run")
    artifacts = [{"path": name, "sha256": file_hash(output / name), "size": (output / name).stat().st_size}
                 for name in sorted(ARTIFACTS)]
    manifest = {"schema_version": SCHEMA_VERSION, "artifacts": artifacts}
    manifest["fingerprint"] = sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest["fingerprint"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(run(args.panel, args.output))
        return 0
    except Exception as exc:
        print(f"chronological ML benchmark failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
