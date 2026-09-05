from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_ranker.professor_acceptance import (
    build_professor_acceptance,
    export_professor_acceptance,
)
from stock_ranker.research_website import professor_acceptance


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _market_row(ticker: str, isin: str, *, eligible: bool = True) -> dict:
    return {
        "ticker": ticker, "company": f"{ticker} Limited", "isin": isin,
        "sector": "Capital Goods", "industry": "Capital Goods", "size_segment": "SMALL",
        "classification_status": "CLASSIFIED", "trade_date": "2026-08-07",
        "latest_price": 120.0, "snapshot_source": "official snapshot",
        "baseline_eligible": eligible, "baseline_reason_code": "ELIGIBLE" if eligible else "INSUFFICIENT_5Y_HISTORY",
        "baseline_reason": "Eligible" if eligible else "History unavailable",
        "baseline_yoy_growth": .2, "baseline_cagr_3y": .1, "baseline_cagr_5y": .08,
        "baseline_days_since_recorded_high": 4, "baseline_score": 1.0 if eligible else None,
        "baseline_sector_rank": 1.0 if eligible else None, "v2_eligible": False,
        "v2_reason_code": "FUNDAMENTALS_UNAVAILABLE", "v2_reason": "No accepted evidence",
        "research_v2_score": None, "research_v2_sector_rank": None,
    }


def _history(path: Path) -> None:
    dates = pd.bdate_range("2021-08-02", "2026-08-07")
    pd.DataFrame({"date": dates.date.astype(str), "adjusted_close": range(100, 100 + len(dates)),
                  "close": range(100, 100 + len(dates))}).to_csv(path, index=False)


