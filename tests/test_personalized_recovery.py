import pandas as pd
import pytest

from stock_ranker.personalized import InvestorProfile
from stock_ranker.personalized_recovery import (
    classify_profile_eligibility, effective_dated_security_master, recover_history_book,
)


def _facts(listing="2020-01-01"):
    return pd.DataFrame([{"ticker": "AAA", "isin": "INE000A01001", "company": "A Ltd",
                          "primary_exchange": "NSE", "exchange_security_id": "AAA",
                          "listing_date": listing, "product_sector": "Industrials",
                          "product_classification_as_of": "2026-09-18"}])


def _live():
    return pd.DataFrame([{"ticker": "AAA", "isin": "INE000A01001", "primary_exchange": "NSE",
                          "trade_date": "2026-09-18", "latest_price": 120,
                          "snapshot_status": "AVAILABLE", "snapshot_source": "OFFICIAL_NSE_CM_UDIFF"}])


def _actions():
    return pd.DataFrame(columns=["ticker", "isin", "exchange", "action_type", "subject", "ex_date"])


def test_terminal_repair_sanitizes_impossible_row_and_appends_official_close(tmp_path):
    pd.DataFrame({"date": ["2023-09-15", "2024-01-02", "2026-09-04"],
                  "raw_close": [80, 0, 100], "adjusted_close": [80, 0, 100]}).to_csv(tmp_path / "AAA.csv", index=False)
    result = recover_history_book(_facts(), tmp_path, _live(), _actions(), as_of_date="2026-09-18")
    assert len(result.repairs) == 1
    assert result.history_audit.iloc[0].invalid_observations_removed == 1
    dates, prices = result.book.arrays["INE000A01001"]
    assert str(dates[-1]) == "2026-09-18" and prices[-1] == 120


def test_action_in_gap_quarantines_terminal_append(tmp_path):
    pd.DataFrame({"date": ["2023-09-15", "2026-09-04"], "raw_close": [80, 100],
                  "adjusted_close": [80, 100]}).to_csv(tmp_path / "AAA.csv", index=False)
    actions = pd.DataFrame([{"ticker": "AAA", "isin": "INE000A01001", "exchange": "NSE",
                             "action_type": "SPLIT", "subject": "Split", "ex_date": "2026-09-10"}])
    result = recover_history_book(_facts(), tmp_path, _live(), actions, as_of_date="2026-09-18")
    assert result.repairs.empty
    assert result.history_audit.iloc[0].terminal_repair_reason == "CORPORATE_ACTION_IN_GAP"


def test_official_dividend_bridge_extends_total_return_without_price_splice(tmp_path):
    pd.DataFrame({"date": ["2023-09-15", "2026-09-04"], "raw_close": [80, 100],
                  "adjusted_close": [80, 100]}).to_csv(tmp_path / "AAA.csv", index=False)
    actions = pd.DataFrame([{"ticker": "AAA", "isin": "INE000A01001", "exchange": "NSE",
                             "action_type": "DIVIDEND", "subject": "Dividend - Rs 2 Per Share",
                             "ex_date": "2026-09-10"}])
    bridge = pd.DataFrame({"trade_date": ["2026-09-08", "2026-09-10", "2026-09-17", "2026-09-18"],
                           "isin": ["INE000A01001"] * 4, "ticker": ["AAA"] * 4,
                           "close": [101, 99, 110, 120]})
    result = recover_history_book(_facts(), tmp_path, _live(), actions, as_of_date="2026-09-18",
                                  official_price_bridge=bridge)
    audit = result.history_audit.iloc[0]
    assert audit.terminal_repair_status == "APPENDED_OFFICIAL_TOTAL_RETURN_BRIDGE"
    _, prices = result.book.arrays["INE000A01001"]
    assert prices[-1] == pytest.approx(100 * 101 / 100 * (99 + 2) / 101 * 120 / 99)


