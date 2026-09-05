# Point-in-Time Integrity and Historical Eligibility Audit

## Decision

**GO.** The accepted Research V2 engine and frozen walk-forward prediction
pipeline were already point-in-time safe. No accepted historical ranking used a
fundamental before its proven public-availability date, and no formation-price
anchor used a price after its ranking date. This audit therefore adds evidence,
adversarial regression coverage, and a reproducible offline audit command; it
does not rewrite frozen outputs or change either scoring formula.

The audit deliberately distinguishes a point-in-time ranking contract from the
current company-page fact layer. The latter combines current display evidence
from several providers and is not an authorized historical-fundamental input.

## Architecture and data lineage

| Research V2 input | Accepted source | Period/date represented | Availability rule | Historical selection | PIT status |
|---|---|---|---|---|---|
| 1Y return | cutoff-rebased accepted adjusted prices | ranking close and prior 1Y anchor | price observation date | latest observation on or before each target, within seven days | safe |
| 3Y CAGR | same price panel | ranking close and prior 3Y anchor | price observation date | backward-only anchor | safe |
| 5Y CAGR | same price panel | ranking close and prior 5Y anchor | price observation date | backward-only anchor | safe |
| Recorded-high recency | same price panel | complete recorded history through ranking date | price observation date | maximum uses only observations through selected current anchor; repeated highs use latest date | safe |
| 1Y annualized volatility | same price panel | trailing daily simple returns | price observation date | selected 1Y anchor through selected current anchor; sample standard deviation × sqrt(252) | safe |
| 3Y maximum drawdown | same price panel | trailing three-year adjusted-price path | price observation date | selected 3Y anchor through selected current anchor | safe |
| ROCE | reviewed official NSE-hosted audited standalone annual report | required fiscal year | official exchange dissemination timestamp/date | only mapped direct disclosure with availability on or before ranking cutoff | safe but narrow |
| Debt-to-equity | same annual report and basis | required fiscal year | same official dissemination evidence | same strict selector; substitutes prohibited | safe but narrow |
| YoY profit growth | current/prior annual PAT from the same reviewed report | required and comparable prior fiscal years | same official dissemination evidence | derived only after the report is eligible | safe but narrow |

The general Research V2 CSV contract requires
`(ticker, period_end, available_date)` as the revision-aware natural key. It
first validates dates and keys, then filters both `period_end <= ranking_date`
and `available_date <= ranking_date`. For each ticker it selects the greatest
eligible period end and then the greatest availability date for that period.
Numeric validation occurs only after future records are removed.

The real annual-report builder is stricter: it requires an official exchange
timestamp no later than the explicit 15:30 IST cutoff. The frozen walk-forward
mapping additionally requires the preregistered fiscal year, standalone basis,
direct disclosures, exact pages/tables, and PDF hashes.

## Price formation and outcomes

`_anchor` considers only prices with `date <= target`; the seven-day tolerance
can reject a stale prior observation but can never select a following trading
day. The frozen blind pipeline rejects any predictor row after its cutoff and
rebases adjusted history at the cutoff. Its four accepted maximum formation
dates exactly equal the four ranking dates.

Future prices are permitted only in the separately acquired outcome/label
artifacts. The label contract requires `label_end_date > as_of_date`. Outcome
columns are prohibited from blind predictor artifacts. Cross-sectional scores
and ranks are calculated only after stock-level price and fundamental
eligibility, so rejected rows do not influence sector component scores.

## Concrete adversarial evidence

No confirmed ranking leakage was found; consequently there is no invalid
"value used before fix." The cached source evidence proves that the guards are
material rather than ceremonial:

- For 2022-08-05, four archive reports were classified post-cutoff and three
  more exact NSE announcement searches resolved only to post-cutoff evidence.
  MARUTI's revised FY2021-22 report was disseminated on 2022-08-08 and was
  rejected for the 2022-08-05 ranking.
- RELIANCE's required FY2021-22 annual-report candidate was marked
  `POST_CUTOFF_ANNUAL_REPORT` for 2022-08-05.
