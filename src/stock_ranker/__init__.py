"""Offline, explainable stock-ranking research tools."""

from stock_ranker.baseline import (
    calculate_baseline_rankings,
    get_top_stocks_by_sector,
)
from stock_ranker.config import BaselineConfig
from stock_ranker.exporting import ExportResult, export_rankings
from stock_ranker.ingestion import load_stock_csv
from stock_ranker.validation import validate_baseline_input

__all__ = [
    "BaselineConfig",
    "ExportResult",
    "calculate_baseline_rankings",
    "export_rankings",
    "get_top_stocks_by_sector",
    "load_stock_csv",
    "validate_baseline_input",
]

__version__ = "0.1.0"
