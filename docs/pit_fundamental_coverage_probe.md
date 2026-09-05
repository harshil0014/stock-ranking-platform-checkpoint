# Point-in-time fundamental coverage probe

## Outcome

The 50-security probe is **PARTIAL and did not pass the scale gate**. It found
14 exact-identity reports containing candidates for all three required
disclosures, but none is a constructed Research V2 record until its standalone
tables, values, units, current/prior profit pair, and formulas receive the same
review used by `nse_audited_standalone_fundamentals_v1`. The current 34-stock
cohort, formulas, weights, rankings, historical experiments, and fingerprints
were not changed.

This is a useful negative boundary rather than a data-source failure. The free,
official route exists and can plausibly create many more records, but fully
automatic text promotion would weaken the accepted contract.

## Exact V2 input audit

Research V2 uses nine metrics. Six come from point-in-time adjusted prices:
one-year return, three- and five-year CAGR, recorded-high recency, one-year
annualized volatility, and three-year maximum drawdown. The three filing inputs
are:

| Canonical field | Accepted meaning |
|---|---|
| `roce` | Issuer-disclosed audited standalone Return on Capital Employed |
| `debt_to_equity` | Issuer-disclosed audited standalone debt-equity ratio |
| `profit_growth_yoy` | Current divided by comparable prior audited standalone annual profit, minus one |

Each record also requires exact security identity, `period_end`, and the real
exchange dissemination time used as `available_date`. No proxy ratio, derived
ROCE, derived leverage, imputation, or standalone/consolidated mixing is
permitted.

## Deterministic probe

The population was the 1,198 exact-ISIN NSE securities that were current-product
Baseline eligible but not already V2 eligible. Fifty were selected by ascending
SHA-256 of ISIN, giving 16 sectors. The cutoff was 21 August 2026 and the target
report was FY2025-26.

### Official structured XBRL

After filtering to standalone annual facts with both `period_end` and
`available_at` no later than the cutoff:

| Measure | Securities |
|---|---:|
| Represented | 48/50 |
| Annual profit | 47/50 |
| Exact `DebtEquityRatio` | 9/50 |
| Exact `ReturnOnCapitalEmployed` | 0/50 |
| Complete strict V2 filing inputs | **0/50** |

The XBRL is therefore an excellent PIT-safe profit and accounting backbone, but
not a complete V2 source. Raw-value derivation was intentionally not attempted.

### Official annual reports

| Gate | Securities |
|---|---:|
| Eligible report disseminated by cutoff | 22/50 |
| PDF extracted successfully | 22/22 |
| Exact current ISIN present in report text | 18/50 |
| Explicit ROCE candidate | 18/50 |
| Explicit debt-equity candidate | 22/50 |
| Annual profit candidate | 21/50 |
| All candidates plus exact identity and timestamp | 14/50 |
| Fully reviewed, constructed new PIT-safe V2 records | **0/50** |

Final statuses were 14 complete disclosure candidates requiring review, four
reports without the exact current ISIN in extracted text, four missing direct
ROCE, and 28 with no eligible FY2025-26 annual report by the cutoff. The 14
candidate tickers are SHRIPISTON, IDEA, IGARASHI, POWERINDIA, BLUESTARCO, TRF,
TRIDENT, SHALBY, AMBUJACEM, PVRINOX, VIMTALABS, TVTODAY, BOSCHLTD, and
SHEKHAWATI. This list is a review queue, not an eligibility list.

The report availability result is expected during filing season. NSE states
that its annual-report page contains company submissions and exposes exchange
received/dissemination times. SEBI LODR Regulation 34 requires listed entities
to submit annual reports to the exchange, while the Ministry of Corporate
Affairs' Schedule III amendment requires disclosure of Return on Capital
Employed and the numerator/denominator used for the listed ratios. These make
the annual report the best free primary source for the missing ROCE evidence:

- [NSE corporate annual reports](https://www.nseindia.com/companies-listing/corporate-filings-annual-reports)
- [SEBI LODR regulations, annual-report requirement](https://www.sebi.gov.in/sebi_data/attachdocs/jan-2023/1674822905952.pdf)
- [MCA Schedule III ratio disclosures](https://www.mca.gov.in/Ministry/pdf/ScheduleIIIAmendmentNotification_24032021.pdf)

## Source and fallback decision

1. **Primary:** NSE annual-report metadata and archive PDF, linked through the
   exact NSE master identity and proven again by ISIN in the report.
2. **Structured companion:** NSE integrated-results XBRL for timestamped profit
   and cross-checking, never as a substitute for absent direct ROCE.
3. **Free fallback:** the issuer's BSE annual-report/corporate filing for a
   dual-listed exact ISIN, only when BSE provides an official dissemination
   timestamp and the same audited standalone basis. This probe did not count an
   untested BSE record.
4. **Issuer website:** corroboration only; it cannot establish the original
   market availability time by itself.

The next safe engineering step is a review tool that presents the exact report
page/table/formula and requires an explicit mapping decision. Once at least 10
of this fixed 50-security sample are reviewed complete (20%), rerun the same
gate. Only then should metadata discovery scale across the 1,198-security
population. Reports that arrive after a ranking cutoff remain unavailable for
that date even if they are downloadable today.

## Reproduction and evidence

The source-controlled protocol is
`marketdata/specifications/pit_fundamental_coverage_probe_v1.json`. Generated
PDFs, extracted text, the coverage matrix, summaries, and inventories are kept
under ignored `data/marketdata/pit-fundamental-probe-2026-08-21-50*` paths.
The final summary SHA-256 is
`265f67885523c7d7ff4a3242249e73d2b64f149b3f4738c691188c92ba3c47d2` and the
coverage-matrix SHA-256 is
`12d832d6f59d78b8aee03a7f972ad447742f1b5ed186d2c4e94521dd904ed52a`.

No multi-year monthly backtest or future-outcome inspection was started.
