# Real NIFTY 50 point-in-time Research V2

## Status and lineage

This milestone is an official-data integration, not a new scoring method.
Baseline V1 is the project's transparent approximation of the
professor-paper signals. Research V2 is the project's separate point-in-time
extension. Qlib reproductions are a separate machine-learning research track.

The accepted Research V2 implementation, formulas, directions, weights,
eligibility rules, within-sector rank-range component normalization, ties, and
outputs are unchanged. Component scores describe relative within-sector rank
position, not the magnitude of financial superiority.

## Frozen inputs and availability

The universe is the current NIFTY 50 from the accepted official 7 August 2026
snapshot. Prices come unchanged from the accepted frozen Baseline bundle:
repaired Yahoo `Adj Close` through `yfinance==1.5.1`, with its symbol mapping,
security-history boundaries, corporate-action audit, and upstream dividend
adjustment semantics.

Fundamental acquisition uses only the official NSE Integrated Filing –
Financials metadata endpoint and official NSE archive XBRLs. Product and
website execution make no network requests. The canonical availability time
is the NSE exchange dissemination timestamp (`creation_Date`); broadcast time
is retained separately. The cutoff is `2026-08-07T15:30:00+05:30`, the close
of the ranking trading session in IST. Full timestamps—not truncated dates—are
used to select filings.

For each company, preparation first excludes post-cutoff versions, selects the
latest eligible 31 March annual period, requires consolidated statements, and
then selects the latest exchange-disseminated version for that period. A later
revision cannot rewrite an earlier snapshot. Original/revision metadata,
remarks, statement basis, audit label, concept/context provenance, and source
hashes are retained. No consolidated/standalone mixing occurs.

The audited BAJAJFINSV example is an original, consolidated 31 March 2026
filing broadcast at `30-Apr-2026 23:08:23` and exchange-disseminated at
`30-Apr-2026 23:08:27`. Its official XBRL SHA-256 is
`6190a4c0d4c99af85a9406d00db06f5286237e2bc148fe515e5430ef0c86bc1d`;
the separately supplied NSE metadata-export sample SHA-256 is
`f90f5c51f8e530f1958d2283eeb75a2722bf475b9937f7ec46ca6193f6c4848d`.
These values audit the general schema and do not trigger ticker-specific
parsing.

## Exact mapping policy

Research V2 continues to accept precomputed `roce`, `debt_to_equity`, and
`profit_growth_yoy`; its scoring source defines no underlying accounting-ratio
formula. The separate real-data contract is
`nse_audited_standalone_fundamentals_v1`, displayed as **NSE Audited
Standalone Fundamentals v1**. It requires all three inputs to use the audited
standalone FY2025-26 basis: an issuer-disclosed ROCE, an issuer-disclosed
debt-to-equity ratio, and statutory reported PAT for FY2025-26 and its
FY2024-25 comparable. Profit growth alone uses the existing YoY expression.

The declarative mapping retains the exact labels, values, pages, statutory
table/section, issuer ratio definitions, report metadata, and warnings. It
performs no fuzzy match, ticker-specific code branch, derivation, imputation,
or proxy substitution. Management highlights cannot override the statutory
ratio table. Explicit zero is a value; a missing fact is not zero. Consolidated
values never become donor fundamentals for this standalone contract.

Observed official taxonomy families are `INDAS`, `BANKING`, `NBFC_INDAS`, and
`LI`. In particular, ROA/ROE is not ROCE, liabilities/equity is not silently
treated as debt/equity, and revenue growth is not profit growth. Ambiguous
facts are excluded rather than chosen by document order.

## Immutable Research V2 method

The nine raw metrics and percentage weights are:

| Metric | Weight | Direction |
| --- | ---: | --- |
| one-year return | 10 | higher |
| three-year CAGR | 10 | higher |
| five-year CAGR | 10 | higher |
| days since recorded high | 5 | lower |
| one-year annualized volatility | 12.5 | lower |
| three-year maximum drawdown | 12.5 | higher (nearer zero) |
| ROCE | 15 | higher |
| debt-to-equity | 10 | lower |
| YoY profit growth | 15 | higher |

