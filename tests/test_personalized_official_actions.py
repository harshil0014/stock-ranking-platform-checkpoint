import pandas as pd

from stock_ranker.personalized import InvestorProfile
from stock_research.personalized_official_actions import (
    OfficialActionHistoryBook,
    load_official_action_ledger,
    apply_recovered_terms,
    affordable_rights_allotment,
    validate_recovery_pack,
)
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
    history = tmp_path / "history"; history.mkdir(parents=True)
    splits = tmp_path / "splits"; splits.mkdir(parents=True)
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


def test_recovered_evidence_reconciles_and_respects_cutoff():
    pack = ROOT / "external_research_pack/residual_recovery_20260925"
    if not pack.exists():
        return  # large evidence pack is intentionally outside Git
    audit = validate_recovery_pack(pack, pack.parent / "event_terms_round2")
    assert (audit["round2_events"], audit["covered_union"], audit["core_mechanics_unknown"]) == (445, 445, 0)
    old = pd.read_csv(ROOT / "experiments/personalized-official-action-freeze/build-02/normalized_official_action_ledger.csv.gz")
    new, applied = apply_recovered_terms(old, pack, as_of_date="2026-09-18")
    repeat, repeat_audit = apply_recovered_terms(old, pack, as_of_date="2026-09-18")
    pd.testing.assert_frame_equal(new, repeat)
    assert applied == repeat_audit
    assert applied["applied_pre_cutoff"] == 22
    assert pd.to_datetime(new.event_date).max() <= pd.Timestamp("2026-09-18")
    early, early_audit = apply_recovered_terms(old.loc[old.event_date.le("2024-12-31")], pack,
                                               as_of_date="2024-12-31")
    assert early_audit["post_cutoff_excluded"] > 0
    assert pd.to_datetime(early.event_date).max() <= pd.Timestamp("2024-12-31")
    withdrawn = new.loc[new["isin"].eq("INE125F01032") & new.event_date.eq("2025-04-15")]
    assert withdrawn.iloc[0].economic_policy == "WITHDRAWN_NO_ALLOTMENT"
    assert withdrawn.iloc[0].mechanics_status == "PASSIVE_RIGHTS"
    assert not new.loc[new.event_type.eq("RIGHTS"), "mechanics_status"].eq("AUTO_MULTIPLIER").any()
    assert new.loc[new["isin"].eq("INE205A01025") & new.event_type.eq("DEMERGER"),
                   "entitlement_terms"].iloc[0] == "1:1_EACH_OF_4"
    assert new.loc[new["isin"].eq("INE076B01028") & new.event_type.eq("SCHEME_OR_MERGER"),
                   "economic_policy"].iloc[0] == "PREFERENCE_SHARE_VALUATION_UNAVAILABLE"
    ratios = {"INE176N01039": .1, "INE188Y01031": .1, "INE363L01045": .5,
              "INE413X01035": .1, "INE621I01042": .2, "INE799C01049": .1}
    for isin, expected in ratios.items():
        assert new.loc[new["isin"].eq(isin) & new.event_type.eq("CONSOLIDATION"),
                       "total_share_multiplier"].eq(expected).any()


def test_rights_exercise_requires_portfolio_cash():
    assert affordable_rights_allotment(10, 0, 3, 1, 5) == (0, 0)
    assert affordable_rights_allotment(10, 14, 3, 1, 5) == (2, 4)
    assert affordable_rights_allotment(10, 150, 3, 1, 5) == (30, 0)


def test_withdrawn_and_passive_rights_do_not_allot_shares(tmp_path):
    for policy in ("WITHDRAWN_NO_ALLOTMENT", "PASSIVE_NO_SUBSCRIPTION_ZERO_ENTITLEMENT_VALUE"):
        action = normalized_action(event_type="RIGHTS", status="PASSIVE_RIGHTS")
        action["economic_policy"] = policy
        action["total_share_multiplier"] = None
        book = official_book(tmp_path / policy, action, pre=100, post=100)
        row = book.simulate(InvestorProfile(amount=100, interval_days=31, lookback_months=2,
                                            whole_shares=True), "2020-03-01").iloc[0]
        assert row.status == "AVAILABLE"
        assert row.shares_bought == 2


def test_demerger_and_preference_entitlements_block_without_valuation(tmp_path):
    profile = InvestorProfile(amount=100, interval_days=31, lookback_months=2, whole_shares=True)
    for event_type, reason in (("DEMERGER", "RESULTING_SECURITY_VALUATION_UNAVAILABLE"),
                               ("SCHEME_OR_MERGER", "PREFERENCE_SHARE_VALUATION_UNAVAILABLE")):
        action = normalized_action(event_type=event_type, status="BLOCKING", reason=reason)
        book = official_book(tmp_path / event_type, action)
        row = book.simulate(profile, "2020-03-01").iloc[0]
        assert row.status == "UNRESOLVED_CORPORATE_ACTION"
        assert row.reason == reason


def test_consolidation_clean_and_fractional_holdings(tmp_path):
    action = normalized_action(event_type="CONSOLIDATION", numerator=1, denominator=2)
    clean = official_book(tmp_path / "clean", action, pre=50, post=100)
    profile = InvestorProfile(amount=100, interval_days=31, lookback_months=2, whole_shares=True)
    assert clean.simulate(profile, "2020-03-01").iloc[0].status == "AVAILABLE"
    fractional = official_book(tmp_path / "fractional", action, pre=100, post=200)
    row = fractional.simulate(profile, "2020-03-01").iloc[0]
    assert row.status == "UNRESOLVED_FRACTIONAL_ENTITLEMENT"


def test_intermediate_consolidation_fraction_not_hidden_by_later_split(tmp_path):
    actions = pd.concat([
        normalized_action(event_type="CONSOLIDATION", numerator=1, denominator=2),
        normalized_action(event_date="2020-02-15", event_type="SPLIT", numerator=2, denominator=1),
    ], ignore_index=True)
    book = official_book(tmp_path, actions, pre=100, post=200)
    row = book.simulate(InvestorProfile(amount=100, interval_days=31, lookback_months=2,
                                        whole_shares=True), "2020-03-01", include_journal=False).iloc[0]
    assert row.status == "UNRESOLVED_FRACTIONAL_ENTITLEMENT"
    assert row.reason == "FRACTIONAL_CONSOLIDATION_ENTITLEMENT:2020-02-01"
