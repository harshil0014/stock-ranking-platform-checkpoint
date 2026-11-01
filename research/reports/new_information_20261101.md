# Execution repair and new-information pilots — 1 November 2026

The execution proxy is corrected and tested. The first delivery-information head
failed its development gate; its exposed performance remains unopened. The filing
pilot is **inconclusive and operationally dropped**. No weights, champion, preference lens,
prospective ledger, trading account, or production ranking was changed.

## Actual next-open execution

The previous proxy could buy at the same close used for the decision. This is
unattainable timing for an after-close signal. It does not mathematically inflate
every return: an overnight fall can improve a later entry. Here the mean correction
is negative for every reported group. Raw legacy tables remain preserved.

The new proxy uses actual cached provider Open × (Adj Close / Close), not shifted
closing prices. Every scheduled contribution stays as idle cash and buys at the
first observed opening strictly after its scheduled date. This deliberately applies
to later monthly contributions too. Costs are 25 bp per buy and terminal sale.
Fractional shares, fixed selection/weights, 12-month cohorts, original base 7500
schedule. End-of-horizon liquidation uses the last observed adjusted close on or
before the known endpoint with a maximum 7-day mark gap. First fills are all later
than the decision. Missing opens, paths or unresolved actions block entire portfolios.

| period | model | policy | valid_dates | legacy mean XIRR % | next-open mean XIRR % | change pp |
| --- | --- | --- | --- | --- | --- | --- |
| development | active_champion | global_top20 | 16 | 40.398 | 40.149 | -0.249 |
| development | active_champion | sector_top3_equal_sector | 10 | 38.942 | 38.518 | -0.425 |
| development | factor20_fixed | global_top20 | 15 | 38.023 | 37.646 | -0.377 |
| development | factor20_fixed | sector_top3_equal_sector | 10 | 34.878 | 34.463 | -0.415 |
| exposed | active_champion | global_top20 | 12 | 0.739 | 0.602 | -0.137 |
| exposed | active_champion | sector_top3_equal_sector | 7 | 2.046 | 1.784 | -0.262 |
| exposed | factor20_fixed | global_top20 | 7 | 9.399 | 9.145 | -0.254 |
| exposed | factor20_fixed | sector_top3_equal_sector | 5 | 2.686 | 2.387 | -0.298 |


These are means of overlapping cohort XIRRs, not a chainable strategy CAGR.
Each row compares old and new execution on the same valid observations. Cross-model
comparisons require matched dates:

| period | policy | matched_dates | lens_minus_champion_xirr | lens_minus_champion_drawdown |
| --- | --- | --- | --- | --- |
| development | global_top20 | 15 | -2.314 | -1.075 |
| development | sector_top3_equal_sector | 9 | -2.827 | -0.632 |
| exposed | global_top20 | 7 | 8.963 | -1.429 |
| exposed | sector_top3_equal_sector | 5 | 0.656 | -2.404 |


The last two columns above are lens minus champion in percentage points; negative
drawdown means worse loss. Development Top 20 remains worse for the lens by 2.314 pp
on 15 matched dates. Exposed comparisons have only 7 Top 20 or 5 sector observations and
were already exposed diagnostics, not a new holdout or a reason to promote a model.
There were 82 valid and 30 blocked of 112 planned portfolio observations. Failure reasons:
`{'Unresolved corporate action': 30}`. Missingness can bias the remaining sample.

## Cheap new-information long shot: lagged delivery percentage

Downloaded official NSE full delivery reports and same-session bhavcopy ISINs
serially. Full report endpoints were unavailable for 15 pre 2020 sample dates, so those
remain unknown. Coverage passed on 29 dates including December 2019 and 28 dates
in 2020–25 (16 development, 12 exposed),
with at least 500 complete EQ stocks/date. These are dated snapshots, not a continuous
daily microstructure panel and not a survivorship-free universe. BSE stocks,
surveillance stages, circuit execution, pledge changes and bulk/block histories were
not synthesized from ordinary price/volume data.

One fixed annual expanding Ridge(alpha=10) price/volume control versus the same
head plus delivery percentage and delivery×recent momentum. The source session
must precede the decision date. Each annual fit uses only labels matured before
January 1;December 2019 and 2020 provide training, 2021–23 provides 12 development evaluation dates.
Six initial fits, plus six identical review reconstructions that reproduced the
stored full-support IC exactly; no hyperparameter grid. The target is next-open to 21st-session close net
of 25 bp per side, a different short-horizon objective from the champion's SIP goal.
Raw return/volatility features are the existing price head; official lagged quantity
and turnover are included in both models. All inputs are same-date global
percentiles. Protocols were hashed before fitting.

- Matched control mean IC: **0.067808**.
- Delivery-augmented mean IC: **0.065655**.
- Increment: **-0.002153**, versus required **>0.010135**.
- Decision: **kill this fixed candidate**; exposed performance unopened.

