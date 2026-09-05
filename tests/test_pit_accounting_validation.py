from stock_ranker.pit_accounting_validation import parse_profit_page, parse_ratio_page, unique_disclosure


def test_explicit_percent_roce_is_converted_but_plain_ratio_is_not() -> None:
    percent = """NOTES TO THE STANDALONE FINANCIAL STATEMENTS\nParticulars 31 March 2026 31 March 2025\nReturn on Capital Employed EBIT Capital employed 15.85% 24.83%"""
    plain = """NOTES TO THE STANDALONE FINANCIAL STATEMENTS\nParticulars 31 March 2026 31 March 2025\nReturn on Capital Employed EBIT Capital employed 0.09 0.10"""
    assert parse_ratio_page("roce", 1, percent)[0].current_value == 0.1585
    assert parse_ratio_page("roce", 1, plain)[0].current_value == 0.09


def test_dash_is_never_promoted_as_zero() -> None:
    text = """NOTES TO THE STANDALONE FINANCIAL STATEMENTS\nParticulars 31 March 2026 31 March 2025\nDebt Equity Ratio Total debt Shareholder equity - -"""
    selected, reason = unique_disclosure(parse_ratio_page("debt_to_equity", 1, text))
    assert selected is None
    assert reason == "NO_DIRECT_DISCLOSURE_PARSED"


def test_conflicting_disclosures_are_quarantined() -> None:
    one = """NOTES TO THE STANDALONE FINANCIAL STATEMENTS\n31 March 2026 31 March 2025\nDebt Equity Ratio Total debt Shareholder equity 0.10 0.20"""
    two = one.replace("0.10 0.20", "0.30 0.40")
    selected, reason = unique_disclosure(parse_ratio_page("debt_to_equity", 1, one) + parse_ratio_page("debt_to_equity", 2, two))
    assert selected is None
    assert reason == "CONFLICTING_DIRECT_DISCLOSURES"


def test_profit_requires_standalone_years_and_unit() -> None:
    text = """STANDALONE STATEMENT OF PROFIT AND LOSS\nINR in crore\nYear ended 31 March 2026 31 March 2025\nProfit for the year 120.50 (40.25)"""
    result = parse_profit_page(7, text)
    assert result[0].current_value == 120.5
    assert result[0].prior_value == -40.25
    assert result[0].unit == "INR crore"


def test_mixed_reporting_basis_is_not_accepted() -> None:
    text = """STANDALONE AND CONSOLIDATED FINANCIAL STATEMENTS\nINR in crore\n2026 2025\nProfit for the year 120.50 40.25"""
    assert parse_profit_page(7, text) == []


def test_net_debt_to_equity_is_not_accepted_as_debt_to_equity() -> None:
    explicit_net = """NOTES TO THE STANDALONE FINANCIAL STATEMENTS\n2026 2025\nNet debt to equity ratio 0.14 0.25\nNet debt equals debt less cash and cash equivalents"""
    disguised_net = """NOTES TO THE STANDALONE FINANCIAL STATEMENTS\n2026 2025\nDebt-equity Ratio Non-current borrowings plus current borrowings less cash and cash equivalents Equity 0.55 0.79"""
    assert parse_ratio_page("debt_to_equity", 1, explicit_net) == []
    assert parse_ratio_page("debt_to_equity", 1, disguised_net) == []


def test_multiline_net_debt_formula_is_not_accepted() -> None:
    text = """NOTES TO THE STANDALONE FINANCIAL STATEMENTS
2026 2025
Debt-equity Ratio Total borrowings less
cash and cash equivalents and term deposits divided by total equity 0.55 0.79"""
    assert parse_ratio_page("debt_to_equity", 1, text) == []


def test_next_ratio_row_cannot_supply_missing_debt_equity_values() -> None:
    text = """NOTES TO THE STANDALONE FINANCIAL STATEMENTS
2026 2025
Debt Equity Ratio Total debt Total equity
Interest coverage ratio 29.64 29.61"""
    assert parse_ratio_page("debt_to_equity", 1, text) == []


def test_debt_equity_requires_local_numerator_and_denominator_evidence() -> None:
    text = """NOTES TO THE STANDALONE FINANCIAL STATEMENTS
2026 2025
Debt Equity Ratio 0.20 0.30
Revenue from operations 100 90"""
    assert parse_ratio_page("debt_to_equity", 1, text) == []


def test_wrapped_in_percent_roce_unit_is_respected() -> None:
    text = """NOTES TO THE STANDALONE FINANCIAL STATEMENTS\n2026 2025\nReturn on Capital employed (in Earnings before interest Capital employed 1.70 1.07 59%\n%)"""
    result = parse_ratio_page("roce", 1, text)
    assert result[0].current_value == 0.017
