from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest


RUNNER = Path(__file__).parents[1] / "marketdata" / "runners" / "backfill_bse_history.py"
SPEC = importlib.util.spec_from_file_location("backfill_bse_history", RUNNER)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

RUNNER_DIR = RUNNER.parent
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))


def _load_runner(name: str):
    spec = importlib.util.spec_from_file_location(name, RUNNER_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


official_recovery = _load_runner("build_bse_official_history_recovery")
udiff_downloader = _load_runner("download_bse_udiff_bhavcopies")
udiff_cohort = _load_runner("download_bse_udiff_cohort")


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


def test_stale_history_requires_and_records_current_reference() -> None:
    frame = _history().iloc[:2].copy()
    normalized, audit = module.validate_downloaded_history(
        frame,
        trade_date="2026-09-02",
        official_price=105.0,
        current_reference_price=106.0,
    )
    assert normalized.iloc[-1]["date"] == "2025-09-02"
    assert audit["terminal_freshness"] == "STALE_CURRENT_REFERENCE_ONLY"
    assert audit["current_reference_authority"] == "SCREENER_PREMIUM"


def test_cache_sidecar_makes_stale_validated_history_resumable(tmp_path: Path) -> None:
    target = tmp_path / "BSE-504240.csv"
    normalized, audit = module.validate_downloaded_history(
        _history().iloc[:2],
        trade_date="2026-09-02",
        official_price=105.0,
        current_reference_price=106.0,
    )
    module._atomic_csv(normalized, target)
    module._atomic_json(
        {
            **audit,
            "trade_date": "2026-09-02",
            "accepted_for_current_reference": True,
            "validation_status": "ACCEPTED",
            "csv_sha256": __import__("hashlib").sha256(target.read_bytes()).hexdigest(),
        },
        module._history_metadata_path(target),
    )
    assert module._cache_covers(target, "2026-09-02")
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert not module._cache_covers(target, "2026-09-02")


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


def test_official_bonus_terms_do_not_require_a_nearby_trade(tmp_path: Path) -> None:
    factor, error = official_recovery.action_factor(
        {
            "bse_code": "501270", "event_type": "BONUS",
            "ex_date": "09 Jan 2026", "purpose": "Bonus issue 1:10",
        },
        [{"date": "2022-04-04", "close": 1.34, "raw_close": 1.34, "adjusted_close": 1.34}],
        {}, tmp_path,
    )
    assert error == ""
    assert factor is not None
    assert factor["factor"] == pytest.approx(10 / 11)
    assert factor["prior_trade_date"] == ""


def test_actions_outside_retained_history_are_ignored() -> None:
    first, last = pd.Timestamp("2025-01-01").date(), pd.Timestamp("2026-09-07").date()
    assert not official_recovery.action_affects_observed_history(
        {"ex_date": "31 Dec 2024"}, first, last
    )
    assert official_recovery.action_affects_observed_history(
        {"ex_date": "21 Aug 2026"}, first, last
    )
    assert not official_recovery.action_affects_observed_history(
        {"ex_date": "10 Sep 2026"}, first, last
    )


def test_udiff_no_record_html_requires_bse_identity() -> None:
    assert udiff_downloader.is_bse_no_record_html(
        b"<!doctype html><title>BSE India</title>BSE Limited"
    )
    assert not udiff_downloader.is_bse_no_record_html(
        b"<!doctype html><title>generic proxy error</title>"
    )


def test_udiff_cohort_requires_exact_code_isin_mapping(tmp_path: Path) -> None:
    path = tmp_path / "cohort.csv"
    path.write_text("bse_code,isin\n544400,INE0MV001018\n", encoding="utf-8")
    assert udiff_cohort.load_cohort(path) == {"544400": "INE0MV001018"}
    path.write_text(
        "bse_code,isin\n544400,INE0MV001018\n544400,INE999A01001\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="multiple ISINs"):
        udiff_cohort.load_cohort(path)
