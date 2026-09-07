from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


RUNNER = Path(__file__).parents[1] / "marketdata" / "runners" / "backfill_bse_history.py"
SPEC = importlib.util.spec_from_file_location("backfill_bse_history", RUNNER)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def _history(last_close: float = 105.0, last_adjusted: float = 105.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Close": [90.0, 100.0, last_close],
            "Adj Close": [88.0, 98.0, last_adjusted],
        },
        index=pd.to_datetime(
            [
                "2024-09-02 10:00:00+05:30",
                "2025-09-02 10:00:00+05:30",
                "2026-09-02 10:00:00+05:30",
            ]
        ),
    )


def test_bse_provider_code_uses_exact_numeric_scrip_code() -> None:
    assert module.bse_provider_code("504240") == "504240.BO"
    assert module.bse_provider_code(504240) == "504240.BO"
    assert module.bse_provider_code("504240.0") == "504240.BO"
    with pytest.raises(ValueError, match="numeric official scrip code"):
        module.bse_provider_code("DELTON")


def test_download_validation_accepts_matching_official_bse_close() -> None:
    normalized, audit = module.validate_downloaded_history(
        _history(), trade_date="2026-09-02", official_price=105.0
    )
    assert list(normalized.columns) == ["date", "raw_close", "adjusted_close"]
    assert normalized.iloc[-1]["date"] == "2026-09-02"
    assert audit["provider_raw_close"] == 105.0
    assert audit["current_relative_difference"] == 0.0


def test_download_validation_rejects_wrong_security_price() -> None:
    with pytest.raises(ValueError, match="differs from accepted BSE close"):
        module.validate_downloaded_history(
            _history(last_close=150.0, last_adjusted=150.0),
            trade_date="2026-09-02",
            official_price=105.0,
        )


def test_download_validation_rejects_stale_terminal_observation() -> None:
    frame = _history().iloc[:2].copy()
    with pytest.raises(ValueError, match="calendar days"):
        module.validate_downloaded_history(
            frame,
            trade_date="2026-09-02",
            official_price=100.0,
        )


def test_bse_cache_filename_matches_existing_live_market_contract(tmp_path: Path) -> None:
    target = tmp_path / "BSE-504240.csv"
    normalized, _ = module.validate_downloaded_history(
        _history(), trade_date="2026-09-02", official_price=105.0
    )
    module._atomic_csv(normalized, target)
    assert target.is_file()
    assert module._cache_covers(target, "2026-09-02")


def test_existing_history_is_extended_and_overlaps_are_deduplicated(tmp_path: Path) -> None:
    target = tmp_path / "BSE-504240.csv"
    existing = pd.DataFrame({
        "date": ["2024-01-02", "2025-01-02"],
        "raw_close": [10.0, 20.0],
        "adjusted_close": [10.0, 20.0],
    })
    incoming = pd.DataFrame({
        "date": ["2025-01-02", "2026-01-02"],
        "raw_close": [21.0, 30.0],
        "adjusted_close": [21.0, 30.0],
    })
    module._atomic_csv(existing, target)
    merged = module.merge_cached_history(target, incoming)
    assert merged["date"].tolist() == ["2024-01-02", "2025-01-02", "2026-01-02"]
    assert merged.loc[merged["date"].eq("2025-01-02"), "raw_close"].iat[0] == 21.0
