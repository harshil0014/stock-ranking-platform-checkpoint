import pandas as pd
import pytest

from stock_research.historical_financial_features import usable_observation_time, to_research_evidence
from stock_research.historical_financial_features import derived_ratios


def test_vendor_observation_cannot_be_backdated_by_financial_period():
    assert usable_observation_time("2026-09-01T00:00:00Z", "2022-03-31").startswith("2026-09-01")


@pytest.mark.parametrize("observed,period", [("2026-09-01", "2022-03-31"), ("2022-01-01T00:00:00Z", "2022-03-31")])
def test_invalid_observation_clock_rejected(observed, period):
    with pytest.raises(ValueError):
        usable_observation_time(observed, period)


def test_historical_bridge_never_admits_unverified_vendor_vintage():
    with pytest.raises(ValueError, match="historical training blocked"):
        to_research_evidence(pd.DataFrame(), ranking_date="2022-08-05", sectors_by_isin={}, mode="historical_train")


def test_ratios_do_not_mix_periods_or_invent_denominators():
    rows = [{"period_end": "2025-03-31", "feature": name, "value": value, "source_cell": name}
            for name, value in [("annual_pat", 10), ("annual_sales", 100), ("balance_borrowings", 20),
                                ("balance_equity_capital", 10), ("balance_reserves", 30)]]
    result = {r["feature"]: r["value"] for r in derived_ratios(rows)}
    assert result == {"derived_net_margin": .1, "derived_debt_to_equity": .5, "derived_roe_closing_equity": .25}
    rows[-1]["period_end"] = "2024-03-31"
    assert [r['feature'] for r in derived_ratios(rows)] == ["derived_net_margin"]


def test_current_bridge_exact_identity_and_conflict_guard():
    rows = pd.DataFrame([{"isin": "INE002A01018", "ticker": "RELIANCE", "feature": "annual_pat",
                          "period_end": "2025-03-31", "available_at": "2026-09-01T10:00:00Z",
                          "source_hash": "a" * 64, "value": 5}])
    result = to_research_evidence(rows, ranking_date="2026-09-02", sectors_by_isin={"INE002A01018": "Energy"}, mode="current")
    assert result.value.tolist() == [5]
    assert result.availability_status.tolist() == ['current_only']
    conflict = pd.concat([rows, rows.assign(value=6)])
    with pytest.raises(ValueError, match="conflicting"):
        to_research_evidence(conflict, ranking_date="2026-09-02", sectors_by_isin={"INE002A01018": "Energy"}, mode="current")
