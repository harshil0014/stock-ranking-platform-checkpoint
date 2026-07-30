"""Generate deterministic, fictional Research V2 CSV fixtures.

The generated companies and values are synthetic and are not investment
recommendations. Run from the repository root.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pandas as pd


OUTPUT_DIR = Path("data/input")
RANKING_DATE = pd.Timestamp("2026-06-30")

STOCKS = (
    ("TEC001", "Aster Quantum Systems", "Technology", 80, 0.18, 0.018),
    ("TEC002", "Blue Nova Software", "Technology", 110, 0.12, 0.032),
    ("TEC003", "Cedar Pixel Labs", "Technology", 65, 0.08, 0.045),
    ("TEC004", "Delta Logic Studio", "Technology", 90, 0.14, 0.026),
    ("TEC005", "Echo Circuit Works", "Technology", 180, 0.14, 0.026),
    ("TEC006", "Fable Data Services", "Technology", 125, 0.04, 0.055),
    ("FIN001", "Amber Ledger Cooperative", "Financial Services", 70, 0.11, 0.020),
    ("FIN002", "Banyan Credit Network", "Financial Services", 95, 0.07, 0.028),
    ("FIN003", "Coral Payment House", "Financial Services", 55, 0.15, 0.038),
    ("FIN004", "Dawn Rural Finance", "Financial Services", 120, 0.05, 0.018),
    ("FIN005", "Elm Trust Services", "Financial Services", 85, 0.09, 0.048),
    ("FIN006", "Flint Capital Exchange", "Financial Services", 105, 0.02, 0.060),
    ("IND001", "Atlas Motion Equipment", "Industrials", 100, 0.16, 0.024),
    ("IND002", "Beacon Process Tools", "Industrials", 75, 0.10, 0.035),
    ("IND003", "Cobalt Fabrication Lab", "Industrials", 130, 0.06, 0.020),
    ("IND004", "Drift Transit Components", "Industrials", 60, 0.13, 0.043),
    ("IND005", "Ember Automation Works", "Industrials", 115, 0.03, 0.052),
    ("IND006", "Forge Industrial Studio", "Industrials", 90, 0.08, 0.030),
)

FUNDAMENTALS = {
    "TEC001": (0.28, 0.18, 0.22),
    "TEC002": (0.21, 0.35, 0.12),
    "TEC003": (0.16, 0.12, -0.08),
    "TEC004": (0.24, 0.25, 0.15),
    "TEC005": (0.24, 0.25, 0.15),
    "TEC006": (0.11, 0.60, -0.15),
    "FIN001": (0.19, 1.20, 0.14),
    "FIN002": (0.15, 0.80, 0.06),
    "FIN003": (0.23, 1.50, 0.19),
    "FIN004": (0.12, 0.45, -0.04),
    "FIN005": (0.17, 1.05, 0.09),
    "FIN006": (0.09, 1.80, -0.12),
    "IND001": (0.26, 0.30, 0.20),
    "IND002": (0.18, 0.55, 0.11),
    "IND003": (0.14, 0.20, -0.03),
    "IND004": (0.22, 0.75, 0.16),
    "IND005": (0.10, 0.95, -0.10),
    "IND006": (0.20, -0.40, 0.08),
}


def _price_factor(index: int, annual_trend: float, variation: float) -> float:
    years = index / 252
    cycle = variation * math.sin(index * 0.071)
    secondary = variation * 0.55 * math.sin(index * 0.019 + 0.8)
    drawdown = -variation * 2.8 * math.exp(
        -((index - 920) / 58) ** 2
    )
    return math.exp(annual_trend * years) * (1 + cycle + secondary + drawdown)


def generate_universe() -> None:
    with (OUTPUT_DIR / "v2_universe.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(("ticker", "company", "sector"))
        writer.writerows((ticker, company, sector) for ticker, company, sector, *_ in STOCKS)


def generate_prices() -> None:
    dates = pd.bdate_range("2020-06-22", RANKING_DATE)
    base_series: dict[str, list[float]] = {}
    rows: list[tuple[str, str, object]] = []
    for ticker, _company, _sector, base, trend, variation in STOCKS:
        if ticker == "TEC005":
            values = [value * 2 for value in base_series["TEC004"]]
        else:
            values = [
                round(base * _price_factor(index, trend, variation), 6)
                for index in range(len(dates))
            ]
        base_series[ticker] = values
        rows.extend(
            (ticker, day.strftime("%Y-%m-%d"), value)
            for day, value in zip(dates, values, strict=True)
        )

    # Future observations prove they are excluded from the June 30 calculation.
    rows.extend(
        [
            ("TEC001", "2026-07-01", 9999.0),
            ("FIN001", "2026-07-02", "not-a-number"),
            ("IND001", "2026-07-03", 1.0),
        ]
    )
    with (OUTPUT_DIR / "v2_prices.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(("ticker", "date", "adjusted_close"))
        writer.writerows(rows)


def generate_fundamentals() -> None:
    rows: list[tuple[object, ...]] = []
    for ticker, values in FUNDAMENTALS.items():
        roce, leverage, profit = values
        rows.append(
            (
                ticker,
                "2024-03-31",
                "2024-06-15",
                round(roce - 0.02, 4),
                round(max(leverage - 0.05, 0), 4),
                round(profit - 0.03, 4),
            )
        )
        rows.append(
            (
                ticker,
                "2025-03-31",
                "2025-06-15",
                roce,
                leverage,
                profit,
            )
        )

    # An eligible revision: the later availability date must win.
    rows.append(("TEC002", "2025-03-31", "2025-08-01", 0.225, 0.32, 0.135))
    # Future records, including malformed numerics, must be ignored.
    rows.extend(
        [
            ("TEC001", "2025-03-31", "2026-07-15", 0.99, 0.01, 0.99),
            ("FIN003", "2025-03-31", "2026-07-05", "bad", "bad", "bad"),
            ("IND001", "2026-03-31", "2026-08-01", 0.90, 0.05, 0.80),
        ]
    )
    with (OUTPUT_DIR / "v2_fundamentals.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "ticker",
                "period_end",
                "available_date",
                "roce",
                "debt_to_equity",
                "profit_growth_yoy",
            )
        )
        writer.writerows(rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_universe()
    generate_prices()
    generate_fundamentals()


if __name__ == "__main__":
    main()
