from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from stock_research.consensus import verify_consensus
from stock_research.errors import ResearchValidationError
from stock_research.model_adapters import (
    AdapterCatalog, FunctionalModelAdapter, OpenSourceAPMom12mAdapter,
)
from stock_research.platform import (
    FeatureRequirement, ModelSpecification, build_model_dataset,
    specifications_from_registry, validate_feature_evidence,
)
from stock_research.registry import validate_execution_registry


ROOT = Path(__file__).parents[1]


def evidence(*, current_only=False, late=False):
    rows = []
    for ticker, sector, alpha, beta in [("AAA", "Tech", 1.0, 2.0), ("BBB", "Bank", 3.0, 4.0)]:
        for feature, value in [("alpha", alpha), ("beta", beta)]:
            rows.append({
                "as_of_date": "2026-08-07", "ticker": ticker, "sector": sector,
                "feature": feature, "value": value,
                "available_at": "2026-08-07T10:00:01+00:00" if late and ticker == "AAA" and feature == "alpha" else "2026-08-07T09:59:00+00:00",
                "availability_status": "current_only" if current_only and feature == "beta" else "pit_verified",
                "source_id": "official:test", "evidence_fingerprint": "a" * 64,
            })
    return pd.DataFrame(rows)


def specification():
    return ModelSpecification(
        "test_model", "native_deterministic",
        (FeatureRequirement("alpha"), FeatureRequirement("beta")),
        supported_frequencies=("event_date",), status="adapter_ready",
    )


def test_current_only_is_displayable_but_never_historical():
    assert len(validate_feature_evidence(evidence(current_only=True), mode="current")) == 4
    with pytest.raises(ResearchValidationError, match="current_only_historical_leakage"):
        validate_feature_evidence(evidence(current_only=True), mode="historical_train")


def test_per_feature_clock_enforces_1530_ist_cutoff():
    with pytest.raises(ResearchValidationError, match="future_feature_availability"):
        validate_feature_evidence(evidence(late=True), mode="historical_evaluation")
    naive = evidence()
    naive["available_at"] = "2026-08-01T10:00:00"
    with pytest.raises(ResearchValidationError, match="timezone"):
        validate_feature_evidence(naive, mode="current")


def test_model_dataset_reports_missing_requirements_without_imputation():
    raw = evidence().loc[lambda frame: ~((frame.ticker == "BBB") & (frame.feature == "beta"))]
    dataset = build_model_dataset(raw, specification(), mode="historical_evaluation", frequency="event_date")
    assert dataset.features["ticker"].tolist() == ["AAA"]
    excluded = dataset.eligibility.loc[dataset.eligibility.ticker.eq("BBB")].iloc[0]
    assert excluded.reason == "MISSING_REQUIRED_FEATURES"
    assert excluded.missing_features == "beta"
    assert len(dataset.feature_fingerprint) == 64


def test_feature_freshness_is_a_model_requirement():
    stale = evidence()
    stale.loc[stale.feature.eq("alpha"), "available_at"] = "2026-01-01T00:00:00+00:00"
    spec = replace(specification(), required_features=(FeatureRequirement("alpha", 30), FeatureRequirement("beta")))
    dataset = build_model_dataset(stale, spec, mode="historical_train", frequency="event_date")
    assert dataset.features.empty
    assert set(dataset.eligibility.missing_features) == {"alpha"}


def test_functional_adapter_emits_canonical_signals_without_mutation():
    raw = evidence()
    dataset = build_model_dataset(raw, specification(), mode="historical_evaluation", frequency="event_date")
    before = dataset.features.copy(deep=True)
    adapter = FunctionalModelAdapter(specification(), lambda frame: frame.alpha - frame.beta)
    signals = adapter.produce_signals(dataset, run_id="run-1")
    assert signals.score.tolist() == [-1.0, -1.0]
    pd.testing.assert_frame_equal(dataset.features, before)


def signals(model, scores):
    return pd.DataFrame({
        "as_of_date": ["2026-08-07", "2026-08-07"], "ticker": ["AAA", "BBB"],
        "score": scores, "model_id": [model, model], "run_id": [f"{model}-run"] * 2,
    })


