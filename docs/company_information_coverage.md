# Provider-independent company information layer

The company-information layer is an offline, accepted snapshot keyed by ISIN.
It is designed against the breadth of a useful Indian-equity research page;
Screener.in is only a coverage checklist. The system does not scrape, copy, or
depend on Screener.

## Accepted snapshot

- Schema: `company_fact_layer_v1`
- Market date: 2026-08-19
- Market fingerprint: `8a1ef7cd21703b989c33cd439f2147ab823a00b0c6bc76606da0b70de1d8a53b`
- Company-fact fingerprint: `b64e8843125f61bee3434687fcf2e3b0c684ef83301bec1f38d104bece00a57a`
- Canonical identities: 5,093 unique ISINs

The build consumes only accepted local market, history, annual-report and
professor evidence. It makes no provider request during website navigation.
An immutable snapshot is hash-validated before an atomic accepted-state
pointer is changed. A failed candidate leaves the prior snapshot active.

## Measured coverage

| Category | Count | Percent |
|---|---:|---:|
| Canonical identity | 5,093 | 100.0000% |
| Accepted current/latest price | 5,092 | 99.9804% |
| Official sector-tier classification | 750 | 14.7261% |
| Accepted adjusted history | 2,531 | 49.6957% |
| Usable 1Y history | 2,150 | 42.2148% |
| Usable 3Y history | 1,883 | 36.9723% |
| Usable 5Y history | 1,676 | 32.9079% |
| Annual report or official document link | 2,007 | 39.4070% |
| Official XBRL annual statements | 2,146 | 42.1363% |
| Official XBRL quarterly/YTD statements | 2,269 | 44.5513% |
| Official XBRL balance sheets | 2,205 | 43.2947% |
| Official XBRL cash flows | 2,149 | 42.1952% |
| Normalized shareholding | 2,464 | 48.3801% |
| Official/secondary corporate actions | 970 | 19.0457% |
| ROCE / debt-to-equity / profit growth | 34 each | 0.6676% |
| Baseline V1 eligible | 568 | 11.1526% |
| Strict Research V2 eligible | 34 | 0.6676% |
| Identity-validated secondary company profiles | 574 | 11.2704% |
| Market cap / share count (primary or secondary) | 951 | 18.6727% |
| Valuation (at least one accepted field) | 945 | 18.5549% |
| Annual financial evidence (primary or secondary) | 2,224 | 43.6678% |
| Quarterly financial evidence (primary or secondary) | 2,309 | 45.3367% |
| Balance sheets / cash flows (primary or secondary) | 2,259 / 2,220 | 44.3550% / 43.5892% |
| Derived secondary classification reference (not used by models) | 258 | 5.0658% |

The professor acceptance file contains 99 requested rows representing 98
unique securities. Ninety-seven requests (96 unique securities) are in the
current supported market state. The two BSE-only securities outside that state
remain fully visible in the separate professor-acceptance evidence rather than
being silently inserted into today's traded-security denominator.

Remaining zeroes are deliberately visible. They mean the repository has not yet accepted
the required normalized evidence—not that the field does not exist publicly.
The UI supplies a specific status and the official discovery route instead of
inventing a value or presenting a meaningless empty card.

## Page contract

Each company page traverses Company Overview, Classification, Market Data,
Price History Evidence, Valuation, Quarterly Results, Annual Financials,
Balance Sheet, Cash Flow, Ratios/Quality, Shareholding, Peers, Corporate
Actions/Announcements/Documents, Professor Reference, Baseline V1, Research
V2, Why This Rank, Source Evidence and Historical Validation.

Official taxonomy, professor workbook taxonomy and any future derived research
taxonomy are separate fields. A derived taxonomy may be populated only from
reproducible business evidence; company-name guessing and opaque prediction
are prohibited. Peers share an accepted classification and never cause ranks
to be recalculated.

For banks, insurers and similar institutions, missing conventional industrial
ROCE or leverage is labelled non-comparable rather than forced into an
industrial formula. Standalone/consolidated basis, periods, source URLs and
document hashes remain attached to accepted annual facts.

## Refresh

```powershell
.\.venv\Scripts\stock-ranker.exe company-facts --dry-run
.\.venv\Scripts\stock-ranker.exe company-facts
```

The first command validates and fingerprints the complete in-memory candidate
without writing. The second writes an immutable snapshot beneath ignored
`data/company_facts/`, validates all artifact hashes and atomically advances
`accepted_state.json`. Current-market refresh and fact-layer refresh are
separate so a new EOD snapshot cannot mutate frozen historical research.

## Unresolved external data limitations

Broad official four-tier classification, BSE adjusted histories, broader BSE
financial-statement normalization, historical filing backfill and strict
standalone ratio-definition coverage still require additional exchange archive
acquisition. NSE XBRL statements, Regulation 31 ownership, action ledgers and
document indexes are now implemented at bulk scale. The legitimate source priority and
legal/technical constraints are maintained in
`marketdata/specifications/data_source_matrix.json` and
`marketdata/specifications/company_fact_contract_v1.json`.

The real Yahoo scale attempt requested all 2,558 mapped identities. A later
conservative backlog drain has accepted 577 exact identities, permanently
rejected one unresolved identity and retained 1,980 pending items. It did not
relabel provider errors as missing company data. The corrected professor-plus-stratified
benchmark independently accepted 345/346. Broader refresh uses resumable
checkpoints and continues from the last-known-good state.

The result materially reduces empty-page categories but remains **PARTIAL**
rather than falsely claiming Screener-level parity. No ranking rule, V2
eligibility rule or frozen research fingerprint changed.
