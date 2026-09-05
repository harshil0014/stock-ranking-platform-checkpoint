# Free Classification Attempt 3: Official BSE to Yahoo Exact Bridge

## Decision

**GO.** The bridge classified 1,886 of 2,610 previously unclassified
BSE-only securities (72.26%) without fuzzy names, guessed symbols, identity
conflicts, or ambiguous sector membership. Combined with the independently
reproduced Yahoo NSE result, 3,346 of 4,080 unclassified securities receive a
current-product broad sector.

This is current-product evidence only. It does not change frozen historical
research, Professor Reference results, Research V2, or either ranking formula.

## Exact mechanism

For BSE securities, identity is accepted only through:

```text
canonical numeric BSE code
= official BSE ListofScripData SCRIP_CD
and canonical ISIN
= official BSE ISIN_NUMBER
and official nonblank scrip_id
-> exact scrip_id.BO
-> Yahoo exchange BSE and quoteType EQUITY
-> exactly one Yahoo bulk sector membership
```

For NSE securities, the existing canonical exchange symbol is converted only
to its exact `.NS` representation and must match Yahoo exchange `NSI`, type
`EQUITY`, and exactly one bulk sector membership.

No company name participates in either identity decision.

## Probe and full-run evidence

- Official BSE endpoint: `https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w`
- Official micro cross-check: `PeerSmartSearch/w`
- Yahoo mechanism: yfinance 1.5.1 `EquityQuery(region=in)` plus eleven bulk
  sector queries with deterministic pagination and 250-row pages.
- Representative sample: proportional allocation across official BSE group or
  unmatched strata; within each stratum, SHA-256 ordering using seed `20260823`,
  canonical code, and ISIN.
- Sample result: 70/100 accepted.
- Full BSE result: 1,886/2,610 accepted.
- Exact official code and ISIN: 2,094/2,610; conflicts: zero.
- Exact Yahoo `.BO` symbol: 2,092/2,094 exact identities.
- Full failures: 516 official active lookups absent, 205 without Yahoo sector,
  two Yahoo symbols absent, and one unclear/non-equity segment.
- Accepted wrong identities: zero.
- Ambiguous sector memberships: zero.

The accepted combined batch is stored in the ignored local evidence store
under `data/company_facts/providers/bulk_classification/`. It preserves raw
normalized inputs, classifications, all rejected rows, artifact hashes, a
manifest, and a deterministic fingerprint.

## Taxonomy boundary

Yahoo provides only its broad sector labels, such as `Technology`,
`Industrials`, or `Financial Services`. It does not establish BSE's official
Macro-Economic Sector -> Sector -> Industry -> Basic Industry hierarchy.
Official four-level BSE taxonomy coverage from this bridge is therefore zero.

The current Product Classification v1 Baseline needs a stable broad sector for
within-sector ranking, so this evidence is sufficient for that current-product
purpose. It is not sufficient for claims requiring official BSE industry or
basic-industry classification.

## Provenance and precedence

The product keeps this precedence:

```text
existing official classification
> existing richer exact-identity secondary observation
> exact bulk Yahoo sector with canonical NSE or official BSE identity
> unclassified
```

The classification provider is Yahoo. BSE is the identity authority for BSE
securities. The result must never be displayed as an official BSE industry
classification.

## Reproduction

Use the market-data environment; the product environment does not import
yfinance:

```powershell
.\.venv-marketdata\Scripts\python.exe marketdata\runners\acquire_bulk_classification.py `
  --batch-id <fresh-batch-id>

.\.venv\Scripts\python.exe marketdata\runners\prepare_company_facts.py
```

Classification is slow-changing reference data and is not polled during page
navigation or added to every daily market refresh.
