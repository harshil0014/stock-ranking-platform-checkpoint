# Official exchange backbone

The current product state is built offline from immutable, hash-verified
evidence. Browser requests never contact an exchange or secondary provider.
The refresh job first lands broad NSE/BSE catalogues, then normalizes linked
XBRL evidence, rebuilds a candidate company-fact snapshot, validates it, and
atomically changes the accepted pointer. A failed provider or candidate build
does not replace the last-known-good snapshot.

## Accepted 22 August 2026 acquisition

The accepted batch `official-backbone-20260822-04` contains 13,926 NSE
Integrated Filing rows (all pages), 3,816 legacy financial-result rows, 2,289
NSE shareholding rows, 929 NSE corporate-action rows, 72,327 NSE announcement
rows, and 361 BSE action rows. It selected 4,020 latest/annual XBRLs, downloaded
4,015, normalized 4,015 and retained five failures as failures. The canonical
stores contain 1,582,209 numeric financial facts for 2,269 issuers, 60,308
shareholding observations for 2,929 issuers, 997 actions for 912 issuers, and
72,477 document records for 2,525 issuers.

The resulting 5,093-security company snapshot has 2,146 official annual
statement periods, 2,269 official quarterly/YTD periods, 2,205 official
balance-sheet periods, 2,149 official cash-flow periods, and 2,464 issuers with
normalized shareholding. Statement basis, source concepts, contexts, units,
periods, revisions, URLs and source hashes remain available; unknown numeric
concepts are retained for later parser versions.

## Evidence and model boundaries

The 257 prior derived classifications were all supported only by an
identity-validated secondary provider. They are now explicitly
`DERIVED_SECONDARY_REFERENCE_ONLY`; none is ranking-grade. The 750 official
sector classifications remain `OFFICIAL`; 4,086 securities remain
`UNCLASSIFIED` in that acquisition audit. A later conservative Yahoo backlog
success raised the current reference-only count to 258 and reduced current
`UNCLASSIFIED` to 4,085; it remains non-ranking-grade. No classification
was guessed from a company name.

Official statement facts may populate informational valuation and quality
fields only when the needed values, units, period and basis are unambiguous.
Conventional debt-to-equity is not derived for banks, NBFCs, or insurers.
These informational formulas are versioned separately and do not feed the
accepted Baseline V1 or Research V2 contracts. Baseline remains 568 eligible
and strict Research V2 remains 34 eligible.

## Open-source attribution

The acquisition uses the MIT-licensed `nse-xbrl` approach as a taxonomy/parser
reference. It also consumes the `nse-historical-membership` shareholding
dataset at commit `0e9f58c4d457faf0e7ad3db4f4c1449e697e23e0`; its code is MIT
and the derived data is CC BY 4.0. The project did not copy GPL BSE wrapper
code. BSE transport uses official public BSE endpoints and exact scrip-code /
ISIN reconciliation.

## Recurring operation

`stock-ranker data-refresh` checks official sources independently of the
secondary queue. Yahoo is a secondary, conservative, persistent backlog: a
small sequential batch is attempted, a rate limit stops that provider queue,
and accepted cached facts are retained. Provider outages therefore cannot
erase official evidence or take the website down. Raw catalogues and linked
evidence are retained under ignored immutable batches; generated coverage,
inventory and exclusion reports are written beneath
`data/company_facts/reports/`.

The remaining gaps are explicit: broad BSE financial-statement normalization,
official all-listed classification delivery, BSE corporate-action-aware price
history, and strict audited standalone ratio definitions. They are not filled
from Yahoo or Screener and are not described as model eligibility.
