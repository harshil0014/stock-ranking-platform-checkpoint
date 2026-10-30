"""Fundamental data and screening.

IMPORTANT -- read before trusting anything this module produces:

yfinance serves fundamentals as they stand **today**. There is no point-in-time
history, so a screen built here can rank stocks *now* but cannot be backtested.
Applying today's P/E to a 2015 date would be lookahead bias of the worst kind --
you'd be "discovering" that cheap-and-profitable companies outperformed, using
the profitability they went on to report. That is why this module has no
backtest entry point, and why nothing here comes with a performance claim.

To test a fundamental strategy honestly you need point-in-time data, where each
date sees only what had actually been published by then. In India that means a
paid source (Screener.in, Tijori, Capitaline) rather than free Yahoo data.
"""

from __future__ import annotations

import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .universe import to_yahoo

CACHE_FILE = "fundamentals.parquet"
# Fundamentals move quarterly; re-pulling more often than daily is wasted time.
MAX_CACHE_AGE_HOURS = 24


# Lenders, matched loosely because sector taxonomies disagree: yfinance says
# "Financial Services" where a Screener.in export says "Banks" or "Finance".
LENDER_SECTOR_PATTERN = r"financial|bank|nbfc|insurance|finance"


@dataclass(frozen=True)
class Metric:
    field: str  # key in yfinance's .info dict
    label: str  # column header
    pillar: str  # value | quality | growth
    higher_is_better: bool
    positive_only: bool = False  # negative values are meaningless, not "cheap"
    skip_lenders: bool = False  # metric is meaningless for banks/NBFCs


# A deliberately small set. Every extra metric is another chance to fit noise,
# and most of them are correlated with one already here.
METRICS = [
    # Value -- what you pay.
    Metric("trailingPE", "PE", "value", False, positive_only=True),
    Metric("priceToBook", "PB", "value", False, positive_only=True),
    Metric("enterpriseToEbitda", "EV/EBITDA", "value", False, positive_only=True),
    # Quality -- what you get. Leverage ratios are meaningless for lenders,
    # whose balance sheets are debt by construction, so banks skip that one.
    Metric("returnOnEquity", "ROE", "quality", True),
    Metric("returnOnAssets", "ROA", "quality", True),
    Metric("operatingMargins", "OpMargin", "quality", True),
    Metric("debtToEquity", "D/E", "quality", False, skip_lenders=True),
    # Growth -- where it's heading.
    Metric("earningsGrowth", "EarnGrw", "growth", True),
    Metric("revenueGrowth", "RevGrw", "growth", True),
]

PILLARS = ("value", "quality", "growth")

_EXTRA_FIELDS = ["sector", "industry", "marketCap", "dividendYield",
                 "trailingEps", "bookValue"]


def _fetch_one(symbol: str, exchange: str) -> dict | None:
    import yfinance as yf

    ticker = to_yahoo(symbol, exchange)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            info = yf.Ticker(ticker).info or {}
    except Exception:
        return None
    if not info.get("marketCap"):
        return None  # nothing usable came back

    row = {"symbol": symbol}
    for metric in METRICS:
        row[metric.field] = info.get(metric.field)
    for field in _EXTRA_FIELDS:
        row[field] = info.get(field)
    return row


