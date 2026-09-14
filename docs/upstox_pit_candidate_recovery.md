# Upstox PIT candidate recovery

## Purpose

Upstox Company Fundamentals is integrated as a **structured candidate source** for missing Research V2 accounting evidence. It is not used as the point-in-time clock and it does not change the Research V2 formula, market snapshot, or eligibility rules.

The API is useful because the financial-statement endpoints are keyed by exact ISIN and expose historical annual statement data. The acquisition runner requests the **standalone** income statement and balance sheet with full statement detail and stores immutable raw JSON plus SHA-256 hashes.

## Hard PIT boundary

A historical period label in a response fetched in September 2026 does not prove that the value was known at an earlier ranking date. Every normalized Upstox row is therefore stamped:

`REQUIRES_EXACT_OFFICIAL_FILING_MATCH`

Promotion remains behind the existing `pit_structured_fundamentals` contract. The old exchange filing must match exact ISIN, reporting basis and period, must have been disseminated before the ranking cutoff, and the structured values must be deterministically matched to the original hash-verified filing.

The Upstox **key-ratios** endpoint is deliberately not used for PIT. Upstox documents that endpoint as returning current company values for ROCE and the other ratios. A current ROCE cannot be backdated into Research V2.

## What Upstox can recover safely

The yearly income-statement endpoint provides historical net-profit values. The normalizer turns adjacent annual observations into `current_pat` / `prior_pat` candidate pairs for `profit_growth_yoy` after official filing verification.

The balance-sheet endpoint provides historical statement values and detailed line items. These are retained as structured search/reconciliation evidence, but this integration does **not** derive debt-to-equity or ROCE from them. The accepted Research V2 accounting contract currently requires issuer-reported ratios and forbids silent formula substitution.

This means Upstox reduces PDF/XBRL archaeology, especially for profit history and table location, without weakening the two difficult fields. Historical ROCE and debt-to-equity still need exact official disclosure/matching before promotion.

## Credentials

Use the free read-only Upstox Analytics Token. Never paste it into source files, command arguments, logs, or GitHub. The runner reads only the `UPSTOX_ACCESS_TOKEN` environment variable.

Windows CMD example:

```cmd
set UPSTOX_ACCESS_TOKEN=<paste token locally>
.venv-test\Scripts\python marketdata\runners\acquire_upstox_v2_candidates.py --company-facts data\company_facts\snapshots\<accepted-snapshot>\company_facts.csv --output data\point_in_time\upstox_v2_probe_20260914 --limit 100
```

`data/point_in_time/` is already ignored by Git, so raw authenticated responses remain local.

The default delay is 1.1 seconds per API request, intentionally conservative against Upstox's documented 2,000 requests per 30 minutes standard-API ceiling. Use `--resume` after interruption. After the 100-company probe is audited, use `--all --resume` to scale.

## Output

The runner writes:

- `raw/income-statement/*.json`
- `raw/balance-sheet/*.json`
- `provenance.json`
- `normalized/income_facts.csv`
- `normalized/balance_facts.csv`
- `normalized/profit_pairs.csv`
- `summary.json`

No output from this runner is accepted Research V2 evidence by itself.

## Upstox documentation used

- Analytics Token: https://upstox.com/developer/api-documentation/analytics-token/
- Income Statement: https://upstox.com/developer/api-documentation/get-income-statement/
- Balance Sheet: https://upstox.com/developer/api-documentation/get-balance-sheet/
- Key Ratios: https://upstox.com/developer/api-documentation/get-key-ratios/
- Rate Limits: https://upstox.com/developer/api-documentation/rate-limiting/
