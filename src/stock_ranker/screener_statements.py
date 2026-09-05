"""Read-only presentation of validated Screener standalone workbooks.

This module exposes the historical tables already stored in accepted, hash-pinned
manual Screener batches.  It does not acquire data and it does not participate in
Baseline V1 or Research V2 calculations.
"""

from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any, Callable

from stock_ranker.screener_historical_fundamentals import (
    REPORTING_BASIS,
    _XlsxCells,
    _cell,
    _excel_date,
    inspect_screener_historical_workbook,
    sha256_file,
)
from stock_ranker.screener_data_bundle import load_accepted_screener_data_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MARKETDATA_ROOT = PROJECT_ROOT / "data/marketdata"
SCREENER_BUNDLE_STATE = PROJECT_ROOT / "data/company_facts/providers/screener_bundle/accepted_state.json"
_COLUMNS = "BCDEFGHIJK"


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _divide(numerator: float | None, denominator: float | None, multiplier: float = 1.0) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * multiplier


def _add(*values: float | None) -> float | None:
    return None if any(value is None for value in values) else sum(values)  # type: ignore[arg-type]


def _row(label: str, values: list[float | None], *, kind: str = "amount") -> dict[str, Any]:
    return {"label": label, "values": values, "kind": kind}


def _period_columns(cells: dict[str, tuple[object, str | None]], row: int) -> list[str]:
    columns: list[str] = []
    for column in _COLUMNS:
        try:
            _excel_date(_cell(cells, f"{column}{row}"))
        except ValueError:
            continue
        columns.append(column)
    return columns


def _dates(cells: dict[str, tuple[object, str | None]], row: int, columns: list[str]) -> list[str]:
    return [_excel_date(_cell(cells, f"{column}{row}")).isoformat() for column in columns]


def _values(cells: dict[str, tuple[object, str | None]], row: int, columns: list[str]) -> list[float | None]:
    return [_number(_cell(cells, f"{column}{row}")) for column in columns]


def _map(values: list[list[float | None]], function: Callable[..., float | None]) -> list[float | None]:
    return [function(*items) for items in zip(*values, strict=True)]


@lru_cache(maxsize=1)
def _candidate_records() -> list[tuple[dict[str, object], Path, Path]]:
    records: list[tuple[dict[str, object], Path, Path]] = []
    if SCREENER_BUNDLE_STATE.is_file():
        bundle = load_accepted_screener_data_bundle(
            SCREENER_BUNDLE_STATE,
            include_history=False,
            include_workbook_audit=True,
        )
        identity = bundle.market_master.set_index("isin", drop=False)
        for row in bundle.workbook_audit.loc[
            bundle.workbook_audit["file_status"].eq("ACCEPTED")
        ].to_dict("records"):
            isin = str(row.get("isin", "")).upper()
            expected_hash = str(row.get("workbook_sha256", ""))
            workbook = bundle.root / "workbooks" / isin / f"{expected_hash}.xlsx"
            if isin not in identity.index or not workbook.is_file():
                continue
            market_row = identity.loc[isin]
            records.append(({
                "ticker": str(market_row["ticker"]),
                "isin": isin,
                "reporting_basis": REPORTING_BASIS,
                "source_observed_at": bundle.summary.get("source_observed_at"),
                "screener_url": None,
                "workbook_sha256": expected_hash,
                "contract_version": bundle.summary.get("schema_version"),
                "accepted_bundle_fingerprint": bundle.fingerprint,
            }, workbook, bundle.root / "bundle_summary.json"))
    if not MARKETDATA_ROOT.exists():
        return records
    for manifest_path in sorted(MARKETDATA_ROOT.glob("screener-historical-*/batch_manifest.json")):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        for raw in payload.get("records", []):
            if not isinstance(raw, dict) or raw.get("reporting_basis") != REPORTING_BASIS:
                continue
            relative = Path(str(raw.get("cached_filename", "")))
            candidates = (manifest_path.parent / "source_workbooks" / relative, manifest_path.parent / relative)
            workbook = next((path for path in candidates if path.is_file()), None)
            if workbook is not None:
                records.append((raw, workbook, manifest_path))
    return records


