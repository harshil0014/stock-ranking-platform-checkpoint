from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest
import stock_research.qlib_reproduction as reproduction

from stock_ranker.research_v2 import ResearchV2Inputs, calculate_research_v2
from stock_ranker.v2_config import ResearchV2Config
from stock_research.contracts import validate_feature_panel
from stock_research.errors import ResearchValidationError
from stock_research.qlib_reproduction import (
    QlibLinearReproductionConfig,
    build_qlib_subprocess_environment,
    plan_qlib_linear_reproduction,
    run_qlib_linear_reproduction,
)
from stock_research.synthetic_qlib import (
    FEATURE_COLUMNS,
    PRICE_DERIVED_FEATURES,
    THREAD_CONTROLS,
    generate_synthetic_qlib_data,
    reconstruct_price_features,
    write_canonical_csv,
    write_canonical_json,
)


def test_deterministic_generation_counts_alignment_and_panel():
    first = generate_synthetic_qlib_data()
    second = generate_synthetic_qlib_data()
    pd.testing.assert_frame_equal(first.features, second.features)
    pd.testing.assert_frame_equal(first.labels, second.labels)
    pd.testing.assert_frame_equal(first.prices, second.prices)
    assert first.features.shape == (6000, 14)
    assert first.labels.shape == (6000, 5)
    assert first.qlib_panel.shape == (6000, 11)
    assert first.qlib_panel.index.names == ["datetime", "instrument"]
    assert list(first.qlib_panel.columns) == [
        *(("feature", name) for name in FEATURE_COLUMNS),
        ("label", "forward_1d_return"),
    ]
    merged = first.labels.merge(
        first.prices.rename(columns={
            "date": "label_end_date", "adjusted_close": "end_price"
        }),
        on=["ticker", "label_end_date"],
    ).merge(
        first.prices.rename(columns={
            "date": "as_of_date", "adjusted_close": "start_price"
        }),
        on=["ticker", "as_of_date"],
    )
    expected = merged["end_price"] / merged["start_price"] - 1
    np.testing.assert_allclose(
        merged["forward_return"], expected, rtol=0, atol=2e-16
    )


def test_every_price_feature_reconstructs_from_history_through_each_date():
    bundle = generate_synthetic_qlib_data()
    for observation_date, stored in bundle.features.groupby(
        "as_of_date", sort=True
    ):
        reconstructed = reconstruct_price_features(
            bundle.prices, bundle.universe, observation_date
        )
        expected = stored.sort_values("ticker", kind="mergesort")
        assert reconstructed["ticker"].tolist() == expected["ticker"].tolist()
        np.testing.assert_allclose(
            reconstructed[list(PRICE_DERIVED_FEATURES)].to_numpy(),
            expected[list(PRICE_DERIVED_FEATURES)].to_numpy(),
            rtol=0,
            atol=1e-14,
        )


def test_missing_policy_reject_and_canonical_serialization(tmp_path):
    bundle = generate_synthetic_qlib_data()
    broken = bundle.features.copy()
    broken.loc[0, FEATURE_COLUMNS[0]] = np.nan
    with pytest.raises(ResearchValidationError, match="nonfinite_numeric"):
        validate_feature_panel(broken)

    csv_path = write_canonical_csv(bundle.features.head(2), tmp_path / "data.csv")
    raw = csv_path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
    assert raw == write_canonical_csv(
        bundle.features.head(2), tmp_path / "again.csv"
    ).read_bytes()
    json_path = write_canonical_json({"z": 1.25, "a": "x"}, tmp_path / "data.json")
    assert json_path.read_bytes().endswith(b"\n")
    assert json.loads(json_path.read_text(encoding="utf-8")) == {"a": "x", "z": 1.25}


def _fake_verified_environment(tmp_path: Path) -> tuple[Path, Path]:
    interpreter = tmp_path / "python.exe"
    interpreter.write_bytes(b"fake")
    lock = tmp_path / "freeze.txt"
    lock.write_text("pyqlib==0.9.7\n", encoding="utf-8")
    report = tmp_path / "environment.json"
    report.write_text(json.dumps({
        "status": "verified",
        "environment_fingerprint": "a" * 64,
        "resolved_lock": str(lock),
        "interpreter": str(interpreter),
        "packages": ["pyqlib==0.9.7"],
        "import_results": {
            "qlib": {"ok": True, "version": "0.9.7"},
            "lightgbm": {"ok": True, "version": "4.6.0"},
            "numpy": {"ok": True, "version": "2.0.2"},
            "pandas": {"ok": True, "version": "2.2.3"},
            "qlib.contrib.data.handler": {"ok": True, "version": None},
            "qlib.contrib.model.linear": {"ok": True, "version": None},
        },
    }), encoding="utf-8")
    return interpreter, report


