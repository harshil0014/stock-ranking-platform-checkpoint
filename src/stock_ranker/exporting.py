"""CSV result exporting for full and top-N Baseline V1 rankings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from stock_ranker.contracts import OUTPUT_COLUMNS


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Paths written by one ranking run."""

    full_rankings_path: Path
    top_rankings_path: Path


def export_rankings(
    full_rankings: pd.DataFrame,
    top_rankings: pd.DataFrame,
    output_dir: str | Path,
    top_n: int,
) -> ExportResult:
    """Export canonical full and top-N ranking CSV files."""

    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
        raise ValueError("top_n must be a positive integer")

    for label, frame in (
        ("full rankings", full_rankings),
        ("top rankings", top_rankings),
    ):
        missing = set(OUTPUT_COLUMNS).difference(frame.columns)
        if missing:
            raise ValueError(
                f"{label} missing required columns: "
                + ", ".join(sorted(missing))
            )

    directory = Path(output_dir)
    if directory.exists() and not directory.is_dir():
        raise ValueError(f"Output path is not a directory: {directory}")
    directory.mkdir(parents=True, exist_ok=True)

    full_path = directory / "full_rankings.csv"
    top_path = directory / f"top_{top_n}_rankings.csv"
    full_rankings.loc[:, list(OUTPUT_COLUMNS)].to_csv(full_path, index=False)
    top_rankings.loc[:, list(OUTPUT_COLUMNS)].to_csv(top_path, index=False)
    return ExportResult(full_path, top_path)