Champion guard support is narrower than the full delivery cohort. On their
intersection, all three scores use exactly the same 12 date, stock and changed-target
rows: champion mean IC **-0.029666**,
control **0.067435**, delivery
**0.065227**. Date-level counts are in the
diagnostic CSV. This is separate from the original full-support kill gate and does
not redefine the champion's original objective or validate a competing product.
One failed two-feature head does not reject every Indian microstructure signal.

## Higher-ceiling long shot: local filing reader

Six real NSE filing documents were downloaded, hashed and read, including two
auditor resignation events, three auditor appointment events and one non-auditor
resignation. One resignation concerns a step-down subsidiary. A resignation is an
event, not evidence of wrongdoing: one document cites fee disagreement and another
auditor consolidation. Neither is automatically a loser label.

The installed llama3.2:3b was pinned by local digest; issuer identifiers were
redacted in bounded excerpts. One CPU compute thread, no GPU allocation, isolated
local service inside the same governed job. No cloud inference or model downloads.
Fixed prompt/seed, temperature 0, exact-substring support required. Results:

- Original strict single-label score: **0/2**.
- Fixed regex correct classifications: **2/2**.
- Outcome: **INCONCLUSIVE — operationally dropped**; 2 of 6 planned cases completed.
- Investment-alpha test: **not run**. Dated pledge data and mature prospective
  loser labels are missing. This is source-reviewed factual extraction, not an
  independent human-labeled governance benchmark or a financial backtest.

The intended 600 secondbudget overran to 4801 seconds of wall time;
the blocking HTTP timeout was not an absolute deadline. Host availability/scheduling
may contribute, but the cause of the wall-clock gap is not established. An absolute
worker watchdog was added afterward and inference was not rerun. Case 1 returned the
correct event but its quote differed only in PDF whitespace, causing strict rejection.
Case 2 contains both resignation and appointment, with no priority rule in the prompt;
its appointment answer is not established as factually wrong. Its firm-name quote
alone is insufficient semantic support. The original 0/2 score is preserved, but is
**not a sound estimate of extraction accuracy**. This pilot failed on operational
cost and evaluation design, not a demonstrated lack of governance signal.

Metadata was first observed in the existing October 31 acquisition; document bodies
were acquired November 1. Exchange publication dates, metadata first observation,
and new document acquisition times are distinct. Nothing was backfilled into a
prospective forecast. Exact prompts, model settings, source receipts and hashed
results are retained; full documents/excerpts and raw LLM answers remain local.

## Disposition of the other suggestions

- Tail radar: not tested in this batch. A 2 x/24 monthtarget needs more mature,
  point-in-time labels and a volatility-matched control; the 12-monthSIP label is
  not a substitute.
- Global simple model: not shipped. A weak sector placebo is not an equivalence
  test of a new model. Keep it a separate preregistered non-inferiority question.
- Fixed regime switch: not tested. Complete point-in-time 2012–19 memberships,
  adjusted daily histories and terminal proceeds are still incomplete; there is
  no valid three-bear-regime panel ready to score.
- Public shadow: existing append-only research records remain intact. No actual
  money was committed. Fresh, complete champion inputs and source-to-fill parity
  still gate the start of an eligible prospective holdout.

## Reproduction and limits

Run the scripts only through `champion_market_low_load_20261031.run`, using
`work/new-information-20261101` for this run's status/logs. One research worker,
one compute thread, CPU cap 12.5%,4 seconds active/2 seconds rest. The isolated LLM
was CPU-only; its service is shut down afterward. No power settings changed.
The PDF reader uses the installed bundled pypdf if absent from the repo venv.
Acquisition and raw price caches remain local; compact receipts are versioned.

Eight focused execution regression tests passed before replay. Artifact integrity
checks are recorded separately:15 checks passed, including exact reproduction of
the development IC. The final local test run passed 17 tests covering execution,
the watchdog, and the existing professor factor module. Local validation does not imply remote CI passed.
The initial PDF logging attempt failed on Windows cp1252; switching this runner's
stdout to UTF-8 fixed it, preserving the failed log. No model/prompt was tuned from
that error. Current-survivor identities, retrospective sectors, provider price
adjustment vintages, missing execution constraints and sparse overlapping dates
remain. The execution correction repairs this new research proxy; old model
training labels and old published benchmark cashflows have not been silently
retrained or overwritten. Original same-close performance claims remain provisional.

Sources: [NSE reports](https://www.nseindia.com/all-reports),
[Ollama generation API](https://docs.ollama.com/api/generate),
[Llama 3.2 model card](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/MODEL_CARD.md).
The model card lists a December 2023 pretraining cutoff; that and redaction reduce
some known-issuer leakage concerns, but do not establish contamination-free data.
