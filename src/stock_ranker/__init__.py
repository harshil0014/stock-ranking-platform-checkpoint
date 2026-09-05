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
from stock_ranker.professor_reference import (
    ProfessorReferenceResult,
    benchmark_professor_reference,
    export_professor_reference,
    extract_professor_reference,
)
from stock_ranker.professor_acceptance import (
    ProfessorAcceptanceResult,
    build_professor_acceptance,
    export_professor_acceptance,
)
from stock_ranker.professor_strategy import (
    ProfessorStrategyResult,
    benchmark_professor_strategy,
    export_professor_strategy,
    extract_ok_strategy_workbook,
)
from stock_ranker.live_market import (
    LiveMarketBundle,
    add_bse_traded_securities,
    apply_official_segments,
    audit_official_equity_universe,
    build_latest_snapshot,
    classify_ranking_instruments,
    combine_live_market,
    load_index_membership,
    load_live_market_bundle,
    load_official_equity_universe,
    write_live_bundle,
)
from stock_ranker.data_state import (
    DATA_STATE_VERSION,
    DataStatePaths,
    data_state_status,
    promote_candidate_bundle,
    resolve_accepted_bundle_root,
)
from stock_ranker.company_facts import (
    FACT_SCHEMA_VERSION,
    CompanyFactResult,
    build_company_facts,
    load_company_fact_snapshot,
    promote_company_fact_snapshot,
    resolve_company_fact_snapshot,
    write_company_fact_snapshot,
)
from stock_ranker.secondary_facts import (
    YAHOO_OBSERVATION_VERSION,
    YahooSecondaryBundle,
    load_yahoo_secondary_bundle,
    validate_yahoo_identity,
    validate_yahoo_observations,
    yahoo_coverage,
)
from stock_ranker.exchange_backbone import (
    BACKBONE_VERSION,
    OfficialBackboneBundle,
    audit_derived_classifications,
    due_backlog,
    initialize_backlog,
    load_official_backbone,
    parse_exchange_xbrl,
    update_backlog,
)
from stock_ranker.product_classification import (
    PRODUCT_CLASSIFICATION_VERSION,
    add_product_classification_and_baseline,
)
from stock_ranker.bulk_classification import (
    BULK_CLASSIFICATION_VERSION,
    BulkClassificationResult,
    build_bulk_classifications,
    validate_bulk_classifications,
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
from stock_ranker.pit_fundamental_probe import (
    PITFundamentalProbeConfig,
    assess_annual_report_probe,
    select_probe_cohort,
    summarize_structured_fact_coverage,
)
from stock_ranker.pit_fundamental_scale import (
    audit_historical_report_availability,
    build_pit_fundamental_population,
    select_report_download_batch,
    summarize_annual_report_metadata,
)
from stock_ranker.identity_continuity import (
    build_identity_continuity,
    parse_nse_name_history,
    parse_nse_symbol_history,
)
from stock_ranker.pit_annual_report_packets import build_annual_report_review_packets
from stock_ranker.pit_accounting_validation import (
    ParsedDisclosure,
    parse_profit_page,
    parse_ratio_page,
    unique_disclosure,
)
from stock_ranker.pit_accounting_promotion import (
    load_promoted_additions,
    merge_candidate_fundamentals,
    validated_fundamental_candidates,
)
from stock_ranker.pit_structured_fundamentals import (
    StructuredPITBridgeResult,
    bridge_structured_fundamentals,
)
from stock_ranker.screener_historical_fundamentals import (
    SCREENER_HISTORICAL_CONTRACT_VERSION,
    ScreenerHistoricalResult,
    build_screener_pit_cohorts,
    calibrate_screener_against_gold,
    official_clock_from_availability,
    parse_screener_historical_workbook,
)
from stock_ranker.screener_public_history import (
    PUBLIC_PAGE_SCHEMA,
    PUBLIC_VALUE_METHOD,
    acquire_public_company_pages,
    parse_cached_public_pages,
    parse_public_company_history,
)
from stock_ranker.screener_xbrl_reconstruction import (
    XBRL_CANDIDATE_VALUE_METHOD,
    XBRL_REQUIRED_CONCEPTS,
    XBRLScreenerReconstructionResult,
    audit_xbrl_component_alignment,
    reconstruct_screener_methodology_from_xbrl,
)
from stock_ranker.baseline_eligibility_audit import audit_baseline_eligibility
from stock_ranker.pit_accounting_pdfium import (
    PdfiumDisclosure,
    parse_pdfium_profit_page,
    parse_pdfium_ratio_page,
    select_pdfium_disclosure,
)
from stock_ranker.liquidity_contract import (
    calculate_point_in_time_liquidity,
    validate_liquidity_panel,
)
from stock_ranker.bse_annual_report_fallback import (
    exact_bse_identity_map,
    select_bse_annual_report_announcement,
)
from stock_ranker.v2_config import ResearchV2Config, ResearchV2Weights
from stock_ranker.screener_data_bundle import (
    SCREENER_BUNDLE_VERSION,
    ScreenerDataBundleResult,
    accept_screener_data_bundle,
    build_coverage_audit,
    build_missing_history_and_next_batch,
    ingest_screener_data_bundle,
    merge_history_incrementally,
    merge_screener_market_exports,
)
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
    "ProfessorReferenceResult",
    "LiveMarketBundle",
    "add_bse_traded_securities",
    "DATA_STATE_VERSION",
    "DataStatePaths",
    "FACT_SCHEMA_VERSION",
    "CompanyFactResult",
    "YAHOO_OBSERVATION_VERSION",
    "YahooSecondaryBundle",
    "BACKBONE_VERSION",
    "OfficialBackboneBundle",
    "PRODUCT_CLASSIFICATION_VERSION",
    "BULK_CLASSIFICATION_VERSION",
    "BulkClassificationResult",
    "build_bulk_classifications",
    "validate_bulk_classifications",
    "add_product_classification_and_baseline",
    "audit_derived_classifications",
    "due_backlog",
    "initialize_backlog",
    "load_official_backbone",
    "parse_exchange_xbrl",
    "update_backlog",
    "load_yahoo_secondary_bundle",
    "validate_yahoo_identity",
    "validate_yahoo_observations",
    "yahoo_coverage",
    "build_company_facts",
    "load_company_fact_snapshot",
    "promote_company_fact_snapshot",
    "resolve_company_fact_snapshot",
    "write_company_fact_snapshot",
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
    "load_official_equity_universe",
    "load_index_membership",
    "apply_official_segments",
    "build_latest_snapshot",
    "combine_live_market",
    "write_live_bundle",
    "load_live_market_bundle",
    "data_state_status",
    "promote_candidate_bundle",
    "resolve_accepted_bundle_root",
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
    "benchmark_professor_reference",
    "export_professor_reference",
    "extract_professor_reference",
    "ProfessorAcceptanceResult",
    "build_professor_acceptance",
    "export_professor_acceptance",
    "ProfessorStrategyResult",
    "benchmark_professor_strategy",
    "export_professor_strategy",
    "extract_ok_strategy_workbook",
    "select_point_in_time_filing",
    "PITFundamentalProbeConfig",
    "assess_annual_report_probe",
    "select_probe_cohort",
    "summarize_structured_fact_coverage",
    "audit_historical_report_availability",
    "build_pit_fundamental_population",
    "select_report_download_batch",
    "summarize_annual_report_metadata",
    "build_identity_continuity",
    "parse_nse_name_history",
    "parse_nse_symbol_history",
    "build_annual_report_review_packets",
    "ParsedDisclosure",
    "parse_profit_page",
    "parse_ratio_page",
    "unique_disclosure",
    "load_promoted_additions",
    "merge_candidate_fundamentals",
    "validated_fundamental_candidates",
    "StructuredPITBridgeResult",
    "bridge_structured_fundamentals",
    "SCREENER_HISTORICAL_CONTRACT_VERSION",
    "ScreenerHistoricalResult",
    "build_screener_pit_cohorts",
    "calibrate_screener_against_gold",
    "official_clock_from_availability",
    "parse_screener_historical_workbook",
    "PUBLIC_PAGE_SCHEMA",
    "PUBLIC_VALUE_METHOD",
    "acquire_public_company_pages",
    "parse_cached_public_pages",
    "XBRL_CANDIDATE_VALUE_METHOD",
    "XBRL_REQUIRED_CONCEPTS",
    "XBRLScreenerReconstructionResult",
    "audit_xbrl_component_alignment",
    "reconstruct_screener_methodology_from_xbrl",
    "parse_public_company_history",
    "audit_baseline_eligibility",
    "PdfiumDisclosure",
    "parse_pdfium_profit_page",
    "parse_pdfium_ratio_page",
    "select_pdfium_disclosure",
    "calculate_point_in_time_liquidity",
    "validate_liquidity_panel",
    "exact_bse_identity_map",
    "select_bse_annual_report_announcement",
    "SCREENER_BUNDLE_VERSION",
    "ScreenerDataBundleResult",
    "accept_screener_data_bundle",
    "build_coverage_audit",
    "build_missing_history_and_next_batch",
    "ingest_screener_data_bundle",
    "merge_history_incrementally",
    "merge_screener_market_exports",
]

__version__ = "0.2.0"