Price formulas, sample-volatility annualization, drawdown, anchor tolerances,
latest repeated-high handling, negative-leverage exclusion, and final scoring
are exactly those in `docs/research_v2_methodology.md`.

## Reproducibility and result

Preparation was executed twice from the same frozen raw inputs without a
refetch. Both runs selected the same filings and produced byte-equivalent
canonical artifacts and the same bundle fingerprint. The prepared bundle
contains canonical universe, prices, fundamentals, eligibility, rankings,
comparison, filing provenance, mapping, metadata, and a SHA-256 manifest. Raw
NSE metadata/XBRL and the prepared bundle remain ignored.

All 50 companies receive a deterministic status. The Integrated Filing XBRL
stage remains preserved as corroborating evidence. Because it supplied no
complete canonical rows, an additive annual-report rescue uses official
NSE-hosted FY2025-26 PDFs disseminated before the same cutoff. `pypdf==6.15.0`
(BSD-3-Clause) runs only in `.venv-marketdata`; the product environment and
offline website do not import it.

Annual-report metadata discovery found 46 eligible FY2025-26 reports; four had
none by the cutoff. Forty-four PDFs were conservatively extracted and two were
rejected because strict PDF extraction failed. Keyword candidates are coverage
evidence only and never become fundamentals automatically. The reviewed
standalone mapping admits 34 companies across 13 sectors and excludes 16.
RELIANCE, for example, uses its standalone statutory ratio table: ROCE 20.7%,
Debt:Equity 0.41, and reported PAT of INR 43,851 crore versus INR 35,262 crore;
the exact pages, labels, issuer formula text, submission metadata, and hashes
remain in provenance.

The comparison has three distinct rank fields. The original Baseline V1
sector rank is retained as context. The unchanged Baseline V1 engine is then
rerun on exactly the 34-stock Research V2 eligible cohort to produce a matched
Baseline sector rank. Only `matched_baseline_sector_rank -
research_v2_sector_rank` is reported as movement. Eligible peer count is
explicit; sectors with one eligible company are marked
`SINGLE_ELIGIBLE_PEER`, have null movement, and are scientifically
non-informative. Raw Baseline and Research V2 score magnitudes are not
comparable.

SBI remains excluded because ROA/ROE cannot replace ROCE. SHRIRAMFIN remains
excluded despite debt-equity and profit disclosure because it has no explicit
ROCE. HDFCLIFE remains excluded because ROE, ROEV, and return on invested
capital are prohibited substitutes. Other unreviewed candidates remain
ambiguous rather than being accepted from a first keyword occurrence.

## Limitations

- Current constituents create survivorship bias; there is no historical
  constituent universe.
- This is one `2026-08-07` snapshot, not walk-forward evaluation or a backtest.
- NSE taxonomy and explicit-ratio coverage are incomplete.
- Issuer ROCE definitions may vary; exact labels, pages, formulas, and basis
  are preserved instead of normalizing them silently.
- Standalone reporting was selected because it provides the broadest
  internally consistent audited statutory-ratio coverage under one basis, not
  because standalone economics are universally superior. It may omit material
  economics of consolidated groups.
- Adjusted, exceptional, discontinued, or re-presented profit disclosures are
  surfaced as warnings; the project applies no custom normalization.
- PDF extraction is imperfect; unreadable or basis-ambiguous reports are
  excluded.
- Yahoo adjusted-price semantics are inherited from the accepted price source.
- There is no transaction-cost, liquidity, portfolio-construction,
  optimization, profitability, real-market performance, or investment claim.
- The output is research screening only and is not investment advice.

Research V2 changes some ordering relative to Baseline V1 on a matched eligible
cohort. Whether those changes improve future-return ranking quality requires
walk-forward evaluation.
