from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import pytest

from stock_ranker.live_market import (
    apply_official_segments,
    build_latest_snapshot,
    combine_live_market,
    load_index_membership,
    load_live_market_bundle,
    load_official_equity_universe,
    write_live_bundle,
)


def _universe_csv(path: Path) -> Path:
    pd.DataFrame([
        {"SYMBOL": "AAA", "NAME OF COMPANY": "Alpha Auto", "SERIES": "EQ", "DATE OF LISTING": "01-JAN-2000", "PAID UP VALUE": 10, "MARKET LOT": 1, "ISIN NUMBER": "INE000A01001", "FACE VALUE": 10},
        {"SYMBOL": "BBB", "NAME OF COMPANY": "Beta Bank", "SERIES": "BE", "DATE OF LISTING": "02-FEB-2010", "PAID UP VALUE": 10, "MARKET LOT": 1, "ISIN NUMBER": "INE000B01001", "FACE VALUE": 10},
        {"SYMBOL": "CCC", "NAME OF COMPANY": "Core Care", "SERIES": "BZ", "DATE OF LISTING": "03-MAR-2020", "PAID UP VALUE": 10, "MARKET LOT": 1, "ISIN NUMBER": "INE000C01001", "FACE VALUE": 10},
        {"SYMBOL": "ETF", "NAME OF COMPANY": "An ETF", "SERIES": "EQMF", "DATE OF LISTING": "04-APR-2020", "PAID UP VALUE": 10, "MARKET LOT": 1, "ISIN NUMBER": "INF000X01001", "FACE VALUE": 10},
    ]).to_csv(path, index=False, lineterminator="\n")
    return path


def _membership(path: Path, ticker: str, company: str, isin: str, industry: str) -> Path:
    pd.DataFrame([{"Company Name": company, "Industry": industry, "Symbol": ticker, "Series": "EQ", "ISIN Code": isin}]).to_csv(path, index=False)
    return path


def _bhavcopy(path: Path, trade_date: str = "2026-08-07") -> Path:
    rows = []
    for ticker, series, isin, close in (("AAA", "EQ", "INE000A01001", 110), ("BBB", "BE", "INE000B01001", 90)):
        rows.append({
            "TradDt": trade_date, "BizDt": trade_date, "Sgmt": "CM", "Src": "NSE",
            "FinInstrmTp": "STK", "FinInstrmId": 1, "ISIN": isin, "TckrSymb": ticker,
            "SctySrs": series, "XpryDt": "", "FininstrmActlXpryDt": "", "StrkPric": "",
            "OptnTp": "", "FinInstrmNm": ticker, "OpnPric": close - 2, "HghPric": close + 2,
            "LwPric": close - 3, "ClsPric": close, "LastPric": close, "PrvsClsgPric": 100,
            "UndrlygPric": "", "SttlmPric": close, "OpnIntrst": "", "ChngInOpnIntrst": "",
            "TtlTradgVol": 1000, "TtlTrfVal": 100000, "TtlNbOfTxsExctd": 100,
            "SsnId": "F1", "NewBrdLotQty": 1, "Rmks": "", "Rsvd1": "", "Rsvd2": "", "Rsvd3": "", "Rsvd4": "",
        })
    content = pd.DataFrame(rows).to_csv(index=False, lineterminator="\n").encode()
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("BhavCopy.csv", content)
    return path


def _prepared(tmp_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Path]]:
    universe = load_official_equity_universe(_universe_csv(tmp_path / "equity.csv"))
    files = {}
    specs = {
        "LARGE": ("AAA", "Alpha Auto", "INE000A01001", "Automobile and Auto Components"),
        "MID": ("BBB", "Beta Bank", "INE000B01001", "Financial Services"),
        "SMALL": ("OUTSIDE", "Outside", "INE999Z01001", "Healthcare"),
        "MICRO": ("OUT2", "Outside 2", "INE999Y01001", "Information Technology"),
    }
    memberships = {}
    for segment, values in specs.items():
        files[segment] = _membership(tmp_path / f"{segment}.csv", *values)
        memberships[segment] = load_index_membership(files[segment], segment)
    return apply_official_segments(universe, memberships), universe, files


