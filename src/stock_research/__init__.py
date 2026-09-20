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
from stock_research.registry import ExecutionRegistry, validate_execution_registry
from stock_research.platform import (
    FeatureRequirement, ModelDataset, ModelSpecification,
    build_model_dataset, specifications_from_registry, validate_feature_evidence,
)
from stock_research.model_adapters import (
    AdapterCatalog, FunctionalModelAdapter, ModelAdapter,
    OpenSourceAPMom12mAdapter, PrecomputedSignalAdapter,
)
from stock_research.consensus import ConsensusResult, verify_consensus
from stock_research.current_data import CURRENT_FEATURE_MAP, load_accepted_current_evidence
from stock_research.exploratory_benchmark import (
    build_exploratory_signals, evaluate_exploratory_signals,
    run_exploratory_benchmark, strict_mom12m,
)
from stock_research.prospective_validation import (
    freeze_prospective_challengers, validate_prospective_freeze,
)
from stock_research.chronological_ml_benchmark import (
    eligible_training_rows, score_sector_metrics,
    validate_panel as validate_chronological_ml_panel,
    validate_result as validate_chronological_ml_result,
)
from stock_research.current_price_ensemble import validate_current_price_ensemble
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
from stock_research.qlib_lightgbm_compatibility import (
    QlibLightGBMCompatibilityConfig,
    QlibLightGBMCompatibilityPlan,
    QlibLightGBMCompatibilityResult,
    build_qlib_lightgbm_plan,
    run_qlib_lightgbm_compatibility_proof,
    validate_frozen_lightgbm_inputs,
)
from stock_research.qlib_lightgbm_reproduction import (
    QlibLightGBMBatchResult,
    QlibLightGBMReproductionConfig,
    QlibLightGBMReproductionPlan,
    QlibLightGBMRunResult,
    build_lightgbm_subprocess_environment,
    compare_lightgbm_reproduction_runs,
    finalize_failed_lightgbm_batch,
    plan_qlib_lightgbm_reproduction,
    run_qlib_lightgbm_reproduction,
    validate_local_recorder_paths,
)
from stock_research.qlib_doubleensemble_reproduction import (
    QlibDoubleEnsembleBatchResult,
    QlibDoubleEnsembleReproductionConfig,
    QlibDoubleEnsembleReproductionPlan,
    QlibDoubleEnsembleRunResult,
    build_doubleensemble_subprocess_environment,
    compare_doubleensemble_runs,
    finalize_doubleensemble_failed_batch,
    plan_qlib_doubleensemble_reproduction,
    run_qlib_doubleensemble_reproduction,
)
from stock_research.qlib_tra_reproduction import (
    QlibTRABatchResult,
    QlibTRAReproductionConfig,
    QlibTRAReproductionPlan,
    QlibTRARunResult,
    build_tra_subprocess_environment,
    compare_tra_runs,
    plan_qlib_tra_reproduction,
    run_qlib_tra_reproduction,
)

__all__ = [
    "ChronologicalSplit", "DateRange", "EvaluationProtocol", "EvaluationResult",
    "RESEARCH_V2_MODEL_ID", "Registry", "ExecutionRegistry", "compare_evaluations",
    "convert_qlib_predictions", "create_manifest", "evaluate_signals",
    "evaluation_protocol_fingerprint", "export_evaluation",
    "fingerprint_config", "fingerprint_dataframe", "fingerprint_environment",
    "fingerprint_file", "load_manifest", "model_configuration_fingerprint",
    "reject_test_contamination", "research_v2_to_signals",
    "transition_manifest", "validate_feature_panel", "validate_labels",
    "validate_manifest", "validate_registry", "validate_signals",
    "validate_execution_registry", "validate_feature_evidence",
    "FeatureRequirement", "ModelDataset", "ModelSpecification",
    "build_model_dataset", "specifications_from_registry",
    "ModelAdapter", "FunctionalModelAdapter", "PrecomputedSignalAdapter",
    "OpenSourceAPMom12mAdapter", "AdapterCatalog",
    "ConsensusResult", "verify_consensus",
    "CURRENT_FEATURE_MAP", "load_accepted_current_evidence",
    "strict_mom12m", "build_exploratory_signals",
    "evaluate_exploratory_signals", "run_exploratory_benchmark",
    "freeze_prospective_challengers", "validate_prospective_freeze",
    "eligible_training_rows", "score_sector_metrics",
    "validate_chronological_ml_panel", "validate_chronological_ml_result",
    "validate_current_price_ensemble",
    "validate_split", "write_manifest",
    "QlibLinearReproductionConfig", "ReproductionBatchResult",
    "ReproductionPlan", "ReproductionRunResult", "SyntheticDatasetBundle",
    "compare_reproduction_runs", "generate_synthetic_qlib_data",
    "build_qlib_subprocess_environment",
    "plan_qlib_linear_reproduction", "reconstruct_price_features",
    "run_qlib_linear_reproduction",
    "QlibLightGBMCompatibilityConfig",
    "QlibLightGBMCompatibilityPlan",
    "QlibLightGBMCompatibilityResult",
    "build_qlib_lightgbm_plan",
    "run_qlib_lightgbm_compatibility_proof",
    "validate_frozen_lightgbm_inputs",
    "QlibLightGBMBatchResult",
    "QlibLightGBMReproductionConfig",
    "QlibLightGBMReproductionPlan",
    "QlibLightGBMRunResult",
    "build_lightgbm_subprocess_environment",
    "compare_lightgbm_reproduction_runs",
    "finalize_failed_lightgbm_batch",
    "plan_qlib_lightgbm_reproduction",
    "run_qlib_lightgbm_reproduction",
    "validate_local_recorder_paths",
    "QlibDoubleEnsembleBatchResult",
    "QlibDoubleEnsembleReproductionConfig",
    "QlibDoubleEnsembleReproductionPlan",
    "QlibDoubleEnsembleRunResult",
    "build_doubleensemble_subprocess_environment",
    "compare_doubleensemble_runs",
    "finalize_doubleensemble_failed_batch",
    "plan_qlib_doubleensemble_reproduction",
    "run_qlib_doubleensemble_reproduction",
    "QlibTRABatchResult",
    "QlibTRAReproductionConfig",
    "QlibTRAReproductionPlan",
    "QlibTRARunResult",
    "build_tra_subprocess_environment",
    "compare_tra_runs",
    "plan_qlib_tra_reproduction",
    "run_qlib_tra_reproduction",
]

__version__ = "0.1.0"