- APOLLOHOSP's required FY2022-23 report was marked post-cutoff for 2023-08-07.
- The four frozen dates rejected 22 proven post-cutoff filing candidates in
  total and left 75 candidates unavailable because exact timing remained
  unproven or the attachment was ambiguous.
- The current all-market exchange cache contains 4,355 financial-fact rows for
  2,146 issuers whose represented periods ended by 2025-08-07 but whose source
  filings were not available until 2026. A period-end-only historical selector
  would leak those rows. No accepted historical ranking reads this current
  display cache.

## Measured funnel

Current product state:

```text
Supported identities                         5,167
Product classified                           4,433
Current-product Baseline eligible             1,237
Exact identity usable within that cohort      1,237
Strict required fundamentals available            34
PIT-safe Research V2 eligible                     34
```

Historical accepted snapshots:

| Ranking date | Investable | Identity resolved | Baseline eligible | Strict fundamentals | PIT-safe V2 | Unproven availability | Proven late filings rejected |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022-08-05 | 50 | 48 | 46 | 8 | 8 | 25 | 7 |
| 2023-08-07 | 50 | 49 | 48 | 4 | 4 | 31 | 3 |
| 2024-08-07 | 50 | 48 | 48 | 8 | 8 | 19 | 6 |
| 2025-08-07 | 50 | 49 | 47 | 16 | 16 | 0 | 6 |

The previously accepted historical selector was already the strict selector.
Therefore before/after eligibility is unchanged, zero factor values changed,
zero selected statements changed, and zero new exclusions were introduced.
This is evidence of prior correctness, not a relaxed audit.

## Identity, corporate actions, and survivorship

The walk-forward universe uses official historical NIFTY 50 constituent
snapshots rather than projecting today's NIFTY 50 backward. The July 2023
`DUMMYREL` corporate-action placeholder remains non-investable; HDFC is not
substituted with HDFCBANK; unresolved provider histories remain excluded.
Historical provider aliases are declarative and audited, but comprehensive
ISIN-vintage continuity across all mergers, demergers, and symbol changes is
not claimed.

The cutoff rebase reduces later corporate-action contamination in provider
adjusted history, and repair sensitivity is preserved. Yahoo's historical
adjustment and repair process is nevertheless not a complete official
security-level corporate-action vintage ledger.

## Restatements and unresolved limitations

Point-in-time availability safety is not the same as perfect historical
vendor-vintage reconstruction. Accepted annual-report PDFs and exchange
timestamps preserve original source evidence for the mapped cohort, but the
all-market normalized exchange cache is a current reconstruction and may
contain comparative facts or later revisions. It is prohibited as a shortcut
for frozen historical rankings.

The generic Research V2 CSV uses calendar-day availability. Same-day records
are treated as available on that date. Real annual-report preparation uses an
explicit timestamp cutoff, but a future intraday strategy would need a
timestamp-level feature contract throughout.

Current company pages select current display facts from official and secondary
stores. Some display datasets do not carry proven historical availability
dates. They remain useful current provenance, but they must never be passed to
historical Research V2 merely because their `period_end` precedes a cutoff.

Historical coverage remains limited to four official NIFTY 50 snapshots and a
narrow direct-disclosure standalone contract. It is not a survivorship-free
all-Indian-equity panel, Alpha benchmark reproduction, or real-market return
claim beyond the separately frozen evaluation.

## Reproduction

No provider or network call is required:

```powershell
.\.venv\Scripts\python.exe marketdata\runners\audit_point_in_time_integrity.py `
  --output data\point_in_time\integrity_audit_v1.json
```

Two independent runs produced byte-identical JSON with SHA-256
`c005faedd88bd867a7c516e2bed7fb89bcd0a7b9e4c5f83f01e1b66aee8d7323`.
The output is ignored evidence; accepted historical bundles remain unchanged.

## Next step

Use one explicitly PIT-safe eligible cohort for the separately authorized
Baseline V1 versus Research V2 comparison. Do not broaden coverage by inferred
filing lags, latest-current statements, or today's universe.