def test_universe_keeps_main_board_equity_series_and_excludes_fund_like_series(tmp_path: Path) -> None:
    universe = load_official_equity_universe(_universe_csv(tmp_path / "equity.csv"))
    assert universe["ticker"].tolist() == ["AAA", "BBB", "CCC"]
    assert universe["series"].tolist() == ["EQ", "BE", "BZ"]
    assert "ETF" not in set(universe["ticker"])


def test_official_memberships_are_exact_and_other_nse_remains_unclassified(tmp_path: Path) -> None:
    classified, _, _ = _prepared(tmp_path)
    rows = classified.set_index("ticker")
    assert rows.loc["AAA", "size_segment"] == "LARGE"
    assert rows.loc["BBB", "size_segment"] == "MID"
    assert rows.loc["CCC", "size_segment"] == "OTHER NSE"
    assert rows.loc["AAA", "sector"] == "Automobile and Auto Components"
    assert rows.loc["CCC", "classification_status"] == "UNCLASSIFIED"


def test_overlapping_segment_membership_is_rejected(tmp_path: Path) -> None:
    classified, universe, files = _prepared(tmp_path)
    del classified
    memberships = {segment: load_index_membership(path, segment) for segment, path in files.items()}
    memberships["MID"] = memberships["LARGE"].assign(size_segment="MID")
    with pytest.raises(ValueError, match="overlap"):
        apply_official_segments(universe, memberships)


def test_latest_snapshot_keeps_missing_stock_visible_and_calculates_day_move(tmp_path: Path) -> None:
    universe, _, _ = _prepared(tmp_path)
    snapshot, metadata = build_latest_snapshot(universe, _bhavcopy(tmp_path / "bhav.zip"))
    rows = snapshot.set_index("ticker")
    assert metadata["matched_count"] == 2
    assert metadata["missing_count"] == 1
    assert rows.loc["AAA", "day_change_pct"] == pytest.approx(10)
    assert rows.loc["CCC", "snapshot_status"] == "PRICE_UNAVAILABLE"
    assert metadata["freshness"] in {"LATEST TRADING SNAPSHOT", "STALE SNAPSHOT"}


def test_old_snapshot_is_labelled_stale_not_current(tmp_path: Path) -> None:
    universe, _, _ = _prepared(tmp_path)
    _, metadata = build_latest_snapshot(universe, _bhavcopy(tmp_path / "old.zip", "2020-01-02"))
    assert metadata["freshness"] == "STALE SNAPSHOT"
    assert metadata["age_calendar_days"] > 3


def test_combine_gates_models_without_fabricating_values(tmp_path: Path) -> None:
    universe, _, _ = _prepared(tmp_path)
    snapshot, _ = build_latest_snapshot(universe, _bhavcopy(tmp_path / "bhav.zip"))
    baseline = pd.DataFrame([{"ticker": "AAA", "company": "Alpha Auto", "sector": "Automobile and Auto Components", "as_of_date": "2026-08-07", "current_price": 110, "close_1y_ago": 100, "close_3y_ago": 80, "close_5y_ago": 60, "ath_date": "2026-08-07", "yoy_growth": .1, "cagr_3y": .1, "cagr_5y": .1, "days_since_recorded_high": 0, "yoy_rank": 1, "cagr_3y_rank": 1, "cagr_5y_rank": 1, "recorded_high_recency_rank": 1, "baseline_score": 1, "sector_rank": 1, "method_version": "baseline_v1_equal_rank_mean"}])
    base_elig = pd.DataFrame([{"ticker": "AAA", "eligible": True, "reason_code": "ELIGIBLE", "reason": "ok"}])
    v2 = pd.DataFrame([{
        "ticker": "AAA", "company": "Alpha Auto", "sector": "Automobile and Auto Components",
        "ranking_date": "2026-08-07", "return_1y": .2, "cagr_3y": .3, "cagr_5y": .4,
        "days_since_recorded_high": 5, "annualized_volatility_1y": .25,
        "max_drawdown_3y": -.2, "roce": .18, "debt_to_equity": .5,
        "profit_growth_yoy": .12, "research_v2_score": 70, "sector_rank": 1,
        "eligible": True, "method_version": "research_v2_point_in_time_weighted",
    }])
    v2_elig = pd.DataFrame([{"ticker": "AAA", "eligible": True, "reason_code": "ELIGIBLE", "reason": "ok"}])
    market = combine_live_market(universe, snapshot, baseline_rankings=baseline, baseline_eligibility=base_elig, v2_rankings=v2, v2_eligibility=v2_elig)
    rows = market.set_index("ticker")
    assert bool(rows.loc["AAA", "baseline_eligible"])
    assert rows.loc["AAA", "v2_reason_code"] == "ELIGIBLE"
    assert rows.loc["AAA", "baseline_cagr_3y"] == pytest.approx(.1)
    assert rows.loc["AAA", "cagr_3y"] == pytest.approx(.3)
    assert rows.loc["AAA", "baseline_days_since_recorded_high"] == 0
    assert rows.loc["AAA", "days_since_recorded_high"] == 5
    assert not any(column.endswith(("_x", "_y")) for column in market.columns)
    assert rows.loc["BBB", "baseline_reason_code"] == "PRICE_HISTORY_UNAVAILABLE"
    assert rows.loc["CCC", "baseline_reason_code"] == "UNCLASSIFIED"
    assert pd.isna(rows.loc["BBB", "baseline_score"])