def fetch_fundamentals(
    symbols: list[str],
    cache_dir: str | Path = "cache",
    refresh: bool = False,
    exchange: str = "NS",
) -> pd.DataFrame:
    """One row per symbol of current fundamental metrics, cached for a day."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / CACHE_FILE

    cached = pd.DataFrame()
    if path.exists() and not refresh:
        cached = pd.read_parquet(path)
        age = pd.Timestamp.now() - pd.to_datetime(cached["fetched_at"]).max()
        if age > pd.Timedelta(hours=MAX_CACHE_AGE_HOURS):
            cached = pd.DataFrame()

    known = set(cached["symbol"]) if not cached.empty else set()
    missing = [s for s in symbols if s not in known]

    if missing:
        print(f"Fetching fundamentals for {len(missing)} symbol(s)... "
              f"(one request each, this takes a minute)", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=8) as pool:
            fetched = list(pool.map(lambda s: _fetch_one(s, exchange), missing))
        rows = [r for r in fetched if r]
        if failed := len(missing) - len(rows):
            print(f"  {failed} symbol(s) returned no fundamentals", file=sys.stderr)
        if rows:
            fresh = pd.DataFrame(rows)
            fresh["fetched_at"] = pd.Timestamp.now()
            cached = pd.concat([cached, fresh], ignore_index=True)
            cached.to_parquet(path, index=False)

    if cached.empty:
        raise RuntimeError("No fundamental data could be retrieved.")

    result = cached[cached["symbol"].isin(symbols)].set_index("symbol")
    return result[~result.index.duplicated(keep="last")]


# Ranking within a sector needs enough peers to be meaningful; below this we
# fall back to a universe-wide rank rather than crowning the best of three.
MIN_SECTOR_PEERS = 5


def _rank(series: pd.Series, higher_is_better: bool) -> pd.Series:
    # rank(pct) ignores NaN, so partial coverage degrades gracefully.
    return series.rank(pct=True, ascending=higher_is_better) * 100


def _percentile_scores(data: pd.DataFrame, sector_neutral: bool = True) -> pd.DataFrame:
    """Rank each metric into a 0-100 score.

    Sector-neutral by default, and that default matters: banks and NBFCs
    structurally trade on lower P/E and P/B than software or consumer names, so
    ranking everything in one pool doesn't find good companies -- it finds the
    cheapest *sector*, then fills the shortlist with it. Ranking each stock
    against its own peers asks the better question: is this a good bank?
    """
    scores = pd.DataFrame(index=data.index)
    sectors = data.get("sector") if sector_neutral else None

    if sectors is not None:
        counts = sectors.value_counts()
        big_enough = sectors.isin(counts[counts >= MIN_SECTOR_PEERS].index)

    for metric in METRICS:
        if metric.field not in data.columns:
            continue
        series = pd.to_numeric(data[metric.field], errors="coerce")
        if metric.positive_only:
            # A negative P/E means losses, not a bargain -- drop, don't rank.
            series = series.where(series > 0)
        if metric.skip_lenders and "sector" in data.columns:
            is_lender = data["sector"].astype(str).str.contains(
                LENDER_SECTOR_PATTERN, case=False, na=False
            )
            series = series.where(~is_lender)

        if sectors is None:
            scores[metric.field] = _rank(series, metric.higher_is_better)
            continue

        # Peers where the sector is well populated, whole universe otherwise.
        within = series.where(big_enough).groupby(sectors).transform(
            lambda s: _rank(s, metric.higher_is_better)
        )
        scores[metric.field] = within.where(big_enough,
                                            _rank(series, metric.higher_is_better))

    return scores


# A pillar built from one surviving metric isn't a pillar, it's that metric
# wearing a hat. A loss-making company whose negative P/E is (correctly)
# dropped would otherwise score 100 on "value" purely on a low P/B.
MIN_METRICS_PER_PILLAR = 2


def screen(
    data: pd.DataFrame,
    weights: dict[str, float] | None = None,
    min_metrics: int = 5,
    sector_neutral: bool = True,
) -> pd.DataFrame:
    """Score and rank the universe. Returns a frame sorted best-first.

    ``weights`` sets the pillar mix, e.g. ``{"value": 2, "quality": 1}``.
    Companies with fewer than ``min_metrics`` usable inputs are dropped rather
    than flattered by a score built from two numbers.
    """
    weights = weights or {p: 1.0 for p in PILLARS}
    scores = _percentile_scores(data, sector_neutral=sector_neutral)

    out = pd.DataFrame(index=data.index)
    out["coverage"] = scores.notna().sum(axis=1)

    for pillar in PILLARS:
        fields = [m.field for m in METRICS
                  if m.pillar == pillar and m.field in scores.columns]
        contributing = scores[fields].notna().sum(axis=1)
        mean = scores[fields].mean(axis=1, skipna=True)
        # Too thin to mean anything -- leave it NaN so it abstains rather
        # than votes on one number.
        out[pillar] = mean.where(contributing >= MIN_METRICS_PER_PILLAR)

    weight_series = pd.Series({p: float(weights.get(p, 0.0)) for p in PILLARS})
    pillar_scores = out[list(PILLARS)]
    # Renormalise per row so a missing pillar doesn't silently drag the score
    # toward zero -- it just doesn't vote.
    applied = pillar_scores.notna().mul(weight_series, axis=1)
    out["score"] = (pillar_scores.fillna(0.0).mul(weight_series, axis=1).sum(axis=1)
                    / applied.sum(axis=1).replace(0.0, float("nan")))

    for column in ["sector", "trailingPE", "priceToBook", "returnOnEquity",
                   "debtToEquity", "earningsGrowth", "dividendYield", "marketCap"]:
        if column in data.columns:
            out[column] = data[column]

    out = out[out["coverage"] >= min_metrics]
    return out.sort_values("score", ascending=False)