def test_future_and_cross_exchange_prices_cannot_repair(tmp_path):
    pd.DataFrame({"date": ["2023-09-15", "2026-09-04"], "raw_close": [80, 100],
                  "adjusted_close": [80, 100]}).to_csv(tmp_path / "AAA.csv", index=False)
    live = _live(); live.loc[0, "trade_date"] = "2026-09-19"
    result = recover_history_book(_facts(), tmp_path, live, _actions(), as_of_date="2026-09-18")
    assert result.history_audit.iloc[0].terminal_repair_reason == "FUTURE_LIVE_PRICE"
    live = _live(); live.loc[0, "primary_exchange"] = "BSE"
    result = recover_history_book(_facts(), tmp_path, live, _actions(), as_of_date="2026-09-18")
    assert result.history_audit.iloc[0].terminal_repair_reason == "CROSS_EXCHANGE_PRICE_REQUIRES_REVIEW"


def test_recovery_rebuild_is_deterministic(tmp_path):
    pd.DataFrame({"date": ["2023-09-15", "2026-09-04"], "raw_close": [80, 100],
                  "adjusted_close": [80, 100]}).to_csv(tmp_path / "AAA.csv", index=False)
    first = recover_history_book(_facts(), tmp_path, _live(), _actions(), as_of_date="2026-09-18")
    second = recover_history_book(_facts(), tmp_path, _live(), _actions(), as_of_date="2026-09-18")
    pd.testing.assert_frame_equal(first.repairs, second.repairs)
    pd.testing.assert_frame_equal(first.history_audit, second.history_audit)
    assert (first.book.arrays["INE000A01001"][0] == second.book.arrays["INE000A01001"][0]).all()
    assert (first.book.arrays["INE000A01001"][1] == second.book.arrays["INE000A01001"][1]).all()


def test_profile_specific_recent_ipo_is_legitimate_ineligibility(tmp_path):
    facts = _facts("2026-01-01")
    pd.DataFrame({"date": ["2026-01-01", "2026-09-04"], "raw_close": [80, 100],
                  "adjusted_close": [80, 100]}).to_csv(tmp_path / "AAA.csv", index=False)
    recovered = recover_history_book(facts, tmp_path, _live(), _actions(), as_of_date="2026-09-18")
    profile = InvestorProfile(lookback_months=12)
    simulation = recovered.book.simulate(profile, "2026-09-18")
    audit = classify_profile_eligibility(simulation, facts, recovered.history_audit, profile, as_of_date="2026-09-18")
    assert audit.iloc[0].eligibility_class == "LEGITIMATE_INELIGIBILITY"
    assert audit.iloc[0].classification_reason == "LISTED_AFTER_PROFILE_START"


def test_security_master_preserves_superseded_and_unresolved_departures():
    evidence = pd.DataFrame([{"canonical_isin": "INE000A01001", "evidence_type": "SYMBOL_CHANGE",
                              "historical_symbol": "OLD", "effective_date": "2024-01-01",
                              "historical_company_name": "Old A", "continuity_status": "OFFICIAL_NSE_SYMBOL_TRANSITION"}])
    old = pd.DataFrame([{"ticker": "GONE", "isin": "INE999A01001", "company": "Gone Ltd",
                         "primary_exchange": "NSE", "exchange_security_id": "GONE",
                         "disposition": "EXCLUDED_FROM_FINAL_ACCEPTED_SNAPSHOT"}])
    master = effective_dated_security_master(_facts(), evidence, old, as_of_date="2026-09-18")
    assert set(master.lifecycle_status) == {"LISTED_AS_OF_CUTOFF", "SUPERSEDED_SYMBOL",
                                            "NO_LONGER_IN_CURRENT_UNIVERSE_UNRESOLVED"}
    gone = master[master.symbol.eq("GONE")].iloc[0]
    assert gone.continuity_status == "PRESERVED_NO_AUTOMATIC_TERMINAL_VALUE"
    assert master[master.symbol.eq("OLD")].iloc[0].valid_to == "2024-01-01"
