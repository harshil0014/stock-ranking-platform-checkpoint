"""Independent worked cases for the standalone workbook replication."""
from datetime import date
import importlib.util
from pathlib import Path

import pytest

P = Path(__file__).resolve().parents[1] / 'research/runners/professor_exact_formula_20261005.py'
SPEC = importlib.util.spec_from_file_location('professor_exact', P)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def test_month_end_and_calendar_days():
    rows = m.schedule(date(2026, 10, 5))
    assert len(rows) == 36
    assert rows[0] == {'history_row': 3, 'scheduled_date': '2023-10-31',
                       'workday_date': '2023-11-01', 'request_start': '2023-10-30',
                       'request_num_days': 1}
    assert rows[-1]['scheduled_date'] == '2026-09-15'
    assert rows[1]['scheduled_date'] == '2023-11-30'
    assert rows[2]['scheduled_date'] == '2023-12-30'


def test_weekend_and_leap_month():
    assert m.workday(date(2023, 9, 30), 1) == date(2023, 10, 2)
    assert m.workday(date(2023, 10, 2), -2) == date(2023, 9, 28)
    assert m.schedule(date(2024, 4, 5), months=2)[0]['scheduled_date'] == '2024-02-29'


def test_integer_purchases_actual_spend_and_no_cash_carry():
    r, ledger = m.calculate({3: 100, 4: 120}, 150)
    assert [t['shares_bought'] for t in ledger] == [75, 62]
    assert r['shares_bought'] == 137
    assert r['invested'] == 14940
    assert r['current_value'] == 20550
    assert r['profit_fraction'] == pytest.approx(5610 / 14940)
    assert r['average_price'] == pytest.approx(14940 / 137)


@pytest.mark.parametrize('quantity', [0, 2.5, 10])
def test_static_quantity_overrides_budget_without_rounding(quantity):
    r, _ = m.calculate({3: 100, 4: 120}, 150, static_quantity=quantity)
    assert r['shares_bought'] == quantity * 2
    assert r['invested'] == quantity * 220


def test_no_purchase_if_price_exceeds_budget():
    r, _ = m.calculate({3: 8000}, 10000, first_slot=True)
    assert r['shares_bought'] == 0
    assert r['profit_fraction'] == ''
    assert r['average_price'] == '#DIV/0!'


def test_missing_quote_preserves_workbook_minus_100_percent():
    r, _ = m.calculate({3: 100}, None)
    assert r['current_value'] == 0
    assert r['profit_fraction'] == -1


def test_blank_history_does_not_become_purchase():
    r, t = m.calculate({3: None}, 100)
    assert r['average_price'] == 0
    assert r['profit_fraction'] == ''
    assert t[0]['shares_bought'] == ''
    assert t[0]['cost'] == 0


@pytest.mark.parametrize('price', [0, '#N/A'])
def test_price_error_propagates_then_profit_iferror_blanks(price):
    r, _ = m.calculate({3: price}, 100)
    assert m.error(r['shares_bought'])
    assert r['profit_fraction'] == ''


def test_workbook_mismatched_sum_ranges_preserved():
    r, _ = m.calculate({2499: 100, 2500: 100}, 100)
    assert r['shares_bought'] == 150
    assert r['invested'] == 7500
    assert r['profit_fraction'] == 1


def test_rank_competition_ties_blanks_negative():
    rows = m.rank_rows([{'profit_fraction': s} for s in [.5, .5, .2, -1, '']])
    assert [r['rank'] for r in rows] == [1, 1, 3, 4, '#N/A']


def test_duplicate_stock_slots_are_not_deduplicated():
    rows = m.rank_rows([{'stock_code': 'X', 'profit_fraction': .5},
                        {'stock_code': 'X', 'profit_fraction': .5},
                        {'stock_code': 'Y', 'profit_fraction': .1}])
    assert [r['rank'] for r in rows] == [1, 1, 3]


def test_invalid_controls_fail_explicitly():
    with pytest.raises(ValueError):
        m.schedule(date(2026, 10, 5), interval=0)
    with pytest.raises(ValueError):
        m.schedule(date(2026, 10, 5), months=0)


def test_negative_rounddown_is_toward_zero():
    _, trades = m.calculate({3: 120}, 150, amount=-7500)
    assert trades[0]['shares_bought'] == -62


def test_misaligned_invested_guard_preserved():
    r, _ = m.calculate({3: 100}, 150, invested_guard_present=False)
    assert r['shares_bought'] == 75
    assert r['invested'] == ''
    assert r['profit_fraction'] == ''


def test_blank_stock_code_and_first_slot_unconditional_invested():
    r, _ = m.calculate({3: 100}, 150, first_slot=True, code_present=False)
    assert r['shares_bought'] == ''
    assert r['average_price'] == '#DIV/0!'
    assert r['profit_fraction'] == -1


def test_screenshot_external_ranks():
    rows = m.screenshot_checks()
    assert len(rows) == 14
    assert all(r['matches'] for r in rows)


def test_cached_schedule_feasible_date():
    rows = m.schedule(date(2026, 9, 1))
    assert len(rows) == 36
    assert (date.fromisoformat(rows[0]['scheduled_date']) - m.EPOCH).days == 45199
    assert (date.fromisoformat(rows[-1]['scheduled_date']) - m.EPOCH).days == 46249
