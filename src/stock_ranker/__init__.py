"""Offline, explainable stock-ranking research tools."""

from stock_ranker.baseline import (
    calculate_baseline_rankings,
    get_top_stocks_by_sector,
)
from stock_ranker.config import BaselineConfig
from stock_ranker.exporting import ExportResult, export_rankings
from stock_ranker.ingestion import load_stock_csv
from stock_ranker.historical_baseline import (
    HistoricalBaselineBundle,
    HistoricalBaselinePrepared,
    calculate_prepared_real_rankings,
    load_historical_baseline_bundle,
    prepare_historical_baseline,
    provider_symbol,
)
from stock_ranker.nse_snapshot import (
    NSESnapshotResult,
    load_nse_snapshot,
    parse_nse_snapshot,
)
from stock_ranker.research_v2 import (
    ResearchV2Inputs,
    ResearchV2Result,
    calculate_research_v2,
    get_top_research_v2_by_sector,
    load_research_v2_inputs,
)
from stock_ranker.real_research_v2 import (
    FUNDAMENTAL_DATA_CONTRACT_VERSION,
    RealResearchV2Bundle,
    XBRLDocument,
    XBRLFact,
    build_matched_cohort_comparison,
    extract_exact_reported_metrics,
    load_real_research_v2_bundle,
    parse_nse_xbrl,
    prepare_real_research_v2_bundle,
    select_point_in_time_filing,
)
from stock_ranker.validation import validate_baseline_input
from stock_ranker.v2_config import ResearchV2Config, ResearchV2Weights
from stock_ranker.v2_exporting import (
    ResearchV2ExportResult,
    export_research_v2_results,
)

__all__ = [
    "BaselineConfig",
    "ExportResult",
    "ResearchV2Config",
    "ResearchV2ExportResult",
    "ResearchV2Inputs",
    "ResearchV2Result",
    "ResearchV2Weights",
    "RealResearchV2Bundle",
    "FUNDAMENTAL_DATA_CONTRACT_VERSION",
    "XBRLDocument",
    "XBRLFact",
    "NSESnapshotResult",
    "HistoricalBaselineBundle",
    "HistoricalBaselinePrepared",
    "calculate_baseline_rankings",
    "calculate_research_v2",
    "export_rankings",
    "export_research_v2_results",
    "get_top_stocks_by_sector",
    "get_top_research_v2_by_sector",
    "load_stock_csv",
    "load_historical_baseline_bundle",
    "load_nse_snapshot",
    "parse_nse_snapshot",
    "load_research_v2_inputs",
    "validate_baseline_input",
    "prepare_historical_baseline",
    "provider_symbol",
    "calculate_prepared_real_rankings",
    "extract_exact_reported_metrics",
    "load_real_research_v2_bundle",
    "parse_nse_xbrl",
    "prepare_real_research_v2_bundle",
    "build_matched_cohort_comparison",
    "select_point_in_time_filing",
]

__version__ = "0.2.0"
