"""Automation-ready, Qlib-independent quantitative research foundation."""

from stock_research.adapters import (
    RESEARCH_V2_MODEL_ID,
    convert_qlib_predictions,
    research_v2_to_signals,
)
from stock_research.comparison import compare_evaluations
from stock_research.contracts import (
    ChronologicalSplit,
    DateRange,
    reject_test_contamination,
    validate_feature_panel,
    validate_labels,
    validate_signals,
    validate_split,
)
from stock_research.evaluation import (
    EvaluationProtocol,
    EvaluationResult,
    evaluate_signals,
    export_evaluation,
)
from stock_research.fingerprints import (
    evaluation_protocol_fingerprint,
    fingerprint_config,
    fingerprint_dataframe,
    fingerprint_environment,
    fingerprint_file,
    model_configuration_fingerprint,
)
from stock_research.manifests import (
    create_manifest,
    load_manifest,
    transition_manifest,
    validate_manifest,
    write_manifest,
)
from stock_research.registry import Registry, validate_registry

__all__ = [
    "ChronologicalSplit", "DateRange", "EvaluationProtocol", "EvaluationResult",
    "RESEARCH_V2_MODEL_ID", "Registry", "compare_evaluations",
    "convert_qlib_predictions", "create_manifest", "evaluate_signals",
    "evaluation_protocol_fingerprint", "export_evaluation",
    "fingerprint_config", "fingerprint_dataframe", "fingerprint_environment",
    "fingerprint_file", "load_manifest", "model_configuration_fingerprint",
    "reject_test_contamination", "research_v2_to_signals",
    "transition_manifest", "validate_feature_panel", "validate_labels",
    "validate_manifest", "validate_registry", "validate_signals",
    "validate_split", "write_manifest",
]

__version__ = "0.1.0"
