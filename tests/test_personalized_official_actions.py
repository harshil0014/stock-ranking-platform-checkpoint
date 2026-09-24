import pandas as pd

from stock_ranker.personalized import InvestorProfile
from stock_research.personalized_official_actions import (
    OfficialActionHistoryBook,
    load_official_action_ledger,
)


def normalized_action(*, event_date="2020-02-01", event_type="BONUS", numerator=2.0,
                      denominator=1.0, status="AUTO_MULTIPLIER", reason=None):
    return pd.DataFrame([{
        "isin": "CURRENT", "ticker": "AAA", "exchange": "NSE", "event_date": event_date,
        "source_text": event_type, "source_event_type": event_type, "event_type": event_type,
        "mapping_basis": "EXACT_PRIMARY_EXCHANGE_SYMBOL", "mechanics_status": status,
        "block_reason": reason, "multiplier_numerator": numerator,
        "multiplier_denominator": denominator,
        "total_share_multiplier": numerator / denominator if status == "AUTO_MULTIPLIER" else None,
    }])


def official_book(tmp_path, actions, *, pre=100.0, post=50.0, provider_ratio=None):
    history = tmp_path / "history"; history.mkdir()
    splits = tmp_path / "splits"; splits.mkdir()
    dates = pd.date_range("2020-01-01", "2020-03-01")
    raw = [pre if day < pd.Timestamp("2020-02-01") else post for day in dates]
    adjusted = [value / provider_ratio if provider_ratio and day < pd.Timestamp("2020-02-01") else value
                for day, value in zip(dates, raw)]
    pd.DataFrame({"date": dates, "raw_close": raw, "adjusted_close": adjusted}).to_csv(
        history / "AAA.csv", index=False
    )
    provider = pd.DataFrame(columns=["isin", "event_date", "split_ratio"])
    if provider_ratio is not None:
        provider = pd.DataFrame([{
            "isin": "CURRENT", "event_date": "2020-02-01", "split_ratio": provider_ratio,
        }])
    provider.to_csv(splits / "split_ledger.csv", index=False)
    identities = pd.DataFrame([{"isin": "CURRENT", "ticker": "AAA"}])
    return OfficialActionHistoryBook(
        identities, history, splits, actions, as_of_date="2020-03-01"
    )


def test_official_symbol_mapping_carries_action_across_isin_change(tmp_path):
    raw = pd.DataFrame([{
        "exchange": "NSE", "isin": "OLD", "ticker_or_code": "AAA",
        "event_date": "01-Feb-2020", "record_date": "02-Feb-2020",
        "source_text": "Bonus 1:1", "event_type": "BONUS", "ratio_numerator": 1,
        "ratio_denominator": 1, "total_share_multiplier": 2, "parse_status": "PARSED",
        "event_date_parsed": "2020-02-01",
    }])
    source = tmp_path / "events.csv"; raw.to_csv(source, index=False)
    facts = pd.DataFrame([{"isin": "CURRENT", "ticker": "AAA", "primary_exchange": "NSE"}])
    ledger, audit = load_official_action_ledger(facts, source, as_of_date="2020-03-01")
    assert ledger.iloc[0]["isin"] == "CURRENT"
    assert ledger.iloc[0].total_share_multiplier == 2
    assert audit["identity_continuity_rows"] == 1


def test_official_bonus_reconstructs_return_basis_and_integer_shares(tmp_path):
    book = official_book(tmp_path, normalized_action())
    result = book.simulate(
        InvestorProfile(amount=100, interval_days=31, lookback_months=2, whole_shares=True),
        "2020-03-01", mode="enhanced_carry",
    ).iloc[0]
    assert result.status == "AVAILABLE"
    assert result.shares_bought == 4
    assert result.total_wealth == 200
    assert result.price_drawdown == 0


def test_provider_split_does_not_inflate_historical_execution_price(tmp_path):
    book = official_book(tmp_path, normalized_action(), provider_ratio=2)
    result = book.simulate(
        InvestorProfile(amount=100, interval_days=31, lookback_months=2, whole_shares=True),
        "2020-03-01", mode="enhanced_carry",
    ).iloc[0]
    assert result.status == "AVAILABLE"
    assert result.shares_bought == 4
    assert result.amount_invested == 200
    assert result.total_wealth == 200
    assert result.price_drawdown == 0


def test_official_blocker_is_profile_window_specific(tmp_path):
    blocker = normalized_action(
        event_date="2018-01-01", event_type="RIGHTS", status="BLOCKING",
        reason="RIGHTS", numerator=1, denominator=1,
    )
    book = official_book(tmp_path, blocker)
    short = book.simulate(
        InvestorProfile(amount=100, interval_days=31, lookback_months=2, whole_shares=True),
        "2020-03-01", mode="enhanced_carry",
    ).iloc[0]
    long = book.simulate(
        InvestorProfile(amount=100, interval_days=31, lookback_months=36, whole_shares=True),
        "2020-03-01", mode="enhanced_carry",
    ).iloc[0]
    assert short.status == "AVAILABLE"
    assert long.status == "UNRESOLVED_CORPORATE_ACTION"


def test_fractional_corporate_action_entitlement_remains_blocked(tmp_path):
    book = official_book(tmp_path, normalized_action(numerator=3, denominator=2), pre=100, post=70)
    result = book.simulate(
        InvestorProfile(amount=100, interval_days=31, lookback_months=2, whole_shares=True),
        "2020-03-01", mode="enhanced_carry",
    ).iloc[0]
    assert result.status == "UNRESOLVED_FRACTIONAL_ENTITLEMENT"


def test_parsed_consolidation_multiplier_is_supported(tmp_path):
    book = official_book(
        tmp_path,
        normalized_action(event_type="CONSOLIDATION", numerator=1, denominator=2),
        pre=50,
        post=100,
    )
    result = book.simulate(
        InvestorProfile(amount=100, interval_days=31, lookback_months=2, whole_shares=True),
        "2020-03-01", mode="enhanced_carry",
    ).iloc[0]
    assert result.status == "AVAILABLE"
    assert result.shares_bought == 2
    assert result.price_drawdown == 0
