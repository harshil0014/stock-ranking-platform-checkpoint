# Offline Qlib Linear reproduction

The `reproduce-qlib-linear` workflow executes the official
`qlib.contrib.model.linear.LinearModel` from `pyqlib==0.9.7` in the isolated
Python 3.12 environment. Product orchestration and evaluation stay in the
Python 3.13 `.venv` and never import Qlib.

The fictional generator uses seed `20260730`, 30 instruments, ten finite
point-in-time features, and 200 observation dates. Labels are exact
next-business-day simple returns. Price-derived features are reconstructed in
tests from history truncated through each observation date. The train,
validation, and test periods contain 120, 30, and 40 dates. A seven-calendar-day
purge applies only between train and validation; a seven-calendar-day embargo
applies only between validation and test.

The standalone runner uses:

```text
LinearModel(
  estimator="ols",
  alpha=0.0,
  fit_intercept=False,
  include_valid=False
)
```

It fits only the train segment and predicts only the test segment. The actual
upstream estimator intercept is exported and checked against `1e-12`; if the
object does not expose an intercept, the artifact records null and
`not_applicable`. It is never fabricated.

Every subprocess receives `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`,
`MKL_NUM_THREADS=1`, and `NUMEXPR_NUM_THREADS=1`. CSVs use stable ordering,
UTF-8, Unix newlines, ISO dates, and `%.17g` floating-point serialization.
Two independent runs must differ by no more than `1e-12` in coefficients and
predictions. The tolerance is fixed and failures remain failures.

Dry-run:

```powershell
.\.venv\Scripts\stock-research.exe reproduce-qlib-linear --dry-run
```

Full two-run reproduction:

```powershell
.\.venv\Scripts\stock-research.exe reproduce-qlib-linear
```

Generated batches are ignored beneath `research/generated/qlib-linear/`.
Runtime may write a proposed registry-status report there, but it never edits
the tracked registry, adoption documents, or planned manifest.

The accepted local batch produced 1,200 Qlib signals and 1,160 genuine Research
V2 signals. Forty explicit Research V2 diagnostics record SYN030's negative
leverage. Both models share one daily evaluation-protocol fingerprint while
retaining different model-configuration fingerprints and visible coverage
differences.

This is offline synthetic-only reproduction. It is not real-market validation,
investment evidence, portfolio performance, or reproduction of an upstream
benchmark. The next milestone is the official Qlib LightGBM implementation on
this frozen synthetic dataset and protocol, without tuning against test
results.
