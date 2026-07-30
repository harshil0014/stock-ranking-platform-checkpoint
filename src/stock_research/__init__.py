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
from stock_research.qlib_reproduction import (
    QlibLinearReproductionConfig,
    ReproductionBatchResult,
    ReproductionPlan,
    ReproductionRunResult,
    build_qlib_subprocess_environment,
    compare_reproduction_runs,
    plan_qlib_linear_reproduction,
    run_qlib_linear_reproduction,
)
from stock_research.synthetic_qlib import (
    SyntheticDatasetBundle,
    generate_synthetic_qlib_data,
    reconstruct_price_features,
)

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
    "QlibLinearReproductionConfig", "ReproductionBatchResult",
    "ReproductionPlan", "ReproductionRunResult", "SyntheticDatasetBundle",
    "compare_reproduction_runs", "generate_synthetic_qlib_data",
    "build_qlib_subprocess_environment",
    "plan_qlib_linear_reproduction", "reconstruct_price_features",
    "run_qlib_linear_reproduction",
]

__version__ = "0.1.0"