def test_dry_run_plan_is_write_free_and_import_isolated(tmp_path):
    interpreter, report = _fake_verified_environment(tmp_path)
    output = tmp_path / "never-created"
    before = set(sys.modules)
    plan = plan_qlib_linear_reproduction(QlibLinearReproductionConfig(
        qlib_interpreter=interpreter,
        environment_report=report,
        output_root=output,
        batch_id="dry-run",
    ))
    new_modules = set(sys.modules).difference(before)
    assert "qlib" not in new_modules
    assert "lightgbm" not in new_modules
    assert not output.exists()
    assert len(plan.commands) == 2
    assert plan.row_counts == {"features": 6000, "labels": 6000, "test": 1200}
    assert plan.commands[0][0] == str(interpreter)


def test_thread_environment_and_environment_mismatch(tmp_path):
    base = {"KEEP": "yes", **{name: "99" for name in THREAD_CONTROLS}}
    built = build_qlib_subprocess_environment(base)
    assert built["KEEP"] == "yes"
    assert {name: built[name] for name in THREAD_CONTROLS} == THREAD_CONTROLS

    interpreter, report = _fake_verified_environment(tmp_path)
    raw = json.loads(report.read_text())
    raw["status"] = "specified_blocked"
    report.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="not verified"):
        plan_qlib_linear_reproduction(QlibLinearReproductionConfig(
            qlib_interpreter=interpreter,
            environment_report=report,
        ))


def test_preexisting_output_is_rejected_at_execution_boundary(tmp_path):
    interpreter, report = _fake_verified_environment(tmp_path)
    output = tmp_path / "output"
    (output / "stale").mkdir(parents=True)
    config = QlibLinearReproductionConfig(
        qlib_interpreter=interpreter, environment_report=report,
        output_root=output, batch_id="stale",
    )
    with pytest.raises(ValueError, match="preexisting batch directory"):
        run_qlib_linear_reproduction(config)


def test_research_v2_all_test_dates_preserve_syn030_diagnostics():
    bundle = generate_synthetic_qlib_data()
    eligible_count = 0
    diagnostics = []
    for observation_date in pd.bdate_range(
        bundle.split.test.start, bundle.split.test.end
    ):
        result = calculate_research_v2(
            ResearchV2Inputs(
                bundle.universe, bundle.prices, bundle.fundamentals
            ),
            ResearchV2Config(ranking_date=observation_date.date()),
        )
        eligible_count += len(result.rankings)
        diagnostics.append(result.eligibility.loc[
            ~result.eligibility["eligible"]
        ])
    ineligible = pd.concat(diagnostics, ignore_index=True)
    assert eligible_count == 1160
    assert len(ineligible) == 40
    assert set(ineligible["ticker"]) == {"SYN030"}
    assert set(ineligible["reason_code"]) == {"INVALID_DEBT_TO_EQUITY"}


def test_product_failure_retains_honest_failed_manifest(tmp_path, monkeypatch):
    interpreter, report = _fake_verified_environment(tmp_path)
    output = tmp_path / "output"

    def fail_after_directory_creation(**kwargs):
        directory = kwargs["batch_directory"] / "run-01"
        directory.mkdir()
        (directory / "runner_request.json").write_text(json.dumps({
            "run_id": "11111111-1111-4111-8111-111111111111"
        }), encoding="utf-8")
        raise RuntimeError("deliberate fixture failure")

    monkeypatch.setattr(reproduction, "_execute_run", fail_after_directory_creation)
    with pytest.raises(RuntimeError, match="deliberate fixture failure"):
        run_qlib_linear_reproduction(QlibLinearReproductionConfig(
            qlib_interpreter=interpreter,
            environment_report=report,
            output_root=output,
            batch_id="failure",
        ))
    failed = json.loads(
        (output / "failure/run-01/experiment_manifest.json").read_text()
    )
    assert failed["status"] == "failed"
    assert "deliberate fixture failure" in failed["failure_reason"]
