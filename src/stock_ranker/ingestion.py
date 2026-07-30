"""CSV ingestion for canonical Baseline V1 stock records."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from stock_ranker.validation import validate_baseline_input


def load_stock_csv(path: str | Path) -> pd.DataFrame:
    """Read and validate a Baseline V1 CSV file."""

    csv_path = Path(path)
    if not csv_path.is_file():
        raise ValueError(f"Input CSV does not exist or is not a file: {csv_path}")

    try:
        data = pd.read_csv(csv_path)
    except (OSError, pd.errors.ParserError, UnicodeError) as exc:
        raise ValueError(f"Could not read input CSV '{csv_path}': {exc}") from exc

    return validate_baseline_input(data)
