"""Standalone acceptance verifier intended for ``.venv-qlib``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

import numpy as np
import pandas as pd


class VerificationFailure(RuntimeError):
    """Concise, expected failure while validating reproduction artifacts."""


def _batch_directory(value: str) -> Path:
    path = Path(value)
    if not path.exists():
        raise argparse.ArgumentTypeError(
            f"batch directory does not exist: {path}"
        )
    if not path.is_dir():
        raise argparse.ArgumentTypeError(
            f"batch directory is not a directory: {path}"
        )
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify an offline two-run Qlib Linear reproduction batch."
        )
    )
    parser.add_argument(
        "batch_directory",
        type=_batch_directory,
        help="existing generated Qlib Linear batch directory",
    )
    return parser


def _relative(path: Path, batch: Path) -> str:
    return path.relative_to(batch).as_posix()


def _require_file(path: Path, batch: Path) -> None:
    if not path.is_file():
        raise VerificationFailure(
            f"missing required artifact: {_relative(path, batch)}"
        )


def _read_json(path: Path, batch: Path) -> dict[str, Any]:
    _require_file(path, batch)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationFailure(
            f"invalid JSON artifact {_relative(path, batch)}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise VerificationFailure(
            f"JSON artifact must contain an object: {_relative(path, batch)}"
        )
    return value


def _read_csv(path: Path, batch: Path) -> pd.DataFrame:
    _require_file(path, batch)
    try:
        return pd.read_csv(path)
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise VerificationFailure(
            f"invalid CSV artifact {_relative(path, batch)}: {exc}"
        ) from exc


def verify(batch: Path) -> None:
    if not batch.is_dir():
        raise VerificationFailure(
            f"batch directory does not exist or is not a directory: {batch}"
        )
    reproduction = _read_json(
        batch / "reproducibility_report.json", batch
    )
    runs = sorted(path for path in batch.glob("run-*") if path.is_dir())
    if len(runs) != 2:
        raise VerificationFailure("expected exactly two run directories")
    required_per_run = (
        "qlib_model_metadata.json",
        "qlib_indexed_predictions.csv",
        "research_v2_signals.csv",
        "research_v2_eligibility_report.csv",
        "evaluation_qlib/evaluation_summary.json",
        "evaluation_research_v2/evaluation_summary.json",
    )
    for run in runs:
        for relative_path in required_per_run:
            _require_file(run / relative_path, batch)

    import qlib

    if qlib.__version__ != "0.9.7":
        raise RuntimeError(f"expected Qlib 0.9.7; got {qlib.__version__}")
    if not reproduction["passed"] or reproduction["tolerance"] != 1e-12:
        raise RuntimeError("batch did not pass the fixed reproducibility tolerance")
    protocols = set()
    models = set()
    for run in runs:
        metadata = _read_json(run / "qlib_model_metadata.json", batch)
        if metadata["thread_controls"] != {
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
        }:
            raise RuntimeError("single-thread controls were not recorded")
        intercept = metadata["intercept"]
        if intercept is not None and abs(float(intercept)) > 1e-12:
            raise RuntimeError("extracted intercept is not zero within tolerance")
        predictions = _read_csv(
            run / "qlib_indexed_predictions.csv", batch
        )
        signals = _read_csv(run / "research_v2_signals.csv", batch)
        eligibility = _read_csv(
            run / "research_v2_eligibility_report.csv", batch
        )
        if len(predictions) != 1200 or len(signals) != 1160:
            raise RuntimeError("unexpected signal counts")
        ineligible = eligibility.loc[~eligibility["eligible"]]
        if len(ineligible) != 40 or set(ineligible["ticker"]) != {"SYN030"}:
            raise RuntimeError("SYN030 diagnostics are incomplete")
        if not np.isfinite(predictions["score"]).all():
            raise RuntimeError("nonfinite Qlib prediction")
        qlib_summary = _read_json(
            run / "evaluation_qlib/evaluation_summary.json", batch
        )
        v2_summary = _read_json(
            run / "evaluation_research_v2/evaluation_summary.json", batch
        )
        protocols.update([
            qlib_summary["evaluation_protocol_fingerprint"],
            v2_summary["evaluation_protocol_fingerprint"],
        ])
        models.update([
            qlib_summary["model_configuration_fingerprint"],
            v2_summary["model_configuration_fingerprint"],
        ])
        if qlib_summary["valid_ic_dates"] < 2 or v2_summary["valid_ic_dates"] < 2:
            raise RuntimeError("evaluation lacks multiple finite IC dates")
    if len(protocols) != 1 or len(models) != 2:
        raise RuntimeError("protocol/model fingerprint fairness boundary failed")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        verify(args.batch_directory)
    except Exception as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        return 1
    print("Qlib Linear integration verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