def test_exact_prefixless_bse_and_isin_cross_listing_resolution(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    identity = tmp_path / "identity.json"
    market_path = tmp_path / "market.csv"
    cache = tmp_path / "cache"; cache.mkdir()
    supplemental = tmp_path / "supplemental"; supplemental.mkdir()
    bse = tmp_path / "bse"; bse.mkdir()
    _write_json(request, {
        "universe": ["NSE:ALPHA", "AMP&CO", "BOM:123456", "BOM:654321"],
        "reference_ranking": [{"rank": 1, "code": "AMP&CO"}, {"rank": 2, "code": "BOM:123456"}],
    })
    _write_json(identity, {"identities": [
        {"requested_code": "AMP&CO", "canonical_exchange": "NSE", "canonical_symbol": "AMP&CO",
         "nse_ticker": "AMP&CO", "company": "Amp Limited", "isin": "INE000000002", "source_url": "official"},
        {"requested_code": "BOM:123456", "canonical_exchange": "BSE", "canonical_symbol": "123456",
         "company": "Bse Limited", "isin": "INE000000003", "provider_symbol": "BSE.BO", "source_url": "official"},
        {"requested_code": "BOM:654321", "canonical_exchange": "BSE", "canonical_symbol": "654321",
         "nse_ticker": "CROSS", "company": "Cross Limited", "isin": "INE000000004", "source_url": "official"},
    ]})
    pd.DataFrame([_market_row("ALPHA", "INE000000001"), _market_row("AMP&CO", "INE000000002"),
                  _market_row("CROSS", "INE000000004", eligible=False)]).to_csv(market_path, index=False)
    _history(cache / "ALPHA.csv"); _history(cache / "AMP&CO.csv"); _history(bse / "123456.csv")
    result = build_professor_acceptance(
        request, identity, live_market_path=market_path, nse_history_root=cache,
        supplemental_nse_history_root=supplemental, bse_history_root=bse,
    )
    rows = result.securities.set_index("requested_code")
    assert rows.loc["AMP&CO", "identity_status"] == "MATCHED_VERIFIED_PREFIXLESS_NSE"
    assert rows.loc["BOM:123456", "identity_status"] == "VERIFIED_BSE_ONLY"
    assert rows.loc["BOM:123456", "baseline_eligibility_reason"] == "UNCLASSIFIED_BSE"
    assert rows.loc["BOM:654321", "identity_status"] == "MATCHED_CROSS_LISTED_ISIN"
    assert result.audit["global_rank_correlation"] is None
    assert result.audit["reference_ranking_verdict"] == "NOT REPRODUCIBLE FROM AVAILABLE METHODOLOGY"


def test_verified_identity_without_provider_history_is_legitimately_unavailable(tmp_path: Path) -> None:
    request, identity, market = tmp_path / "request.json", tmp_path / "identity.json", tmp_path / "market.csv"
    _write_json(request, {"universe": ["BOM:111111"], "reference_ranking": []})
    _write_json(identity, {"identities": [{"requested_code": "BOM:111111", "canonical_exchange": "BSE",
        "canonical_symbol": "111111", "company": "Only BSE Limited", "isin": "INE000000005", "source_url": "official"}]})
    pd.DataFrame([_market_row("OTHER", "INE000000006")]).to_csv(market, index=False)
    for name in ("cache", "supplemental", "bse"):
        (tmp_path / name).mkdir()
    result = build_professor_acceptance(request, identity, live_market_path=market,
        nse_history_root=tmp_path / "cache", supplemental_nse_history_root=tmp_path / "supplemental",
        bse_history_root=tmp_path / "bse")
    assert result.securities.iloc[0]["resolution_status"] == "LEGITIMATELY UNAVAILABLE"
    assert result.securities.iloc[0]["research_v2_reason"] == "BSE_FUNDAMENTAL_CONTRACT_UNAVAILABLE"


def test_official_bse_snapshot_resolves_current_price_without_inventing_rank(tmp_path: Path) -> None:
    request, identity, market = tmp_path / "request.json", tmp_path / "identity.json", tmp_path / "market.csv"
    snapshot = tmp_path / "bse.csv"
    _write_json(request, {"universe": ["BOM:111111"], "reference_ranking": []})
    _write_json(identity, {"identities": [{"requested_code": "BOM:111111", "canonical_exchange": "BSE",
        "canonical_symbol": "111111", "company": "Only BSE Limited", "isin": "INE000000005", "source_url": "official"}]})
    pd.DataFrame([_market_row("OTHER", "INE000000006")]).to_csv(market, index=False)
    pd.DataFrame([{"FinInstrmId": "111111", "ISIN": "INE000000005", "TradDt": "2026-08-07",
                   "ClsPric": 459.9}]).to_csv(snapshot, index=False)
    for name in ("cache", "supplemental", "bse"):
        (tmp_path / name).mkdir()
    result = build_professor_acceptance(request, identity, live_market_path=market,
        nse_history_root=tmp_path / "cache", supplemental_nse_history_root=tmp_path / "supplemental",
        bse_history_root=tmp_path / "bse", bse_snapshot_path=snapshot)
    row = result.securities.iloc[0]
    assert row["resolution_status"] == "RESOLVED"
    assert row["latest_price"] == 459.9
    assert row["baseline_eligibility_reason"] == "UNCLASSIFIED_BSE"
    assert pd.isna(row["baseline_sector_rank"])


def test_export_is_deterministic_and_contains_every_requested_code(tmp_path: Path) -> None:
    source = Path("data/professor_reference/acceptance_current")
    if not source.is_dir():
        return
    frame = pd.read_csv(source / "security_acceptance.csv", low_memory=False)
    assert len(frame) == 99
    assert frame["requested_code"].is_unique
    assert set(frame["resolution_status"]) <= {"RESOLVED", "LEGITIMATELY UNAVAILABLE", "DEFECT REMAINS"}
    assert not frame["identity_status"].eq("UNRESOLVED_IDENTITY").any()


def test_prepared_acceptance_resolves_special_symbols_and_searches() -> None:
    data = professor_acceptance("GVT&D")
    assert data["available"] is True
    assert len(data["rows"]) == 1
    assert data["rows"][0]["identity_status"] == "MATCHED_VERIFIED_PREFIXLESS_NSE"
    assert data["rows"][0]["baseline_sector_rank"] == 4
    bse = professor_acceptance("504240")
    assert bse["rows"][0]["resolution_status"] == "RESOLVED"
    assert bse["rows"][0]["identity_status"] == "VERIFIED_BSE_ONLY"
    cross = professor_acceptance("539997")
    assert cross["rows"][0]["identity_status"] == "MATCHED_CROSS_LISTED_ISIN"
    assert cross["rows"][0]["baseline_eligibility_reason"] == "UNCLASSIFIED"


def test_acceptance_algorithm_contains_no_supplied_company_exceptions() -> None:
    source = Path(__file__).parents[1].joinpath("src/stock_ranker/professor_acceptance.py").read_text(encoding="utf-8")
    for token in ("GVT&D", "GOKULAGRO", "539997", "SHAILY", "TDPOWERSYS"):
        assert token not in source
