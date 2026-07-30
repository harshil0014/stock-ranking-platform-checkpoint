from __future__ import annotations

import math
from datetime import date

import pandas as pd

from stock_ranker.research_v2 import ResearchV2Inputs
from stock_ranker.v2_config import ResearchV2Config


RANKING_DATE = date(2026, 6, 30)


def make_price_rows(
    ticker: str,
    *,
    base: float = 100,
    trend: float = 0.0004,
    variation: float = 0.01,
    start: str = "2020-06-22",
) -> list[dict[str, object]]:
    dates = pd.bdate_range(start, "2026-06-30")
    return [
        {
            "ticker": ticker,
            "date": day.strftime("%Y-%m-%d"),
            "adjusted_close": base
            * math.exp(trend * index)
            * (1 + variation * math.sin(index * 0.11)),
        }
        for index, day in enumerate(dates)
    ]


def make_inputs(
    tickers: tuple[tuple[str, str], ...] = (
        ("AAA", "Technology"),
        ("BBB", "Technology"),
    ),
) -> ResearchV2Inputs:
    universe_rows = []
    price_rows = []
    fundamental_rows = []
    for index, (ticker, sector) in enumerate(tickers):
        universe_rows.append(
            {
                "ticker": ticker,
                "company": f"{ticker} Fictional Company",
                "sector": sector,
            }
        )
        price_rows.extend(
            make_price_rows(
                ticker,
                base=80 + index * 20,
                trend=0.00035 + index * 0.00004,
                variation=0.008 + index * 0.004,
            )
        )
        fundamental_rows.append(
            {
                "ticker": ticker,
                "period_end": "2025-03-31",
                "available_date": "2025-06-15",
                "roce": 0.15 + index * 0.02,
                "debt_to_equity": 0.6 + index * 0.1,
                "profit_growth_yoy": 0.08 + index * 0.03,
            }
        )
    return ResearchV2Inputs(
        universe=pd.DataFrame(universe_rows),
        prices=pd.DataFrame(price_rows),
        fundamentals=pd.DataFrame(fundamental_rows),
    )


def default_config(top_n: int = 5) -> ResearchV2Config:
    return ResearchV2Config(ranking_date=RANKING_DATE, top_n=top_n)
