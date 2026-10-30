# trading_tool

A backtesting engine for **Indian equity (NSE)** trading strategies, in Python.

Free daily data via yfinance, a realistic Indian cost model (STT, stamp duty,
GST, exchange charges, slippage), and a pluggable strategy interface. No live
order placement — this is for testing ideas before risking capital.

## Setup

Uses [uv](https://docs.astral.sh/uv/) (already installed):

```bash
uv venv --python 3.12
uv pip install -e .
```

## Usage

```bash
.venv/Scripts/python -m trading_tool list-strategies
.venv/Scripts/python -m trading_tool backtest --start 2015-01-01 --plot --save
.venv/Scripts/python -m trading_tool backtest -s donchian -p entry=20 -p exit=10
.venv/Scripts/python -m trading_tool compare --start 2015-01-01
.venv/Scripts/python -m trading_tool signals -u nifty100 --refresh
.venv/Scripts/python -m trading_tool screen -u nifty100 --style value --top 20
```

Useful flags: `-u/--universe` (`nifty100`, `nifty50`, `next50`, `nifty10`, or
`RELIANCE,TCS,INFY`),
`--capital`, `--max-weight`, `--rebalance D|W|M`, `--slippage-bps`, `--refresh`.

Prices cache to `cache/` as parquet on first run, so re-runs are instant.
Results land in `results/`.

## What it found

All runs: weekly rebalance, default costs, ₹10L starting capital.

### Nifty 100, 2015-01-01 to 2026-07-31

| strategy | CAGR | Sharpe | Max DD | Turnover | Costs |
|---|---|---|---|---|---|
| ma_crossover | **19.79%** | **0.87** | -36.0% | 3.80x | ₹245k |
| trend_filtered | 18.69% | 0.86 | **-22.0%** | 11.01x | ₹651k |
| buy_hold | 19.37% | 0.85 | -34.9% | 0.25x | ₹15.7k |
| donchian | 13.25% | 0.53 | -26.6% | 14.73x | ₹549k |

### Nifty 50, same period

| strategy | CAGR | Sharpe | Max DD | Turnover | Costs |
|---|---|---|---|---|---|
| buy_hold | 18.27% | **0.78** | -37.4% | 0.29x | ₹16.6k |
| ma_crossover | 15.09% | 0.64 | -36.1% | 4.06x | ₹197k |
| trend_filtered | 11.80% | 0.47 | -28.5% | 11.74x | ₹448k |
| donchian | 8.39% | 0.24 | -26.6% | 15.27x | ₹437k |

**Universe size flips the conclusion.** On the Nifty 50, buy-and-hold beat every
trend system comfortably. Widen to 100 names and the crossover edges ahead —
more candidates means more trends to catch, and the mid-cap band trends harder
than the mega-caps that dominate an equal-weight Nifty 50.

Two cautions on that flip. The margin is thin (0.87 vs 0.85 Sharpe) — not the
kind of gap to bet on. And the Next 50 list carries extra selection bias: it
includes recent IPOs (Swiggy, Hyundai, LICI) that we only know to include
*because* they were worth listing. Some of the improvement is that artifact.

The most interesting row is `trend_filtered`: the same risk-adjusted return as
buy-and-hold with a **-22% worst drawdown against -34.9%**. It doesn't make more
money; it makes similar money with a far better ride. Whether that's worth ~11x
annual turnover depends on whether you'd have held on through the -35%.

### Last 2 years (2024-08 to 2026-07), Nifty 100

| strategy | CAGR | Sharpe | Max DD |
|---|---|---|---|
| buy_hold | 3.47% | -0.08 | -21.2% |
| donchian | 2.49% | -0.18 | -16.8% |
| ma_crossover | 2.44% | -0.28 | -11.7% |
| trend_filtered | 2.26% | -0.31 | -11.9% |

Every Sharpe is negative — over this stretch a 6% fixed deposit beat all of
them. The trend systems did roughly halve the drawdown, which is exactly what
they exist to do, but none of them made money worth the risk.

### Fundamentals, on genuine point-in-time data

The `fundamental` strategy ranks the Nifty 100 quarterly on what had actually
been *filed* by each date — 2,243 quarters across 98 companies, from NSE's own
XBRL, no lookahead.

**Jun 2020 – Mar 2025** (post-COVID bull run):

| strategy | CAGR | Sharpe | Max DD | Turnover | Costs |
|---|---|---|---|---|---|
| buy_hold | 34.87% | **1.71** | -20.0% | 0.23x | ₹4.9k |
| fundamental | 33.34% | 1.27 | -22.9% | 2.53x | ₹46.9k |
| donchian | 25.26% | 1.15 | -20.5% | 14.12x | ₹220k |
| ma_crossover | 22.97% | 1.14 | -21.3% | 2.88x | ₹38.9k |
| trend_filtered | 21.02% | 1.03 | -19.4% | 8.48x | ₹106k |

**Oct 2021 – Mar 2023** (the correction — a different regime):

| strategy | CAGR | Sharpe | Max DD |
|---|---|---|---|
| buy_hold | 7.12% | **0.15** | -14.3% |
| ma_crossover | 6.45% | 0.10 | -10.0% |
| fundamental | 0.94% | -0.12 | **-22.9%** |
| trend_filtered | 3.08% | -0.26 | -10.7% |
| donchian | -2.06% | -0.44 | -16.6% |

**Buy-and-hold wins both.** Ranking on real, honestly-timestamped fundamentals
did not beat owning the index equally weighted — and in the correction it took
the *worst* drawdown of any strategy while paying 10x the costs.

A warning about what to do next: the obvious temptation is to try `metric=`,
`top_n=` and date ranges until something beats the benchmark. Don't. With five
strategies, four metrics and any choice of window, something will win by
chance. That is how backtest results get manufactured. If an edge needs
searching for, it isn't one.

### The pattern across everything tested

Four strategy families, two data sources, several regimes, and the same answer
each time: **equal-weight buy-and-hold is hard to beat after costs.** That is
not a bug in the tool. It is the most robust finding it has produced, and it
is consistent with the broad evidence on active management.

Two takeaways for using this tool: always test against `buy_hold` before
believing an edge, and treat the cost model as part of the result rather than a
footnote.

## The `signals` command

Everything else answers "would this have worked?". This one answers "what does
it say to hold **now**?":

```
  TREND_FILTERED  |  signals as of 2026-07-31 close
  --------------------------------------------------------
  Act at the next session. 34 of 103 names qualify, 100% invested.

  CHANGES SINCE 2026-07-30
    ENTER   BAJAJFINSV      2.94%     Rs 29,412   @ Rs 2,029
    EXIT    ASIANPAINT         --                 @ Rs 2,746
    ...

  TARGET PORTFOLIO on Rs 10.00 L
    symbol          weight          value         price
    ADANIENT         2.94%      Rs 29,412      Rs 3,010
    ...
```

It reads the *unlagged* last row of the same weight matrix the backtest uses,
so the signals are generated by identical code to the one being measured —
there is no separate "live" path to drift out of sync.

Pass `--refresh` to pull current prices; without it you get signals from
whatever is cached, and the command warns if that data is more than four days
old. `--capital` sizes the rupee amounts.

## The `screen` command — fundamentals

Ranks the universe on current fundamentals: P/E, P/B, EV/EBITDA (value); ROE,
ROA, operating margin, debt/equity (quality); earnings and revenue growth
(growth). Each metric becomes a percentile rank, averaged into pillar scores.

```
.venv/Scripts/python -m trading_tool screen --style balanced --top 20
```

`--style` picks the pillar mix: `balanced`, `value`, `quality`, `growth`.

**Read this before using it.** Unlike every other command here, this one is
**not backtested and cannot be**. yfinance serves fundamentals as they stand
today, with no point-in-time history — applying today's P/E to a 2015 date
would mean "discovering" that profitable companies outperformed using the
profits they went on to report. That's lookahead bias of the worst kind, so the
module deliberately has no backtest entry point. Treat the output as a
shortlist to research, not a strategy with a track record.

Testing this honestly needs point-in-time data (Screener.in, Tijori,
Capitaline) where each date sees only what had been published by then.

### Sector-neutral by default

Ranking is done **within each sector**, not across the whole universe. This
matters more than it sounds. Ranked cross-sector, the first version of this
screen returned 11 Financials in its top 20 — not because banks were good, but
because banks structurally trade on lower P/E and P/B than software or consumer
names. A naive screen doesn't find good companies; it finds the cheapest
sector and fills the shortlist with it.

Sectors with fewer than 5 members in the universe fall back to a universe-wide
rank rather than crowning the best of three. `--cross-sector` disables sector
neutrality if you want to see the effect yourself.

Metrics that don't apply are skipped rather than fudged — debt/equity is
dropped for banks, whose balance sheets are debt by construction.

### Reading the `cov` column

`cov` is how many of the 9 metrics actually had data. **Check it before
trusting a rank.** A pillar with fewer than 2 usable metrics abstains rather
than voting, so a company missing data gets scored on its remaining pillars —
which can flatter it. Banks routinely show `qual --` and ride a high
value/growth score to the top of the list. A `9/9` rank is evidence; a `5/9`
rank is a hypothesis.

### Importing a Screener.in export

Screener lets you export a screen's results from its own UI, so no scraping is
involved:

```
.venv/Scripts/python -m trading_tool screen --from-file screen.csv --show-mapping
```

The parser is tolerant by design — Screener's export columns are user-
configurable via "edit columns", so there is no fixed schema. Each canonical
metric declares patterns that identify it, headers match case- and
punctuation-insensitively, and unrecognised columns are *reported*, not
silently dropped. `--show-mapping` prints exactly what was matched to what.

Your export must include the **NSE Code** column (add it via "edit columns") —
without it there's no way to tie rows to tickers.

Units are normalised on import, since Screener and yfinance disagree:

| Screener | yfinance | factor |
|---|---|---|
| ROE `18.5` (%) | `0.185` | ÷ 100 |
| Debt/Eq `0.5` (ratio) | `50.0` (%) | × 100 |
| Mar Cap `1,234` (Cr) | `12_340_000_000` | × 1e7 |

**Verified against a synthetic file only.** I built the test fixture from
Screener's documented column names, not a real download — the exact headers
aren't published anywhere. Run `--show-mapping` on your first real export and
check the mapping; if a column was missed, its pattern goes in `COLUMN_SPECS`
in `screener_import.py`.

## NSE point-in-time fundamentals

The only fundamental source here that supports **honest backtesting**.

```
.venv/Scripts/python -m trading_tool nse-fundamentals -u nifty10 --as-of 2022-06-30
```

NSE's `corporates-financial-results` endpoint (open, and permitted by their
`robots.txt`) returns every quarterly filing with a **`filingDate`** — the
moment it became public. That timestamp is what makes point-in-time queries
possible: `nse.as_of(data, "2022-06-30")` filters on *filing date*, never on
period end, so a result stays invisible until the day it was announced.
yfinance and Screener both serve current figures with no such timestamp, which
is precisely why neither can be backtested.