def test_bundle_fingerprint_validates_and_detects_mutation(tmp_path: Path) -> None:
    universe, _, files = _prepared(tmp_path)
    snapshot, metadata = build_latest_snapshot(universe, _bhavcopy(tmp_path / "bhav.zip"))
    market = combine_live_market(universe, snapshot)
    sources = {"universe": tmp_path / "equity.csv", **files, "bhav": tmp_path / "bhav.zip"}
    result = write_live_bundle(market, tmp_path / "bundle", snapshot_metadata=metadata, source_files=sources, acquisition_started_at=datetime.now().isoformat(), acquisition_completed_at=datetime.now().isoformat(), history_attempted=0, history_acquired=0, history_failed=3)
    loaded = load_live_market_bundle(result.path)
    assert loaded.fingerprint == result.fingerprint
    (result.path / "live_market.csv").write_text("corrupt\n", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact mismatch"):
        load_live_market_bundle(result.path)


def test_accepted_scoring_modules_are_only_called_not_reimplemented() -> None:
    source = (Path(__file__).parents[1] / "marketdata/runners/prepare_live_market.py").read_text(encoding="utf-8")
    assert "calculate_baseline_rankings(prepared.baseline_input)" in source
    assert "load_real_research_v2_bundle(ACCEPTED_V2)" in source
    assert "yf.Ticker(provider_symbol(ticker)).history" in source
    assert "fuzzy" not in source.lower()


def test_history_cache_hit_is_resumable_without_importing_provider(tmp_path: Path) -> None:
    import importlib.util

    runner_path = Path(__file__).parents[1] / "marketdata/runners/prepare_live_market.py"
    spec = importlib.util.spec_from_file_location("prepare_live_market_test", runner_path)
    assert spec and spec.loader
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    (tmp_path / "AAA.csv").write_text("date,raw_close,adjusted_close\n2026-08-07,1,1\n", encoding="utf-8")
    assert runner._fetch_one("AAA", tmp_path, 2) == (True, "CACHE_HIT")


def test_provider_failure_is_bounded_and_does_not_create_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util
    import types

    calls = []
    class FailedTicker:
        def __init__(self, symbol: str) -> None:
            calls.append(symbol)
        def history(self, **kwargs: object) -> pd.DataFrame:
            raise RuntimeError("offline")
    monkeypatch.setitem(__import__("sys").modules, "yfinance", types.SimpleNamespace(Ticker=FailedTicker))
    runner_path = Path(__file__).parents[1] / "marketdata/runners/prepare_live_market.py"
    spec = importlib.util.spec_from_file_location("prepare_live_market_failure_test", runner_path)
    assert spec and spec.loader
    runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
    ok, reason = runner._fetch_one("AAA", tmp_path, 2)
    assert ok is False and "RuntimeError: offline" in reason
    assert calls == ["AAA.NS", "AAA.NS"]
    assert not (tmp_path / "AAA.csv").exists()
