import pytest

from stock_ranker.pit_accounting_pdfium import (
    parse_pdfium_profit_page,
    parse_pdfium_ratio_page,
    select_pdfium_disclosure,
)


PREFIX = "Standalone Financial Statements for 2025-26 and 2024-25\n"


def test_pdfium_text_route_accepts_direct_ratios_and_profit():
    ratios = PREFIX + """
    Debt-Equity Ratio 0.02 0.03 (31.60%)
    Debt-Equity Ratio = Total Debt / Shareholders' Equity
    Return on Capital Employed 18.23% 19.27% (5.38%)
    Return on Capital Employed = EBIT / Capital Employed
    """
    debt, status = select_pdfium_disclosure(parse_pdfium_ratio_page("debt_to_equity", 9, ratios))
    roce, roce_status = select_pdfium_disclosure(parse_pdfium_ratio_page("roce", 9, ratios))
    assert status == roce_status == "VALIDATED"
    assert (debt.current_value, debt.prior_value) == (0.02, 0.03)
    assert (roce.current_value, roce.prior_value) == (0.1823, 0.1927)
    profit = PREFIX + "Statement of Profit and Loss (INR crore)\nProfit for the year 123.40 100.00"
    selected, status = select_pdfium_disclosure(parse_pdfium_profit_page(7, profit))
    assert status == "VALIDATED"
    assert (selected.current_value, selected.prior_value, selected.unit) == (123.4, 100.0, "INR crore")


def test_pdfium_route_rejects_net_debt_and_ambiguous_values():
    text = PREFIX + """
    Net debt to equity ratio 0.2 0.1
    Net debt equals borrowings less cash; Shareholders' Equity is total equity.
    Return on Capital Employed = EBIT / Capital Employed
    """
    assert parse_pdfium_ratio_page("debt_to_equity", 2, text) == []
    conflicting = PREFIX + """
    Debt Equity Ratio 0.1 0.2
    Debt Equity Ratio 0.3 0.4
    Total Debt / Shareholders' Equity
    """
    selected, status = select_pdfium_disclosure(parse_pdfium_ratio_page("debt_to_equity", 3, conflicting))
    assert selected is None
    assert status == "CONFLICTING_PDFIUM_DISCLOSURES"


def test_pdfium_route_does_not_turn_year_or_note_numbers_into_roce():
    text = PREFIX + """
    Return on Capital Employed Earnings before interest and taxes / Capital Employed
    Increase in EBIT in FY 25-26. Note 45 follows.
    """
    assert parse_pdfium_ratio_page("roce", 10, text) == []


def test_pdfium_route_accepts_percent_unit_in_label_with_two_plain_cells():
    text = PREFIX + """
    Return on Capital Employed (%) 20.64 18.37 12.32%
    Return on Capital Employed = Earnings before Interest and Tax / Capital Employed
    """
    selected, status = select_pdfium_disclosure(parse_pdfium_ratio_page("roce", 5, text))
    assert status == "VALIDATED"
    assert (selected.current_value, selected.prior_value) == (0.2064, 0.1837)


def test_pdfium_profit_selects_explicit_standalone_columns_only():
    text = PREFIX + """
    Statement of Profit and Loss (INR crore)
    Consolidated Standalone
    2025-26 2024-25 2025-26 2024-25
    Profit for the year 597.73 372.78 593.66 372.80
    """
    selected, status = select_pdfium_disclosure(parse_pdfium_profit_page(7, text))
    assert status == "VALIDATED"
    assert (selected.current_value, selected.prior_value) == (593.66, 372.8)

    ambiguous = PREFIX + "Statement of Profit and Loss (INR crore)\nProfit for the year 1 2 3 4"
    assert parse_pdfium_profit_page(8, ambiguous) == []


def test_pdfium_ratio_never_uses_adjacent_rows_variance_percentages():
    text = PREFIX + """
    Return on Capital Employed (%) 9.61 11.91 -19%
    k) Return on Investment 4.66 5.35 -13%
    Return on Capital Employed = EBIT / Capital Employed
    """
    selected, status = select_pdfium_disclosure(parse_pdfium_ratio_page("roce", 4, text))
    assert status == "VALIDATED"
    assert selected.current_value == pytest.approx(0.0961)
    assert selected.prior_value == pytest.approx(0.1191)


def test_pdfium_ratio_joins_wrapped_cells_but_stops_at_next_metric():
    text = PREFIX + """
    Return on Capital
    Employed (ROCE)
    Earnings before Interest and Tax / Capital Employed
    In percentage 14.4% 15.5% (6.8%)
    Return on Investment 7.5% 11.4% (33.7%)
    """
    selected, status = select_pdfium_disclosure(parse_pdfium_ratio_page("roce", 4, text))
    assert status == "VALIDATED"
    assert (selected.current_value, selected.prior_value) == (0.144, 0.155)
