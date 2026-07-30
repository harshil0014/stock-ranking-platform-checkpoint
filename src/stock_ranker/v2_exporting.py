"""Export Research V2 rankings and eligibility results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from stock_ranker.research_v2 import ResearchV2Result
from stock_ranker.v2_contracts import (
    V2_ELIGIBILITY_COLUMNS,
    V2_OUTPUT_COLUMNS,
)


@dataclass(frozen=True, slots=True)
class ResearchV2ExportResult:
    full_rankings_path: Path
    top_rankings_path: Path
    eligibility_report_path: Path


def export_research_v2_results(
    result: ResearchV2Result,
    top_rankings: pd.DataFrame,
    output_dir: str | Path,
    top_n: int,
) -> ResearchV2ExportResult:
    """Write all three canonical V2 result files."""

    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
        raise ValueError("top_n must be a positive integer")
    for label, frame, columns in (
        ("full rankings", result.rankings, V2_OUTPUT_COLUMNS),
        ("top rankings", top_rankings, V2_OUTPUT_COLUMNS),
        ("eligibility report", result.eligibility, V2_ELIGIBILITY_COLUMNS),
    ):
        missing = set(columns).difference(frame.columns)
        if missing:
            raise ValueError(
                f"{label} missing required columns: "
                + ", ".join(sorted(missing))
            )

    directory = Path(output_dir)
    if directory.exists() and not directory.is_dir():
        raise ValueError(f"Output path is not a directory: {directory}")
    directory.mkdir(parents=True, exist_ok=True)

    full_path = directory / "full_research_v2_rankings.csv"
    top_path = directory / f"top_{top_n}_research_v2_rankings.csv"
    eligibility_path = directory / "research_v2_eligibility_report.csv"
    result.rankings.loc[:, list(V2_OUTPUT_COLUMNS)].to_csv(full_path, index=False)
    top_rankings.loc[:, list(V2_OUTPUT_COLUMNS)].to_csv(top_path, index=False)
    result.eligibility.loc[:, list(V2_ELIGIBILITY_COLUMNS)].to_csv(
        eligibility_path, index=False
    )
    return ResearchV2ExportResult(full_path, top_path, eligibility_path)
