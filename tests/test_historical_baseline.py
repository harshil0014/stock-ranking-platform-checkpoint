from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stock_ranker.historical_baseline import (
    ADAPTER_VERSION,
    BUNDLE_FILES,
    PRICE_SERIES,
    load_historical_baseline_bundle,
    normalize_provider_history,
    prepare_historical_baseline,
    provider_symbol,
)
from stock_ranker.website import analyze_website_request


def _universe(symbols: tuple[str, ...] = ("ALPHA", "M&M")) -> pd.DataFrame:
    return pd.DataFrame([
        {"Symbol": symbol, "Company Name": f"{symbol} Limited", "Industry": "Industrials"}
        for symbol in symbols
    ])


def _snapshot(symbols: tuple[str, ...] = ("ALPHA", "M&M")) -> pd.DataFrame:
    return pd.DataFrame({"ticker": list(symbols), "close": [200.0] * len(symbols)})


def _history(scale: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame({
        "date": ["2020-01-02", "2021-08-06", "2023-08-07", "2025-08-07", "2026-08-07"],
        "raw_close": np.array([90, 100, 125, 160, 200], dtype=float) * scale,
        "adjusted_close": np.array([90, 100, 125, 160, 200], dtype=float) * scale,
    })


def _prepared(histories=None):
    histories = histories or {"ALPHA": _history(), "M&M": _history()}
    return prepare_historical_baseline(_universe(), _snapshot(), histories)


def test_exact_symbol_mapping_including_punctuation() -> None:
    assert provider_symbol("RELIANCE") == "RELIANCE.NS"
    assert provider_symbol("M&M") == "M&M.NS"
    assert provider_symbol("BAJAJ-AUTO") == "BAJAJ-AUTO.NS"
    with pytest.raises(ValueError, match="whitespace"):
        provider_symbol("BAD SYMBOL")


def test_date_normalization_and_duplicate_dates() -> None:
    frame = _history()
    frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.tz_convert("Asia/Kolkata")
    result = normalize_provider_history(frame)
    assert result["date"].iloc[-1] == "2026-08-07"
    duplicate = pd.concat([frame, frame.iloc[-1:]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        normalize_provider_history(duplicate)


def test_prior_anchor_dates_and_no_future_leakage() -> None:
    frame = _history()
    future = pd.DataFrame({"date": ["2025-08-08", "2026-08-08"], "raw_close": [150, 999], "adjusted_close": [150, 999]})
    result = prepare_historical_baseline(
        _universe(("ALPHA",)), _snapshot(("ALPHA",)),
        {"ALPHA": pd.concat([frame, future], ignore_index=True)},
    )
    anchor = result.anchors.iloc[0]
    assert anchor["close_1y_date"] == "2025-08-07"
    assert anchor["close_3y_date"] == "2023-08-07"
    assert anchor["close_5y_date"] == "2021-08-06"
    assert anchor["current_date"] == "2026-08-07"
    assert anchor["recorded_high_price"] == 200


def test_authoritative_history_boundary_limits_only_recorded_high_search() -> None:
    history = _history()
    history.loc[0, "adjusted_close"] = 999
    boundaries = pd.DataFrame([{
        "ticker": "ALPHA", "valid_from_date": "2021-01-01",
        "boundary_type": "EXCHANGE_LISTING_DATE",
        "evidence_source": "https://exchange.example/listing/alpha",
    }])
    result = prepare_historical_baseline(
        _universe(("ALPHA",)), _snapshot(("ALPHA",)), {"ALPHA": history},
        history_start_boundaries=boundaries,
    )
    anchor = result.anchors.iloc[0]
    assert anchor["recorded_high_date"] == "2026-08-07"
    assert anchor["recorded_high_search_start_date"] == "2021-01-01"
    assert anchor["recorded_high_search_start_basis"] == "EXCHANGE_LISTING_DATE"
    assert result.baseline_input.iloc[0]["close_5y_ago"] == 100


@pytest.mark.parametrize("column,value,message", [
    ("valid_from_date", "bad", "ISO"),
    ("valid_from_date", "2027-01-01", "after as_of_date"),
    ("evidence_source", "", "must not be blank"),
])
def test_history_boundary_contract(column: str, value: str, message: str) -> None:
    boundaries = pd.DataFrame([{
        "ticker": "ALPHA", "valid_from_date": "2021-01-01",
        "boundary_type": "EXCHANGE_LISTING_DATE",
        "evidence_source": "https://exchange.example/listing/alpha",
    }])
    boundaries.loc[0, column] = value
    with pytest.raises(ValueError, match=message):
        prepare_historical_baseline(
            _universe(("ALPHA",)), _snapshot(("ALPHA",)), {"ALPHA": _history()},
            history_start_boundaries=boundaries,
        )


@pytest.mark.parametrize(
    "histories, code",
    [
        ({"ALPHA": None, "M&M": _history()}, "PROVIDER_SYMBOL_UNAVAILABLE"),
        ({"ALPHA": _history().loc[lambda x: x.date >= "2023-01-01"], "M&M": _history()}, "INSUFFICIENT_5Y_HISTORY"),
    ],
)
def test_explicit_unavailable_and_insufficient_history(histories, code) -> None:
    result = _prepared(histories)
    alpha = result.eligibility.set_index("ticker").loc["ALPHA"]
    assert not bool(alpha["eligible"])
    assert alpha["reason_code"] == code


def test_nonfinite_and_current_mismatch_are_excluded() -> None:
    bad = _history()
    bad.loc[2, "adjusted_close"] = np.inf
    result = _prepared({"ALPHA": bad, "M&M": _history()})
    assert result.eligibility.set_index("ticker").loc["ALPHA", "reason_code"] == "NONFINITE_PRICE"
    mismatch = prepare_historical_baseline(
        _universe(("ALPHA",)), pd.DataFrame({"ticker": ["ALPHA"], "close": [250]}),
        {"ALPHA": _history()},
    )
    assert mismatch.eligibility.iloc[0]["reason_code"] == "CURRENT_PRICE_MISMATCH"
    assert mismatch.current_crosscheck.iloc[0]["status"] == "FAIL"


def _write_bundle(root: Path) -> str:
    prepared = _prepared()
    frames = {
        "baseline_input.csv": prepared.baseline_input,
        "anchor_metadata.csv": prepared.anchors,
        "eligibility.csv": prepared.eligibility,
        "symbol_map.csv": prepared.symbol_map,
        "current_crosscheck.csv": prepared.current_crosscheck,
        "historical_prices.csv": pd.DataFrame({"ticker": ["ALPHA"], "date": ["2026-08-07"], "adjusted_close": [200]}),
        "reliance_donor_audit.csv": pd.DataFrame({"event": ["bonus_1_to_1"]}),
    }
    for name, frame in frames.items():
        frame.to_csv(root / name, index=False, lineterminator="\n")
    (root / "reliance_donor_audit.json").write_text(json.dumps({"status": "ADJUSTMENT_VERIFIED"}) + "\n", encoding="utf-8")
    metadata = {
        "adapter_version": ADAPTER_VERSION, "as_of_date": "2026-08-07",
        "reliance_audit_status": "ADJUSTMENT_VERIFIED", "selected_series": PRICE_SERIES,
    }
    (root / "acquisition_metadata.json").write_text(json.dumps(metadata) + "\n", encoding="utf-8")
    (root / "marketdata_dependency_lock.txt").write_text("yfinance==1.5.1\n", encoding="utf-8")
    (root / "marketdata_environment_report.json").write_text("{}\n", encoding="utf-8")
    (root / "security_history_boundaries.csv").write_text(
        "ticker,valid_from_date,boundary_type,evidence_source\n", encoding="utf-8"
    )
    inventory = []
    for name in sorted(BUNDLE_FILES):
        path = root / name
        inventory.append({"path": name, "sha256": sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size})
    fingerprint = sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (root / "bundle_manifest.json").write_text(json.dumps({"schema_version": 1, "bundle_fingerprint": fingerprint, "files": inventory}), encoding="utf-8")
    return fingerprint


def test_bundle_fingerprint_is_deterministic_and_tampering_fails(tmp_path: Path) -> None:
    first = tmp_path / "a"; second = tmp_path / "b"
    first.mkdir(); second.mkdir()
    assert _write_bundle(first) == _write_bundle(second)
    assert load_historical_baseline_bundle(first).fingerprint == load_historical_baseline_bundle(second).fingerprint
    (first / "baseline_input.csv").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_historical_baseline_bundle(first)


def test_prepared_real_website_dispatch_explanations_export_and_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fingerprint = _write_bundle(tmp_path)
    monkeypatch.setattr("stock_ranker.website.PREPARED_REAL_BASELINE_BUNDLE", tmp_path)
    response = analyze_website_request({"input_source": "prepared_real_baseline", "method": "baseline_v1"})
    assert len(response["results"]) == 2
    assert response["provenance"]["data_mode"] == "REAL HISTORICAL PRICE RESEARCH"
    assert response["provenance"]["bundle_fingerprint"] == fingerprint
    assert "close_5y_date" in response["results"][0]["explanation"]["data_derived"]
    assert response["export_filename"] == "real_nifty50_baseline_v1_2026-08-07.csv"
    exported = pd.read_csv(pd.io.common.StringIO(response["export_csv"]))
    assert {"bundle_fingerprint", "adjustment_series", "baseline_score", "close_5y_date"}.issubset(exported.columns)
    assert any("survivorship" in warning for warning in response["provenance"]["warnings"])


def test_existing_synthetic_regressions_unchanged() -> None:
    baseline = analyze_website_request({"method": "baseline_v1", "use_synthetic_sample": True})
    v2 = analyze_website_request({"method": "research_v2", "use_synthetic_sample": True, "ranking_date": "2026-06-30"})
    assert len(baseline["results"]) == 18
    assert sum(row["eligible"] for row in v2["results"]) == 17
