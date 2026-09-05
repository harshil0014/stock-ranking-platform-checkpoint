from __future__ import annotations

import pandas as pd
import pytest

from stock_ranker.bulk_classification import (
    BULK_CLASSIFICATION_VERSION,
    build_bulk_classifications,
    validate_bulk_classifications,
)


def _candidates() -> pd.DataFrame:
    return pd.DataFrame([
        {"ticker": "AAA", "isin": "INE000A01001", "primary_exchange": "NSE", "exchange_security_id": "AAA"},
        {"ticker": "BSE-500001", "isin": "INE000A01002", "primary_exchange": "BSE", "exchange_security_id": "500001"},
    ])


def _official(isin: str = "INE000A01002", code: str = "500001") -> pd.DataFrame:
    return pd.DataFrame([{"SCRIP_CD": code, "ISIN_NUMBER": isin, "scrip_id": "BETA",
                          "Segment": "Equity", "Scrip_Name": "Beta Ltd", "GROUP": "X"}])


def _yahoo() -> tuple[pd.DataFrame, pd.DataFrame]:
    universe = pd.DataFrame([
        {"symbol": "AAA.NS", "exchange": "NSI", "quoteType": "EQUITY"},
        {"symbol": "BETA.BO", "exchange": "BSE", "quoteType": "EQUITY"},
    ])
    sectors = universe.assign(sector=["Technology", "Industrials"])
    return universe, sectors


def test_exact_nse_and_official_bse_bridge_are_accepted_deterministically() -> None:
    universe, sectors = _yahoo()
    first = build_bulk_classifications(
        _candidates(), official_bse=_official(), yahoo_universe=universe,
        yahoo_sector_memberships=sectors, retrieved_at="2026-08-23T00:00:00+00:00",
    )
    second = build_bulk_classifications(
        _candidates().sample(frac=1, random_state=4), official_bse=_official(),
        yahoo_universe=universe.sample(frac=1, random_state=5),
        yahoo_sector_memberships=sectors.sample(frac=1, random_state=6),
        retrieved_at="2026-08-23T00:00:00+00:00",
    )
    assert len(first.classifications) == 2
    assert first.fingerprint == second.fingerprint
    bse = first.classifications.set_index("ticker").loc["BSE-500001"]
    assert bse["provider_symbol"] == "BETA.BO"
    assert bse["identity_method"] == "EXACT_BSE_CODE_AND_ISIN"
    assert bse["sector"] == "Industrials"


@pytest.mark.parametrize(
    ("official", "expected"),
    [(_official(isin="INE-WRONG"), "ISIN_CONFLICT"),
     (_official(code="500999"), "OFFICIAL_BSE_LOOKUP_NOT_FOUND")],
)
def test_bse_code_or_isin_conflicts_remain_unresolved(official: pd.DataFrame, expected: str) -> None:
    universe, sectors = _yahoo()
    result = build_bulk_classifications(
        _candidates().iloc[[1]], official_bse=official, yahoo_universe=universe,
        yahoo_sector_memberships=sectors, retrieved_at="2026-08-23T00:00:00+00:00",
    )
    assert result.classifications.empty
    assert result.audit.iloc[0]["reason"] == expected


def test_missing_symbol_and_ambiguous_sector_are_rejected() -> None:
    universe, sectors = _yahoo()
    ambiguous = pd.concat([sectors, sectors.loc[sectors.symbol.eq("BETA.BO")].assign(sector="Utilities")])
    result = build_bulk_classifications(
        _candidates().iloc[[1]], official_bse=_official(), yahoo_universe=universe,
        yahoo_sector_memberships=ambiguous, retrieved_at="2026-08-23T00:00:00+00:00",
    )
    assert result.classifications.empty
    assert result.audit.iloc[0]["reason"] == "YAHOO_MULTIPLE_SECTOR_MEMBERSHIPS"
    missing = _official().assign(scrip_id="")
    result = build_bulk_classifications(
        _candidates().iloc[[1]], official_bse=missing, yahoo_universe=universe,
        yahoo_sector_memberships=sectors, retrieved_at="2026-08-23T00:00:00+00:00",
    )
    assert result.audit.iloc[0]["reason"] == "SYMBOL_MISSING_OR_MALFORMED"


def test_missing_exact_yahoo_symbol_remains_unresolved() -> None:
    universe, sectors = _yahoo()
    result = build_bulk_classifications(
        _candidates().iloc[[1]], official_bse=_official(),
        yahoo_universe=universe.loc[universe.symbol.ne("BETA.BO")],
        yahoo_sector_memberships=sectors,
        retrieved_at="2026-08-23T00:00:00+00:00",
    )
    assert result.classifications.empty
    assert result.audit.iloc[0]["reason"] == "YAHOO_SYMBOL_NOT_FOUND"


def test_validator_rejects_fabricated_bse_symbol() -> None:
    universe, sectors = _yahoo()
    result = build_bulk_classifications(
        _candidates().iloc[[1]], official_bse=_official(), yahoo_universe=universe,
        yahoo_sector_memberships=sectors, retrieved_at="2026-08-23T00:00:00+00:00",
    )
    bad = result.classifications.assign(provider_symbol="WRONG.BO")
    with pytest.raises(ValueError, match="official-symbol mismatch"):
        validate_bulk_classifications(bad)


def test_product_module_does_not_import_network_providers() -> None:
    from pathlib import Path
    import stock_ranker.bulk_classification as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "import yfinance" not in source
    assert "import requests" not in source
    runner = Path(__file__).parents[1] / "marketdata/runners/acquire_bulk_classification.py"
    assert "Ticker.info" not in runner.read_text(encoding="utf-8")
    assert BULK_CLASSIFICATION_VERSION == "bulk_exact_identity_sector_v1"