@lru_cache(maxsize=512)
def load_screener_statement_history(ticker: str, isin: str) -> dict[str, Any]:
    """Return validated historical statement tables for an exact ticker/ISIN."""

    ticker = ticker.strip().upper()
    isin = isin.strip().upper()
    matches = [item for item in _candidate_records() if str(item[0].get("ticker", "")).upper() == ticker and str(item[0].get("isin", "")).upper() == isin]
    if not matches:
        return {
            "available": False,
            "status": "NO_VALIDATED_SCREENER_HISTORY",
            "reason": "No accepted hash-pinned standalone Screener workbook matches this exact ticker and ISIN.",
        }
    record, workbook_path, manifest_path = max(
        matches,
        key=lambda item: (str(item[0].get("source_observed_at", "")), str(item[2]), str(item[1])),
    )
    expected_hash = str(record.get("workbook_sha256", ""))
    actual_hash = sha256_file(workbook_path)
    if not expected_hash or actual_hash != expected_hash:
        return {
            "available": False,
            "status": "SCREENER_WORKBOOK_INTEGRITY_FAILURE",
            "reason": "The accepted workbook no longer matches its recorded SHA-256.",
        }
    inspection = inspect_screener_historical_workbook(workbook_path)
    with _XlsxCells(workbook_path) as book:
        data = book.sheet("Data Sheet")

    annual_columns = _period_columns(data, 16)
    annual_periods = _dates(data, 16, annual_columns)
    sales = _values(data, 17, annual_columns)
    raw_material = _values(data, 18, annual_columns)
    inventory_change = _values(data, 19, annual_columns)
    power = _values(data, 20, annual_columns)
    manufacturing = _values(data, 21, annual_columns)
    employee = _values(data, 22, annual_columns)
    selling = _values(data, 23, annual_columns)
    other_expenses = _values(data, 24, annual_columns)
    other_income = _values(data, 25, annual_columns)
    depreciation = _values(data, 26, annual_columns)
    interest = _values(data, 27, annual_columns)
    pbt = _values(data, 28, annual_columns)
    tax = _values(data, 29, annual_columns)
    profit = _values(data, 30, annual_columns)
    dividends = _values(data, 31, annual_columns)
    shares = _values(data, 93, annual_columns)
    expenses = _map(
        [raw_material, inventory_change, power, manufacturing, employee, selling, other_expenses],
        lambda raw, change, fuel, mfg, staff, admin, other: _add(raw, -change if change is not None else None, fuel, mfg, staff, admin, other),
    )
    operating_profit = _map([sales, expenses], lambda revenue, cost: None if revenue is None or cost is None else revenue - cost)

    balance_columns = _period_columns(data, 56)
    equity = _values(data, 57, balance_columns)
    reserves = _values(data, 58, balance_columns)
    borrowings = _values(data, 59, balance_columns)
    other_liabilities = _values(data, 60, balance_columns)
    total_liabilities = _values(data, 61, balance_columns)
    fixed_assets = _values(data, 62, balance_columns)
    cwip = _values(data, 63, balance_columns)
    investments = _values(data, 64, balance_columns)
    other_assets = _values(data, 65, balance_columns)
    total_assets = _values(data, 66, balance_columns)
    receivables = _values(data, 67, balance_columns)
    inventory = _values(data, 68, balance_columns)
    cash = _values(data, 69, balance_columns)
    ratio_equity = _values(data, 57, annual_columns)
    ratio_reserves = _values(data, 58, annual_columns)
    ratio_borrowings = _values(data, 59, annual_columns)
    capital_employed = _map([ratio_equity, ratio_reserves, ratio_borrowings], _add)
    roce: list[float | None] = [None]
    for index in range(1, len(annual_columns)):
        denominator = _add(capital_employed[index - 1], capital_employed[index])
        ebit = _add(pbt[index], interest[index])
        roce.append(_divide(ebit, denominator, 200.0))

    quarterly_columns = _period_columns(data, 41)
    quarterly_periods = _dates(data, 41, quarterly_columns)
    q_sales = _values(data, 42, quarterly_columns)
    q_expenses = _values(data, 43, quarterly_columns)
    q_other_income = _values(data, 44, quarterly_columns)
    q_depreciation = _values(data, 45, quarterly_columns)
    q_interest = _values(data, 46, quarterly_columns)
    q_pbt = _values(data, 47, quarterly_columns)
    q_tax = _values(data, 48, quarterly_columns)
    q_profit = _values(data, 49, quarterly_columns)
    q_operating = _values(data, 50, quarterly_columns)

    return {
        "available": True,
        "status": "VALIDATED_SCREENER_STANDALONE_HISTORY",
        "company": inspection.company,
        "ticker": ticker,
        "isin": isin,
        "reporting_basis": REPORTING_BASIS,
        "workbook_version": inspection.version,
        "source_observed_at": record.get("source_observed_at"),
        "screener_url": record.get("screener_url"),
        "workbook_sha256": actual_hash,
        "roce_formula_sha256": inspection.roce_formula_sha256,
        "contract_version": record.get("contract_version"),
        "accepted_bundle_fingerprint": record.get("accepted_bundle_fingerprint"),
        "provenance": "User-supplied Screener Premium standalone workbook; exact ISIN manifest; hash verified at read time.",
        "display_unit": "₹ crore except per-share values and percentages",
        "quarterly_results": {
            "periods": quarterly_periods,
            "rows": [
                _row("Sales", q_sales), _row("Expenses", q_expenses), _row("Operating Profit", q_operating),
                _row("OPM %", _map([q_operating, q_sales], lambda a, b: _divide(a, b, 100.0)), kind="percent"),
                _row("Other Income", q_other_income), _row("Interest", q_interest),
                _row("Depreciation", q_depreciation), _row("Profit Before Tax", q_pbt),
                _row("Tax %", _map([q_tax, q_pbt], lambda a, b: _divide(a, b, 100.0)), kind="percent"),
                _row("Net Profit", q_profit),
            ],
        },
        "profit_loss": {
            "periods": annual_periods,
            "rows": [
                _row("Sales", sales), _row("Expenses", expenses), _row("Operating Profit", operating_profit),
                _row("OPM %", _map([operating_profit, sales], lambda a, b: _divide(a, b, 100.0)), kind="percent"),
                _row("Other Income", other_income), _row("Interest", interest), _row("Depreciation", depreciation),
                _row("Profit Before Tax", pbt), _row("Tax %", _map([tax, pbt], lambda a, b: _divide(a, b, 100.0)), kind="percent"),
                _row("Net Profit", profit), _row("EPS", _map([profit, shares], _divide), kind="per_share"),
                _row("Dividend Payout %", _map([dividends, profit], lambda a, b: _divide(a, b, 100.0)), kind="percent"),
            ],
        },
        "balance_sheet": {
            "periods": _dates(data, 56, balance_columns),
            "rows": [
                _row("Equity Capital", equity), _row("Reserves", reserves), _row("Borrowings", borrowings),
                _row("Other Liabilities", other_liabilities), _row("Total Liabilities", total_liabilities),
                _row("Fixed Assets", fixed_assets), _row("Capital Work in Progress", cwip),
                _row("Investments", investments), _row("Other Assets", other_assets), _row("Total Assets", total_assets),
                _row("Receivables", receivables), _row("Inventory", inventory), _row("Cash & Bank", cash),
            ],
        },
        "cash_flow": {
            "periods": _dates(data, 81, cash_columns := _period_columns(data, 81)),
            "rows": [
                _row("Cash from Operating Activity", _values(data, 82, cash_columns)),
                _row("Cash from Investing Activity", _values(data, 83, cash_columns)),
                _row("Cash from Financing Activity", _values(data, 84, cash_columns)),
                _row("Net Cash Flow", _values(data, 85, cash_columns)),
            ],
        },
        "ratios": {
            "periods": annual_periods,
            "rows": [
                _row("Debtor Days", _map([receivables, sales], lambda a, b: _divide(a, b, 365.0)), kind="days"),
                _row("Inventory Turnover", _map([sales, inventory], _divide), kind="multiple"),
                _row("Return on Equity %", _map([profit, ratio_equity, ratio_reserves], lambda pat, cap, res: _divide(pat, _add(cap, res), 100.0)), kind="percent"),
                _row("Return on Capital Employed %", roce, kind="percent"),
                _row("Debt to Equity", _map([ratio_borrowings, ratio_equity, ratio_reserves], lambda debt, cap, res: _divide(debt, _add(cap, res))), kind="multiple"),
            ],
        },
    }