**Coverage, measured not assumed.** Filing metadata goes back to 2007, but NSE
purges the XBRL documents. Sampling three companies across every year: 2019–2025
fully available, 2018 partial, 2017 and earlier 404 without exception. Treat
**2019 onward** as the usable window — about 7 years, spanning the COVID crash,
the 2022 correction and the recent flat market.

Prices still come from yfinance; NSE's other endpoints return 403.

### Three traps in the XBRL, and how they're handled

Every one of these was found by spot-checking parsed numbers against real
filings. All three fail *silently* — the parser returns plausible figures that
are simply wrong.

1. **`One*` is the quarter; `Four*` is year-to-date.** Established empirically:
   across Q1–Q4 the `Four` figures sit at 1×, 2×, 3× and ~3.9× the `One` ones.
   Reading `Four` as the quarter overstates Q3 by threefold. The parser reads
   `One`.
2. **Banks use a different taxonomy.** No `RevenueFromOperations` anywhere —
   they file "Banking Format" with `InterestEarned`, `ProfitLossForThePeriod`.
   Before this was handled, every bank silently returned no data at all. Both
   vocabularies now map into one schema.
3. **The filing metadata's period disagrees with the document's.** Metadata may
   say `01-Oct→31-Dec` where the XBRL says `DateOfStartOfReportingPeriod:
   2024-04-01`. The document wins.

