# Immutable personalized challenger and prospective shadow evaluation

## Registration

- Challenger source: `d4995807163bef1ec4b297179e6c54a59c71f390`.
- Frozen formula: **67% Goal percentile + 33% LightGBM LambdaRank percentile**, within each investor profile.
- Original prediction date: **2026-09-18**. Registration/prospective start: **2026-09-26**. The intervening days are not claimed as prospective evidence.
- Checkpoints: **2026-12-26**, **2027-03-26**, **2027-09-26**. Run on the following calendar day or later, using observations dated no later than the checkpoint.
- Immutable release/tag: `personalized-challenger-d499580-20260926`, pointing to the original challenger commit. The shadow system is a separate subsequent research commit; it does not replace the original model.
- Registration: `research/freezes/personalized-d499580/`. Do not edit it. Model or policy changes require a separately named future challenger, never an amendment to this one.

All 30,467 original profile-ranking rows and their features are preserved, including baseline scores, execution diagnostics, shares and cash. The top 20 for each of nine profiles and six strategies are fixed with ISIN as the deterministic tie breaker. The five baselines are Goal, standalone LambdaRank, existing/global score, professor whole-share and carry-XIRR. Each strategy's original eligibility count is reported; differences are not hidden.

The exact LambdaRank model was reconstructed from the original checkpoint rows with unchanged parameters and serialized as text. Reconstruction reproduced every saved prediction to within `1e-12`; serialization reproduces inference exactly. Future checkpoint runs cannot train, rerank, substitute selections or rebalance.

The original study was retrospective, with survivorship and historical publication-timing limitations. Audits verify that training outcomes matured before 18 September, original current predictions contain no future outcomes, and terminal observations are through the cutoff. They do **not** claim that all retrospectively collected source documents were publicly available on that historical date. Starting the prospective clock at registration avoids that claim.

## Commands

Use the existing `.venv-qlib` environment, or Python 3.12 with `research/environment/requirements-shadow.txt`. Runners add `src` to their import path; installing the production application is unnecessary.

```powershell
.venv-qlib\Scripts\python.exe research\runners\personalized_shadow.py verify
.venv-qlib\Scripts\python.exe research\runners\personalized_shadow.py reproduce
.venv-qlib\Scripts\python.exe research\runners\personalized_shadow.py schedule

# Create an empty evidence template now or before each checkpoint.
.venv-qlib\Scripts\python.exe research\runners\personalized_shadow.py init-evidence --evidence research/shadow_evidence/3m-v1

# On or after 27 December 2026, after populating and checking the evidence:
.venv-qlib\Scripts\python.exe research\runners\personalized_shadow.py evaluate --months 3 --evidence research/shadow_evidence/3m-v1 --output research/shadow_runs/3m-v1
```

Use `--months 6` or `--months 12` and separately named evidence/output directories for the later dates. These are expanding evaluations from 26 September, not three independently restarted portfolios. Same inputs reproduce byte-identical checkpoint manifests. Repeating the same run is a no-op; changed inputs require a new explicit revision directory. The evaluator rejects early runs and observations after the checkpoint.

## Evidence contract

The template includes three normalized CSV files and a `sources/` directory. Preserve actual exchange/company/provider source files in `sources/`; each CSV row supplies its source URL and the SHA-256 of a preserved raw file. A hash-shaped string without its source file is rejected.

| File | Required content |
| --- | --- |
| `prices.csv` | ISIN, trading date, **observed nominal close**, source URL/hash. No adjusted-close substitutions, synthetic prelisting prices or price interpolation. |
| `actions.csv` | Unique event ID, parent ISIN, ex-date/type, exact ratio where applicable, separate child ISIN, observed cash/settlement terms and source URL/hash. The numerator is the **total post-action shares per denominator old shares** for splits, bonuses and consolidations; it is the child entitlement ratio for demergers/exchanges. |
| `coverage.csv` | Each selected/resulting ISIN, through-date, `OBSERVED_NOMINAL_CLOSE`, and an explicitly verified `COMPLETE` action inventory with source URL/hash. The template starts `PENDING`; never change it merely to make a run pass. |

Supported events: `SPLIT`, `BONUS`, `CONSOLIDATION`, `DEMERGER`, `STOCK_EXCHANGE`, `RIGHTS_LAPSE`, `CASH_DIVIDEND`, `CASH_EXIT`, and explicit `UNRESOLVED`. Use positive integer numerator/denominator. Fractional proceeds require **cash per fractional share** and the actual payment date. Unknown terms remain blocked. Multiple resulting companies may have separate demerger rows; ambiguous ordering of other same-day actions is rejected rather than guessed. Include new child histories and action coverage when resulting securities arise.

Evidence collection is deliberately distinct from deterministic evaluation: the runner does not assume an incomplete provider action feed is exhaustive. Later discoveries can be incorporated only in a separately sealed evidence revision, preserving the original result.

## Execution and outcome interpretation

- Each selected security is an **independent SIP using the full profile contribution**, matching the original tournament. This is not a shared-budget 20-stock portfolio. The metric is the mean outcome across those independent selections.
- Start with zero holdings/cash at registration. Contribute on the profile's fixed calendar-day interval; buy whole shares at the next observed close within seven days, carrying residual cash. A contribution not yet filled by the checkpoint stays in cash; an overdue missing execution price blocks the result.
- Apply ex-date events before close purchases. Hold resulting shares separately. After mandatory conversion/exit of the selected parent, retain future contributions in cash; do not choose a replacement.
- Rights lapse with no subscription or sale. Fractional and mandatory cash receipts enter cash only on the evidenced payment date. Unknown or unpaid mandatory settlements block primary wealth.
- Track received dividends and pending receivables separately. Dividends are not reinvested and remain excluded from the frozen primary price-only measure. A supplemental wealth field includes received dividends.
- Gross quoted-close fills, zero fees/slippage and the original share-credit timing assumptions remain explicit. This is a shadow simulation, not a claim of actual broker fills.
- Missing prices, corporate-action coverage or economic terms remain visible as blocked selections. A top-selection aggregate and baseline comparison are withheld if any selected result is incomplete. No survivor-only aggregate is presented as the policy result.

Each output directory includes the complete copied evidence, immutable input hashes, contribution/execution/action/cash journal, final holdings and pending receivables, per-security results, per-profile strategy metrics, paired baseline comparisons and an output manifest. Back up the **whole sealed checkpoint directory**, including its evidence, at each checkpoint.

## Backup and restoration

The private GitHub repository stores research commits and the immutable challenger release. The release contains a Git bundle of the code/history and checksummed ZIP parts containing original training checkpoints, feature/ranking panels, accepted fact/market snapshots, price histories and overlays, normalized terms and core supporting evidence. Unused exploratory PDF collections are excluded; they are not inputs to the frozen inference.

The release is published only after GitHub reports matching SHA-256 digests for every uploaded asset. `research/backups/personalized-d499580/github_receipt.json` records the immutable release and remote asset digests. GitHub immutable releases also prevent the associated tag from moving while the release exists: [GitHub documentation](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).

To restore: verify downloaded archive digests against the receipt and `input-backup-manifest.json`, clone the Git bundle (or checkout the recorded shadow-system commit from GitHub), then extract all reproduction ZIPs into the repository root. Verify every extracted file against the input manifest before running `verify` and `reproduce`. Source/config/model hashes must remain unchanged. Do not restore these research snapshots over an active production checkout.

Production branches, accepted-state pointers and deployments are not modified by this workflow.
