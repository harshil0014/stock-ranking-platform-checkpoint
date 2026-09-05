"""Validated secondary-provider observations for broad company-page coverage.

The product layer does not import provider SDKs. Acquisition runners write the
canonical files validated here. Secondary evidence never overrides official
identity, exchange prices, audited filings, or Research V2 inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


YAHOO_OBSERVATION_VERSION = "yahoo_secondary_facts_v1"
YAHOO_REQUIRED_COLUMNS = (
    "ticker", "isin", "primary_exchange", "provider_symbol", "provider_version",
    "retrieved_at", "source_as_of", "last_checked_at", "last_changed_at",
    "next_check_due", "freshness_status", "identity_status", "identity_reason",
    "returned_symbol", "returned_exchange", "returned_quote_type", "returned_name",
    "currency", "sector", "industry", "company_profile", "market_cap",
    "shares_outstanding", "trailing_pe", "price_to_book", "trailing_eps",
    "book_value", "dividend_yield_decimal", "beta", "fifty_two_week_high",
    "fifty_two_week_low", "return_on_equity", "debt_to_equity_decimal",
    "revenue_growth", "earnings_growth", "operating_margin", "profit_margin",
    "annual_income_status", "quarterly_income_status", "balance_sheet_status",
    "cash_flow_status", "corporate_actions_status", "holder_data_status",
    "error_code", "error_message",
)


@dataclass(frozen=True)
class YahooSecondaryBundle:
    observations: pd.DataFrame
    financial_facts: pd.DataFrame
    corporate_actions: pd.DataFrame
    manifest: dict[str, Any]


def validate_yahoo_identity(
    *, provider_symbol: str, primary_exchange: str, returned_symbol: Any,
    returned_exchange: Any, returned_quote_type: Any,
) -> tuple[bool, str]:
    """Require an exact exchange security match before accepting any facts."""

    expected_exchange = {"NSE": "NSI", "BSE": "BSE"}.get(primary_exchange)
    expected_symbol = str(provider_symbol).strip().upper()
    observed_symbol = "" if pd.isna(returned_symbol) else str(returned_symbol).strip().upper()
    observed_exchange = "" if pd.isna(returned_exchange) else str(returned_exchange).strip().upper()
    observed_type = "" if pd.isna(returned_quote_type) else str(returned_quote_type).strip().upper()
    valid = bool(
        expected_exchange and expected_symbol and expected_symbol.lower() != "nan"
        and observed_symbol == expected_symbol
        and observed_exchange == expected_exchange
        and observed_type == "EQUITY"
    )
    reason = (
        "Exact provider symbol, exchange and EQUITY type matched the canonical mapping."
        if valid else
        f"expected {expected_symbol or '<missing>'}/{expected_exchange or '<unsupported>'}/EQUITY; "
        f"received {observed_symbol or '<missing>'}/{observed_exchange or '<missing>'}/{observed_type or '<missing>'}"
    )
    return valid, reason


def yahoo_numeric_fact(info: dict[str, Any], key: str, *, percentage_points: bool = False) -> float | None:
    """Normalize a finite Yahoo numeric fact without treating missing values as zero."""

    value = info.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not float("-inf") < number < float("inf"):
        return None
    return number / 100.0 if percentage_points else number


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite_or_missing(series: pd.Series, name: str) -> None:
    values = pd.to_numeric(series, errors="coerce")
    invalid = series.notna() & values.isna()
    if invalid.any():
        raise ValueError(f"Yahoo observation {name} contains nonnumeric values")
    if values.dropna().map(lambda value: not float("-inf") < float(value) < float("inf")).any():
        raise ValueError(f"Yahoo observation {name} contains non-finite values")


def validate_yahoo_observations(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(YAHOO_REQUIRED_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"Yahoo observations are missing columns: {missing}")
    result = frame.loc[:, list(YAHOO_REQUIRED_COLUMNS)].copy()
    if result.empty or result["ticker"].duplicated().any() or result["isin"].duplicated().any():
        raise ValueError("Yahoo observations require unique ticker and ISIN rows")
    if not result["isin"].astype(str).str.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]").all():
        raise ValueError("Yahoo observations contain malformed ISINs")
    dates = pd.to_datetime(result["retrieved_at"], utc=True, errors="coerce")
    if dates.isna().any():
        raise ValueError("Yahoo retrieved_at must be timezone-aware")
    allowed_identity = {"EXCHANGE_SYMBOL_MATCH", "REJECTED_IDENTITY", "PROVIDER_ERROR"}
    if not set(result["identity_status"]).issubset(allowed_identity):
        raise ValueError("Yahoo identity_status is invalid")
    allowed_freshness = {"CURRENT", "DUE_FOR_CHECK", "STALE", "SOURCE_TEMPORARILY_UNAVAILABLE"}
    if not set(result["freshness_status"]).issubset(allowed_freshness):
        raise ValueError("Yahoo freshness_status is invalid")
    numeric = (
        "market_cap", "shares_outstanding", "trailing_pe", "price_to_book",
        "trailing_eps", "book_value", "dividend_yield_decimal", "beta",
        "fifty_two_week_high", "fifty_two_week_low", "return_on_equity",
        "debt_to_equity_decimal", "revenue_growth", "earnings_growth",
        "operating_margin", "profit_margin",
    )
    for column in numeric:
        _finite_or_missing(result[column], column)
    accepted = result["identity_status"].eq("EXCHANGE_SYMBOL_MATCH")
    if (pd.to_numeric(result.loc[accepted, "shares_outstanding"], errors="coerce").dropna() <= 0).any():
        raise ValueError("shares outstanding must be positive")
    high = pd.to_numeric(result["fifty_two_week_high"], errors="coerce")
    low = pd.to_numeric(result["fifty_two_week_low"], errors="coerce")
    if (low.notna() & high.notna() & low.gt(high)).any():
        raise ValueError("52-week low cannot exceed 52-week high")
    rejected = ~accepted
    factual = ["market_cap", "sector", "annual_income_status"]
    if result.loc[rejected, factual].notna().any(axis=None):
        raise ValueError("rejected Yahoo identities cannot contribute facts")
    return result


def load_yahoo_secondary_bundle(directory: str | Path) -> YahooSecondaryBundle:
    root = Path(directory)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != YAHOO_OBSERVATION_VERSION:
        raise ValueError("Yahoo secondary manifest version is unsupported")
    for name, expected in manifest["artifacts"].items():
        if sha256_file(root / name) != expected:
            raise ValueError(f"Yahoo secondary artifact hash mismatch: {name}")
    observations = validate_yahoo_observations(pd.read_csv(root / "observations.csv", low_memory=False))
    financials = pd.read_csv(root / "financial_facts.csv", low_memory=False)
    actions = pd.read_csv(root / "corporate_actions.csv", low_memory=False)
    if len(observations) != int(manifest["requested_count"]):
        raise ValueError("Yahoo requested count is inconsistent")
    return YahooSecondaryBundle(observations, financials, actions, manifest)


def yahoo_coverage(observations: pd.DataFrame) -> dict[str, Any]:
    validated = validate_yahoo_observations(observations)
    accepted = validated.loc[validated["identity_status"].eq("EXCHANGE_SYMBOL_MATCH")]
    fields = {
        "identity": "returned_symbol", "company_profile": "company_profile",
        "classification": "sector", "market_cap": "market_cap",
        "shares_outstanding": "shares_outstanding", "pe": "trailing_pe",
        "pb": "price_to_book", "eps": "trailing_eps", "book_value": "book_value",
        "dividend_yield": "dividend_yield_decimal", "roe": "return_on_equity",
        "debt_to_equity_reference": "debt_to_equity_decimal",
        "revenue_growth": "revenue_growth", "profit_growth_reference": "earnings_growth",
        "high_low_52w": "fifty_two_week_high",
    }
    coverage = {key: int(accepted[column].notna().sum()) for key, column in fields.items()}
    coverage.update({
        "requested": int(len(validated)), "identity_accepted": int(len(accepted)),
        "identity_rejected": int(validated["identity_status"].eq("REJECTED_IDENTITY").sum()),
        "provider_errors": int(validated["identity_status"].eq("PROVIDER_ERROR").sum()),
        "annual_income": int(accepted["annual_income_status"].eq("USEFUL_FACTS").sum()),
        "quarterly_income": int(accepted["quarterly_income_status"].eq("USEFUL_FACTS").sum()),
        "balance_sheet": int(accepted["balance_sheet_status"].eq("USEFUL_FACTS").sum()),
        "cash_flow": int(accepted["cash_flow_status"].eq("USEFUL_FACTS").sum()),
        "corporate_actions": int(accepted["corporate_actions_status"].eq("USEFUL_FACTS").sum()),
        "holder_data": int(accepted["holder_data_status"].eq("USEFUL_FACTS").sum()),
    })
    return coverage