Also: standalone and consolidated are *separate filings*, not separate contexts.
`--basis` picks one, falling back per-quarter when only the other exists, since
dropping a quarter would tear a hole in the trailing-twelve-month sums.

### Verification

The spot check exists to be checked. Current output against published results:

| | parsed | reality |
|---|---|---|
| TCS Q3 FY25 revenue | ₹63,973 cr | ✓ |
| Reliance Q3 FY25 revenue | ₹2,43,865 cr | ✓ |
| TCS TTM revenue @ Jun-2022 | ₹1,91,754 cr | ✓ = TCS FY22 |

Re-run the spot check after any parser change. A backtest built on
silently-wrong fundamentals is worse than no backtest.

## Architecture

```
src/trading_tool/
  config.py           BacktestConfig + CostConfig (all the knobs)
  universe.py         Nifty 50 / Nifty 10 ticker lists, Yahoo suffixes
  data/loader.py      yfinance -> parquet cache -> PriceData panels
  fundamentals.py     fundamental metrics + sector-neutral screening
  screener_import.py  tolerant parser for Screener.in exports
  nse.py              point-in-time fundamentals from NSE filings (XBRL)
  strategies/
    base.py           Strategy ABC; SignalStrategy for per-symbol signals
    indicators.py     SMA, EMA, RSI, ATR, Donchian channels
    trend.py          the four shipped strategies
  backtest/
    engine.py         portfolio simulation loop
    costs.py          Indian transaction-cost model
    metrics.py        CAGR, Sharpe, Sortino, drawdown, turnover
  report.py           console summary + equity/drawdown chart
  cli.py              argparse entrypoint
```

