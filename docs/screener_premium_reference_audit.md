# User-Supplied Screener Premium Reference Audit

Two user-supplied exports were audited on 2026-08-29. They are secondary
current-reference evidence only; the system does not scrape Screener, depend on
it at runtime, redistribute the exports, or use their values as historical
point-in-time facts.

| Export | Rows | SHA-256 |
|---|---:|---|
| `query-results.csv` | 5,442 | `47ea4773220f6c784c210e9f2a95e07c3b08185e0993e7290e760c42bcf0c744` |
| `query-results (1).csv` | 5,442 | `d8c973c7223c6872f935f06cdc2096235965e02bcaf209967814e394906dd003` |

Both contain 5,442 unique valid ISINs. The second file is a strict field subset
for the accounting fields used here; the overlapping identity, ROCE,
debt-to-equity, PAT and profit-growth values have zero conflicts. Against the
current 5,096-company fact layer, exact ISIN matching finds 4,440 companies.
There are 4,176 exact matches with all four reference metrics and 4,133 of
those are not currently strict Research V2 eligible.

That large apparent opportunity is not PIT-safe coverage. The exports contain
no issuer filing identifier, official dissemination timestamp, reporting
period, standalone/consolidated basis, units for PAT, restatement lineage, or
issuer ratio definition. Consequently:

- no fuzzy company or ticker match is allowed;
- every source file and canonical reference row is fingerprinted;
- conflicting exports remain explicit rather than silently choosing one;
- `historical_pit_eligible` is always false;
- values never enter the canonical company-fact store or Research V2;
- the data may prioritize official-report review and cross-check likely parser
  mistakes, but the official filing remains the acceptance authority.

The reproducible audit is `marketdata/runners/audit_screener_premium_exports.py`.
Its ignored output includes exact identity matches, field conflicts, canonical
reference rows and a manifest. The canonical reference fingerprint for these
two exports is
`5303eec99dd7a12851087b39e1ea30b54d80de72d1dc507da0326c16cf7e58ee`.

Current-reference disagreement with a statutory standalone report is not
automatically an error: it can reflect a newer observation date, trailing
period, consolidated basis or a different ratio convention. Such differences
are review signals, never replacement values.
