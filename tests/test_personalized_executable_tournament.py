from dataclasses import replace
import json

import pandas as pd
import pytest

from stock_ranker.personalized import InvestorProfile
from stock_research.personalized_executable_tournament import ExecutableHistoryBook, load_protocol


def book(tmp_path, *, split_ratio=2.0):
    history = tmp_path / "history"; history.mkdir()
    splits = tmp_path / "splits"; splits.mkdir()
    pd.DataFrame({
        "date": pd.date_range("2020-01-01", "2020-03-01"),
        "raw_close": [50.0] * 32 + [50.0] * 28 + [80.0],
        "adjusted_close": [50.0] * 32 + [50.0] * 28 + [80.0],
    }).to_csv(history / "AAA.csv", index=False)
    pd.DataFrame([{"isin": "ID", "ticker": "AAA", "status": "SUCCESS"}]).to_csv(
        splits / "acquisition_audit.csv", index=False
    )
    pd.DataFrame([{
        "isin": "ID", "ticker": "AAA", "provider_symbol": "AAA.NS",
        "event_date": "2020-02-01", "numerator": split_ratio, "denominator": 1,
        "split_ratio": split_ratio, "source_url": "source", "response_sha256": "hash",
    }]).to_csv(splits / "split_ledger.csv", index=False)
    identities = pd.DataFrame([{"isin": "ID", "ticker": "AAA"}])
    return ExecutableHistoryBook(identities, history, splits, as_of_date="2020-03-01")


def test_professor_and_enhanced_cash_policies_are_separate(tmp_path):
    b = book(tmp_path)
    profile = InvestorProfile(amount=60, interval_days=31, lookback_months=2, whole_shares=True)
    professor = b.simulate(profile, "2020-03-01", mode="professor").iloc[0]
    no_carry = b.simulate(profile, "2020-03-01", mode="enhanced_no_carry").iloc[0]
    carry = b.simulate(profile, "2020-03-01", mode="enhanced_carry").iloc[0]
    assert professor.shares_bought == 1 and professor.amount_invested == 50
    assert professor.unused_cash_excluded_by_professor == 70
    assert professor.total_wealth == 80 and professor.profit_loss_pct == pytest.approx(.6)
    assert no_carry.shares_bought == 1 and no_carry.residual_cash == 70 and no_carry.total_wealth == 150
    assert carry.shares_bought == 2 and carry.residual_cash == 20 and carry.total_wealth == 180
    assert all(float(item["shares_purchased"]).is_integer() for item in carry.journal)


def test_split_reconstructs_nominal_price_and_terminal_shares(tmp_path):
    b = book(tmp_path)
    profile = InvestorProfile(amount=100, interval_days=31, lookback_months=2, whole_shares=True)
    result = b.simulate(profile, "2020-03-01", mode="professor").iloc[0]
    assert result.journal[0]["execution_price"] == 100
    assert result.journal[1]["execution_price"] == 50
    assert result.shares_bought == 4
    assert result.current_holding_value == 320


def test_complex_split_is_quarantined(tmp_path):
    b = book(tmp_path, split_ratio=1.5)
    result = b.simulate(InvestorProfile(whole_shares=True), "2020-03-01", mode="enhanced_carry").iloc[0]
    assert result.status == "INVALID_HISTORY"
    assert "complex split" in result.reason


def test_all_invalid_forward_window_keeps_metric_schema(tmp_path):
    b = book(tmp_path)
    result = b.simulate(
        InvestorProfile(amount=100, interval_days=31, lookback_months=2, whole_shares=True),
        "2021-03-01",
        mode="enhanced_carry",
        include_journal=False,
    )
    assert result.status.eq("STALE_TERMINAL").all()
    assert {"xirr", "target_shortfall", "price_drawdown"}.issubset(result.columns)
    assert result[["xirr", "target_shortfall", "price_drawdown"]].isna().all().all()


def test_protocol_keeps_exposed_test_supplementary(tmp_path):
    protocol = {
        "scope": "GLOBAL_ONLY_FROZEN_COHORTS_WHOLE_SHARES",
        "profiles": {"base": {"amount": 7500, "interval_days": 30, "lookback_months": 36,
                                 "horizon_months": 12, "target_cagr": .2}},
        "validation_decision_dates": ["2023-12-31"],
        "supplementary_exposed_test_dates": ["2023-12-31"],
    }
    path = tmp_path / "protocol.json"; path.write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="overlap"):
        load_protocol(path)
