# Qlib DoubleEnsemble frozen synthetic reproduction

This milestone uses the official Qlib 0.9.7
`qlib.contrib.model.double_ensemble.DEnsembleModel`. The method comes from
*DoubleEnsemble: A New Ensemble Method Based on Sample Reweighting and Feature
Selection for Financial Data Analysis* (IEEE ICDM 2020,
DOI `10.1109/ICDM50108.2020.00087`). Qlib repository code is MIT licensed;
that does not grant rights to unrelated datasets.

The runner uses the accepted fictional dataset, label fingerprint
`7412fc79…`, and evaluation protocol `210bca5c…`. It trains three official GBM
submodels with sample reweighting and feature selection enabled. Validation is
provided only as Qlib's internal LightGBM validation set. With early stopping
disabled, it does not choose epochs or configuration. Prediction is restricted
to the frozen test segment.

The configuration follows the pinned Qlib benchmark shape but fixes one
thread, Python and LightGBM seeds, deterministic LightGBM mode, and NumPy's
global seed. Consequently this is not an Alpha158 benchmark reproduction.
Product code imports no Qlib, LightGBM, or Torch; fitting occurs only in fresh
`.venv-qlib` subprocesses through `DEnsembleModel.fit`, and prediction only
through `DEnsembleModel.predict`.

The official object exposes fitted Boosters and selected feature indexes,
which are audited without modification. It does not preserve every
sample-weight vector or complete intermediate loss curve as public state; the
project does not patch the class to manufacture that observability.

Run a write-free validation:

```powershell
.\.venv\Scripts\stock-research.exe reproduce-qlib-doubleensemble `
  --batch-id official-frozen-reproduction-20260731 --dry-run
```

Remove `--dry-run` to perform the two frozen runs. Generated artifacts remain
under the ignored `research/generated/qlib-doubleensemble/` hierarchy. A
failure is retained without fallback, tuning, changed seeds, or retries with
alternate parameters.

The first official frozen attempt completed fitting and prediction without an
implementation exception, but its three submodels each contained one
zero-split tree. The resulting test signal was constant on all 40 dates, so
correlation evaluation was undefined: no valid IC or Rank IC could be
calculated. This is an execution success but a scientific reproduction
failure.

The degeneration is consistent with a scale or configuration mismatch between
the Alpha158-oriented benchmark parameters and this smaller synthetic dataset
and label scale. That explanation is an inference. The artifacts establish
zero-split trees and constant predictions, but do not conclusively identify
any individual parameter as the cause. In particular, they do not establish
that either regularization parameter alone caused the result.

The batch stopped before run 2 and is retained as honest compatibility
evidence. No test-driven tuning, workaround, or alternate configuration was
attempted. DoubleEnsemble remains `adoption_specified`; this is not an
algorithm failure, successful synthetic reproduction, Alpha158 reproduction,
real-market validation, investment evidence, or universal conclusion about
DoubleEnsemble.

The four-model comparison reports IC, Rank IC, both ICIR conventions, and
coverage under one protocol. It declares no winner and contains no portfolio,
profitability, real-market, or investment claim. The synthetic generator is
largely linear, so a more complex ensemble need not outperform Qlib Linear.

All evidence is offline and synthetic only. It is not Indian-market
validation, investment evidence, or advice. The next milestone is a TRA
environment, security, and resource feasibility review with isolated PyTorch
planning; TRA reproduction is not part of this work.
