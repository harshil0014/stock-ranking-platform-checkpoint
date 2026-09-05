from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from stock_ranker.screener_historical_fundamentals import build_screener_pit_cohorts
from stock_ranker.screener_public_history import (
    acquire_public_company_pages,
    parse_public_company_history,
)


def _html(*, ticker: str = "EXACT", tiny_equity: bool = False, basis: str = "Standalone") -> str:
    reserves = "1" if tiny_equity else "900"
    return f"""
    <html><body>
      <div id="company-info" data-company-id="123"></div>
      <a href="https://www.nseindia.com/get-quotes/equity?symbol={ticker}">NSE</a>
      {'View Standalone' if basis == 'Consolidated' else ''}
      <section id="profit-loss"><p>{basis} Figures in Rs. Crores</p><table>
        <tr><th></th><th>Mar 2024</th><th>Mar 2025</th><th>TTM</th></tr>
        <tr><td>Interest</td><td>10</td><td>12</td><td>13</td></tr>
        <tr><td>Profit before tax</td><td>100</td><td>120</td><td>130</td></tr>
        <tr><td>Net Profit</td><td>75</td><td>90</td><td>95</td></tr>
      </table></section>
      <section id="balance-sheet"><p>{basis} Figures in Rs. Crores</p><table>
        <tr><th></th><th>Mar 2024</th><th>Mar 2025</th></tr>
        <tr><td>Equity Capital</td><td>100</td><td>100</td></tr>
        <tr><td>Reserves</td><td>{reserves}</td><td>{reserves}</td></tr>
        <tr><td>Borrowings</td><td>200</td><td>180</td></tr>
      </table></section>
    </body></html>
    """


def _parse(**kwargs: object) -> pd.DataFrame:
    html = _html(**kwargs)
    return parse_public_company_history(
        html,
        {"ticker": "EXACT", "isin": "INE123A01010", "company": "Exact Limited"},
        source_url="https://www.screener.in/company/EXACT/",
        source_observed_at="2026-08-31T00:00:00Z",
        source_sha256=hashlib.sha256(html.encode()).hexdigest(),
    )


def test_public_history_uses_visible_standalone_values_and_screener_formula() -> None:
    frame = _parse()
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["period_end"] == "2025-03-31"
    assert row["prior_period_end"] == "2024-03-31"
    assert row["current_pat"] == 90
    assert row["prior_pat"] == 75
    assert row["profit_growth_yoy"] == pytest.approx(0.2)
    assert row["roce"] == pytest.approx((120 + 12) * 2 / (100 + 900 + 200 + 100 + 900 + 180))
    assert row["debt_to_equity"] == pytest.approx(180 / 1000)
    assert row["source_precision_status"] == "PASS"
    assert row["roce_lower_bound"] <= row["roce"] <= row["roce_upper_bound"]


def test_public_history_rejects_identity_or_nonstandalone_page() -> None:
    with pytest.raises(ValueError, match="NSE identity mismatch"):
        _parse(ticker="OTHER")
    with pytest.raises(ValueError, match="not explicitly standalone"):
        _parse(basis="Consolidated")


def test_public_history_marks_fragile_rounded_ratios_unsafe() -> None:
    frame = _parse(tiny_equity=True)
    assert frame.iloc[0]["source_precision_status"] == "UNSAFE_ROUNDED_RATIO_PRECISION"


def test_pit_selection_excludes_unsafe_public_precision() -> None:
    normalized = _parse(tiny_equity=True)
    clock = pd.DataFrame({
        "isin": ["INE123A01010"],
        "period_end": [pd.Timestamp("2025-03-31", tz="UTC")],
        "official_available_at": [pd.Timestamp("2025-06-01", tz="UTC")],
        "filing_id": ["filing"],
        "official_filing_url": ["https://nse.example/report"],
        "availability_status": ["PIT_AVAILABLE"],
    })
    result = build_screener_pit_cohorts(normalized, clock, [pd.Timestamp("2025-08-07").date()])
    assert result.accepted.empty
    assert result.rejected.iloc[0]["period_status"] == "UNSAFE_SOURCE_DISPLAY_PRECISION"


def test_cache_only_resume_makes_no_request(tmp_path, monkeypatch) -> None:
    html = _html().encode()
    pages = tmp_path / "pages"
    pages.mkdir()
    page = pages / "EXACT.html"
    page.write_bytes(html)
    metadata = {
        "schema_version": "screener_public_history_cache_v1",
        "ticker": "EXACT", "isin": "INE123A01010",
        "url": "https://www.screener.in/company/EXACT/",
        "final_url": "https://www.screener.in/company/EXACT/",
        "observed_at": "2026-08-31T00:00:00+00:00",
        "sha256": hashlib.sha256(html).hexdigest(), "byte_count": len(html),
        "user_agent": "test",
    }
    (pages / "EXACT.json").write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.setattr(
        "stock_ranker.screener_public_history.urlopen",
        lambda *_args, **_kwargs: pytest.fail("cache-only resume attempted a network call"),
    )
    result = acquire_public_company_pages(
        pd.DataFrame([{"ticker": "EXACT", "isin": "INE123A01010"}]),
        tmp_path, request_budget=0,
    )
    assert result.iloc[0]["cache_status"] == "CACHE_HIT"


def test_zero_budget_defers_uncached_identity_without_network(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "stock_ranker.screener_public_history.urlopen",
        lambda *_args, **_kwargs: pytest.fail("zero request budget attempted a network call"),
    )
    result = acquire_public_company_pages(
        pd.DataFrame([{"ticker": "EXACT", "isin": "INE123A01010"}]),
        tmp_path, request_budget=0,
    )
    assert result.iloc[0]["cache_status"] == "DEFERRED_REQUEST_BUDGET"
