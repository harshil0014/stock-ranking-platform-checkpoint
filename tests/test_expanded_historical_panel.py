from pathlib import Path

import pandas as pd

from stock_research.expanded_historical_panel import _derive_pat_growth, _factor_score, _identity_map


def test_identity_map_rejects_ambiguous_tickers(tmp_path: Path):
    path=tmp_path/"identity.csv"
    pd.DataFrame([
        {"reference_nse_code":"AAA","isin":"I1","company":"A","screener_exact_isin_match":True},
        {"reference_nse_code":"AAA","isin":"I2","company":"B","screener_exact_isin_match":True},
        {"reference_nse_code":"BBB","isin":"I3","company":"C","screener_exact_isin_match":True},
        {"reference_nse_code":"CCC","isin":"I4","company":"D","screener_exact_isin_match":False},
    ]).to_csv(path,index=False)
    mapping,ambiguous=_identity_map(path)
    assert mapping=={"BBB":{"isin":"I3","company":"C"}}
    assert ambiguous=={"AAA"}


def test_factor_score_preserves_debt_direction_and_never_imputes():
    frame=pd.DataFrame({"ranking_date":["2022-01-01"]*3,"sector":["S"]*3,
                        "derived_net_margin":[1,2,3],"derived_debt_to_equity":[3,2,1]})
    result=_factor_score(frame,["derived_net_margin","derived_debt_to_equity"])
    assert result.is_monotonic_increasing
    frame.loc[1,"derived_net_margin"]=None
    assert _factor_score(frame,["derived_net_margin","derived_debt_to_equity"]).isna().iloc[1]


def test_profit_growth_never_mixes_workbooks_or_nonconsecutive_periods():
    frame=pd.DataFrame([
        {"isin":"I","period_end":"2022-03-31","feature":"annual_pat","value":10,"available_at":"x","source_hash":"a"},
        {"isin":"I","period_end":"2023-03-31","feature":"annual_pat","value":15,"available_at":"x","source_hash":"a"},
        {"isin":"I","period_end":"2025-03-31","feature":"annual_pat","value":30,"available_at":"x","source_hash":"a"},
        {"isin":"I","period_end":"2023-03-31","feature":"annual_pat","value":99,"available_at":"x","source_hash":"b"},
    ])
    result=_derive_pat_growth(frame)
    assert result[["period_end","value"]].to_dict("records")==[{"period_end":"2023-03-31","value":0.5}]
