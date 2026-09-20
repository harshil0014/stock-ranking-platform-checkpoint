import numpy as np
import pandas as pd

from stock_research.vendor_risk_experiment import FEATURES, RISK, select_features, test_models as evaluate_models


def test_latest_filing_first_and_cutoff_without_backdating_vendor():
    obs = pd.DataFrame([dict(isin="X", period_end="2022-03-31", feature=FEATURES[0], value=2,
                             available_at="2026-09-01T00:00:00Z", source_hash="a")])
    clock = pd.DataFrame([dict(isin="X", period_end=p, official_available_at=t, filing_id=p)
                          for p,t in [("2022-03-31","2022-07-01T00:00:00Z"),
                                      ("2023-03-31","2023-08-07T10:00:01Z")]])
    a,_ = select_features(obs,clock,["2023-08-07"])
    assert a.value.tolist() == [2]
    assert a.available_at.iloc[0].startswith("2026")
    assert a.research_status.iloc[0] == RISK
    b,_ = select_features(obs,clock,["2023-08-08"])
    assert b.period_end.tolist() == ["2023-03-31"]
    assert b.value.isna().all()


def test_vendor_conflicts_are_not_cherry_picked():
    rows = pd.DataFrame([dict(isin="X",period_end="2022-03-31",feature="f",value=v,
                             available_at="2026-09-01T00:00:00Z",source_hash=str(v)) for v in [1,2]])
    clocks = pd.DataFrame([dict(isin="X",period_end="2022-03-31",official_available_at="2022-07-01T00:00:00Z",filing_id="a")])
    selected, conflicts = select_features(rows,clocks,["2022-08-05"])
    assert len(conflicts) == 1
    assert selected.value.isna().all()


def test_ridge_predictions_do_not_use_unmatured_labels():
    rows, outcomes = [], []
    for year in [2022,2023,2024]:
        for i in range(4):
            date=f"{year}-08-07"
            rows.append(dict(ranking_date=date,isin=str(i),ticker=str(i),sector="s",
                             **{f:float(i+year%3) for f in FEATURES},mom12m_signal=i/4,
                             baseline_signal=i, research_v2_signal=3-i,quality=i,quality_momentum=i))
            outcomes.append(dict(ranking_date=date,isin=str(i),ticker=str(i),horizon_months=12,
                                 future_adjusted_return=i/10,actual_endpoint_date=f"{year+1}-08-07"))
    panel, labels = pd.DataFrame(rows), pd.DataFrame(outcomes)
    a,_ = evaluate_models(panel,labels)
    labels.loc[labels.ranking_date.ne("2022-08-07"),"future_adjusted_return"] *= -100
    b,_ = evaluate_models(panel,labels)
    np.testing.assert_allclose(a.ridge,b.ridge,equal_nan=True)
    assert a.loc[a.ranking_date.eq("2023-08-07"),"ridge"].isna().all()
    assert a.loc[a.ranking_date.eq("2024-08-07"),"training_rows"].eq(4).all()