def test_consensus_is_outcome_blind_and_selects_no_winner():
    result = verify_consensus(
        {"first": signals("first", [1, 2]), "second": signals("second", [2, 1])},
        model_configuration_fingerprints={"first": "f1", "second": "f2"},
        evaluation_protocol_fingerprint="protocol",
    )
    assert result.report["winner_selected"] is False
    assert result.report["labels_accessed"] is False
    assert result.pairwise_agreement.rank_correlation.iloc[0] == pytest.approx(-1)
    assert result.consensus_signals.model_id.unique().tolist() == ["verified_rank_consensus"]


def test_consensus_rejects_different_cohorts():
    second = signals("second", [2, 1]).iloc[:1]
    with pytest.raises(ResearchValidationError, match="consensus_cohort_mismatch"):
        verify_consensus(
            {"first": signals("first", [1, 2]), "second": second},
            model_configuration_fingerprints={"first": "f1", "second": "f2"},
            evaluation_protocol_fingerprint="protocol",
        )


def test_execution_registry_is_dependency_free_and_complete():
    registry = validate_execution_registry(ROOT / "research/registry/model_execution_registry.json")
    assert {
        "baseline_v1", "research_v2_baseline", "opensourceap_mom12m",
        "opensourceap_mom6m", "price_multifactor_equal_weight",
        "qlib_linear", "qlib_lightgbm", "qlib_double_ensemble", "qlib_tra",
        "fixed_chronological_lightgbm", "validated_price_ensemble",
    } == registry.model_ids
    specs = specifications_from_registry(registry.entries)
    assert {item.model_id for item in specs} == registry.model_ids
    source = (ROOT / "src/stock_research/platform.py").read_text(encoding="utf-8")
    source += (ROOT / "src/stock_research/model_adapters.py").read_text(encoding="utf-8")
    assert "import qlib" not in source
    assert "import lightgbm" not in source
    assert "import torch" not in source


def monthly_evidence(*, omit=None):
    rows = []
    for ticker in ("AAA", "BBB"):
        for period in pd.period_range("2025-01", "2026-01", freq="M"):
            if omit == (ticker, str(period)):
                continue
            date = period.end_time.date().isoformat()
            rows.append({
                "as_of_date": date, "ticker": ticker, "sector": "Test",
                "feature": "monthly_total_return", "value": 0.01,
                "available_at": f"{date}T09:00:00+05:30",
                "availability_status": "pit_verified", "source_id": "accepted-prices",
                "evidence_fingerprint": "b" * 64,
            })
    return pd.DataFrame(rows)


def mom_spec():
    return ModelSpecification(
        "opensourceap_mom12m", "external_formula_adapter",
        (FeatureRequirement("monthly_total_return"),),
        supported_frequencies=("monthly",), status="adapter_ready",
    )


def test_mom12m_matches_upstream_formula_on_complete_history():
    dataset = build_model_dataset(monthly_evidence(), mom_spec(), mode="historical_evaluation", frequency="monthly")
    adapter = OpenSourceAPMom12mAdapter(mom_spec())
    signals = adapter.produce_signals(dataset, run_id="run")
    assert len(signals) == 4  # Dec 2025 and Jan 2026 for two issuers.
    assert signals.score.tolist() == pytest.approx([(1.01 ** 11) - 1] * 4)
    catalog = AdapterCatalog({"opensourceap_mom12m": adapter})
    assert catalog.model_ids == ("opensourceap_mom12m",)


def test_mom12m_does_not_zero_fill_missing_calendar_month():
    dataset = build_model_dataset(
        monthly_evidence(omit=("AAA", "2025-06")), mom_spec(),
        mode="historical_evaluation", frequency="monthly",
    )
    signals = OpenSourceAPMom12mAdapter(mom_spec()).produce_signals(dataset, run_id="run")
    # BBB has two valid dates; AAA has neither because June is in both windows.
    assert signals.ticker.tolist() == ["BBB", "BBB"]
