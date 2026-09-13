from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from stock_ranker.secondary_facts import (
    YAHOO_REQUIRED_COLUMNS,
    validate_yahoo_identity,
    validate_yahoo_observations,
    yahoo_coverage,
    yahoo_numeric_fact,
)


def _row(**changes):
    value = {column: None for column in YAHOO_REQUIRED_COLUMNS}
    value.update({
        "ticker": "RELIANCE", "isin": "INE002A01018", "primary_exchange": "NSE",
        "provider_symbol": "RELIANCE.NS", "provider_version": "1.5.1",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source_as_of": datetime.now(timezone.utc).isoformat(),
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
        "last_changed_at": datetime.now(timezone.utc).isoformat(),
        "next_check_due": datetime.now(timezone.utc).isoformat(), "freshness_status": "CURRENT",
        "identity_status": "EXCHANGE_SYMBOL_MATCH", "identity_reason": "exact",
        "returned_symbol": "RELIANCE.NS", "returned_exchange": "NSI",
        "returned_quote_type": "EQUITY", "shares_outstanding": 1.0,
    })
    value.update(changes)
    return value


def test_identity_requires_exact_symbol_exchange_and_equity_type():
    assert validate_yahoo_identity(
        provider_symbol="RELIANCE.NS", primary_exchange="NSE",
        returned_symbol="RELIANCE.NS", returned_exchange="NSI", returned_quote_type="EQUITY",
    )[0]
    for returned_symbol, exchange, quote_type in (
        ("NAN", "NYQ", "EQUITY"), ("RELIANCE.NS", "BSE", "EQUITY"),
        ("RELIANCE.NS", "NSI", "MUTUALFUND"),
    ):
        assert not validate_yahoo_identity(
            provider_symbol="RELIANCE.NS", primary_exchange="NSE",
            returned_symbol=returned_symbol, returned_exchange=exchange,
            returned_quote_type=quote_type,
        )[0]
    assert not validate_yahoo_identity(
        provider_symbol="nan", primary_exchange="BSE", returned_symbol="NAN",
        returned_exchange="NYQ", returned_quote_type="EQUITY",
    )[0]


def test_secondary_units_and_missing_values_are_not_fabricated():
    info = {"debtToEquity": 42.5, "trailingAnnualDividendYield": 0.0125,
            "missing": None, "bad": float("inf")}
    assert yahoo_numeric_fact(info, "debtToEquity", percentage_points=True) == 0.425
    assert yahoo_numeric_fact(info, "trailingAnnualDividendYield") == 0.0125
    assert yahoo_numeric_fact(info, "missing") is None
    assert yahoo_numeric_fact(info, "bad") is None


def test_rejected_identity_cannot_contribute_facts():
    row = _row(identity_status="REJECTED_IDENTITY", freshness_status="STALE",
               market_cap=100.0, shares_outstanding=None)
    with pytest.raises(ValueError, match="cannot contribute facts"):
        validate_yahoo_observations(pd.DataFrame([row]))


def test_semantic_validation_and_useful_coverage():
    accepted = _row(market_cap=100.0, company_profile="Profile", sector="Energy",
                    fifty_two_week_low=10.0, fifty_two_week_high=20.0,
                    annual_income_status="USEFUL_FACTS")
    coverage = yahoo_coverage(pd.DataFrame([accepted]))
    assert coverage["identity_accepted"] == coverage["market_cap"] == 1
    assert coverage["annual_income"] == 1
    with pytest.raises(ValueError, match="52-week low"):
        validate_yahoo_observations(pd.DataFrame([_row(fifty_two_week_low=21, fifty_two_week_high=20)]))
    with pytest.raises(ValueError, match="shares outstanding"):
        validate_yahoo_observations(pd.DataFrame([_row(shares_outstanding=-1)]))


def test_unified_refresh_dry_run_is_write_free_and_screener_disabled(tmp_path: Path):
    runner = Path(__file__).parents[1] / "marketdata/runners/refresh_company_data.py"
    completed = subprocess.run(
        [sys.executable, str(runner), "--dry-run", "--secondary-limit", "7"],
        cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0
    plan = json.loads(completed.stdout)
    assert plan["write_free"] is True
    assert "--limit" in plan["secondary"] and "7" in plan["secondary"]
    assert not list(tmp_path.iterdir())


def test_acquisition_source_preserves_canonical_nse_symbol_precedence():
    source = (Path(__file__).parents[1] / "marketdata/runners/acquire_yahoo_secondary_facts.py").read_text(encoding="utf-8")
    assert 'is_bse_only' in source
    assert 'symbol.upper().endswith(".BO")' in source
    assert 'f"{row.ticker}.NS"' in source


def test_product_layer_is_provider_free_and_scheduler_uses_unified_cli():
    root = Path(__file__).parents[1]
    product = (root / "src/stock_ranker/secondary_facts.py").read_text(encoding="utf-8")
    assert "import yfinance" not in product and "import yahoo" not in product.lower()
    scheduler = (root / "marketdata/scheduling/windows_refresh.ps1").read_text(encoding="utf-8")
    assert "refresh_company_data.py" in scheduler
    policy = json.loads((root / "marketdata/specifications/screener_reference_policy.json").read_text(encoding="utf-8"))
    assert policy["decision"] == "USER_SUPPLIED_CURRENT_REFERENCE_ALLOWED"
    assert policy["facts_may_enter_canonical_store"] is True
    assert policy["automated_acquisition_enabled"] is False
    assert policy["runtime_dependency_allowed"] is False
    assert any("historical PIT timestamps" in item for item in policy["prohibited_use"])