### Adding a strategy

Subclass `SignalStrategy`, return 1.0 where you want to be long, and register
it. The engine handles lag, position caps, costs and cash:

```python
class MyStrategy(SignalStrategy):
    """One-line description shown by list-strategies."""
    name = "my_strategy"

    def __init__(self, window: int = 20):
        self.window = window

    def signal(self, bars: pd.DataFrame) -> pd.Series:
        return (bars["close"] > sma(bars["close"], self.window)).astype(float)
```

Then add it to `REGISTRY` in `strategies/__init__.py`.

For cross-sectional ideas (rank the universe, hold the top N), subclass
`Strategy` directly and implement `generate_weights` over the whole panel.

## How the simulation works

**Timing.** Signals are computed from data up to and including the close of day
`t`, then held for day `t+1`. The engine applies that one-bar lag itself by
shifting the weight matrix, so a strategy *cannot* accidentally trade on
information it wouldn't have had.

**Execution.** Fills at the close plus a slippage haircut (default 5 bps).
Reasonable for Nifty 50 names; optimistic for anything illiquid.

**Rebalancing.** Positions are re-sized weekly by default (`--rebalance`), and
only when they've drifted past `rebalance_threshold`. Exits always execute the
day the signal drops — deferring a risk-reducing trade to month-end would not
be realism.

**Costs** (per `config.py`, delivery/CNC at a discount broker):
STT 0.1% each side · stamp duty 0.015% on buy · NSE txn 0.00297% · SEBI ₹10/cr
· 18% GST on brokerage+txn+SEBI · zero brokerage · 5 bps slippage.
These rates change — check them against a current contract note.

## Known limitations

These matter, and none of them are hidden by the output:

- **Survivorship bias.** Uses today's Nifty 50 over all history. Real results
  would be worse. This is the single biggest overstatement in the numbers.
- **Daily bars only.** No intraday, no gap/limit modelling, no circuit breakers.
- **No liquidity check.** Assumes you can always fill at the close. Fine for
  ₹10L on large caps, not for size or for small caps.
- **Long-only, no leverage, no shorting, no F&O.**
- **Taxes on gains are not modelled** — only transaction costs. STCG/LTCG would
  take another meaningful bite out of the high-turnover strategies.
- **yfinance data is unaudited.** Free adjusted-close data has occasional bad
  ticks and adjustment errors. For anything you'd trade real money on, verify
  against a paid feed.

## Next steps

- Walk-forward / out-of-sample splits, so parameters aren't tuned on the same
  data they're judged on (currently the easiest way to fool yourself here).
- Point-in-time index membership to kill the survivorship bias.
- Position sizing by volatility (ATR-based) rather than equal weight.
- Swap the data layer for Zerodha Kite to get clean data and a path to paper
  trading — `data/loader.py` is the only file that would change.
