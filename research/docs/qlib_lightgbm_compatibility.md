# Qlib LightGBM compatibility proof

This milestone tests the official
`qlib.contrib.model.gbdt.LGBModel` from Qlib v0.9.7 with LightGBM 4.6.0.
It does not implement or call an alternative boosting model.

## Frozen boundary

The source-controlled specification at
`research/specifications/qlib_lightgbm_frozen_protocol.json` selects `run-01`
from the accepted `final-locked-20260731` Qlib Linear batch. Selection is the
lexicographically first valid completed run. Both accepted runs must have the
same canonical input, dataset, label, split, ordering, and evaluation-protocol
hashes before execution is allowed.

The data remain the 30 fictional instruments, ten features, seed `20260730`,
and 120/30/40 train/validation/test dates already accepted for Qlib Linear.
The Qlib dataset names the validation segment `valid`, as required by
`LGBModel`, while the frozen research protocol continues to call it
validation.

## Fixed configuration

The only permitted attempt uses squared-error loss, learning rate `0.05`, 31
leaves, no depth limit, minimum 20 rows per leaf, full feature and row
fractions, no regularization, one thread, deterministic column-wise execution,
and seed `20260730` for every LightGBM random source. It requests 200 boosting
rounds and validation-only early stopping after 20 rounds. Test labels are not
available to fitting, stopping, feature selection, or configuration.

## Diagnostic: uninitialized workflow

Qlib v0.9.7 `LGBModel.fit` trains through the official LightGBM implementation
and then unconditionally sends every recorded metric to
`qlib.workflow.R.log_metrics`. The original diagnostic deliberately leaves the
workflow uninitialized. The official call therefore raises:

```text
AttributeError: Please run qlib.init() first using qlib
```

The installed `gbdt.py` SHA-256 is
`062874b847ebd6426b5f54a263d5dbce49b18d528ea35dae96b6a31dbf7f3c66`.
The file is inspected and fingerprinted but never patched.

The preserved standalone compatibility runner makes one official
fixed-configuration attempt. It records training and validation history,
diagnostic model state, feature importance, the upstream failure, and
execution provenance, then returns nonzero. It never predicts, evaluates,
retries, relaxes parameters, initializes a provider, or promotes the model
registry status. This proves only that an uninitialized workflow cannot accept
Qlib's post-training metrics.

## Official local-recorder resolution attempt

The reproduction path uses Qlib's own `MLflowExpManager` with an absolute,
hostless local `file:` URI. Qlib initialization succeeded with an empty local
provider directory, no cache, no provider-data query, and no network tracking.
The first `R.start` then failed before `LGBModel.fit` because the installed
MLflow version places filesystem tracking in maintenance mode and requires an
additional process setting:

```text
MLFLOW_ALLOW_FILE_STORE=true
```

That opt-in was not part of the initial execution configuration. The run
therefore stopped without changing the environment, starting training,
predicting, evaluating, or attempting run 2. Evidence is retained in
`research/generated/qlib-lightgbm/official-local-recorder-20260731`.

## Official resolution and outcome

The exact `MLFLOW_ALLOW_FILE_STORE=true` opt-in was subsequently authorized
for fresh LightGBM child processes only. It was never set in the parent,
Windows user/system environment, product environment, or dependency lock.
Both official runs then created local `MLflowRecorder` instances, closed with
`FINISHED`, trained 53 trees through unmodified `LGBModel.fit`, and produced
1,200 test predictions through `LGBModel.predict`.

The batch
`research/generated/qlib-lightgbm/official-local-recorder-opt-in-20260731`
passed the fixed `1e-12` reproducibility gate with zero prediction, gain
importance, and split importance differences. This is synthetic-only
reproduction evidence, not real-market validation, an upstream benchmark,
portfolio performance, or investment evidence.

Qlib Linear's slightly higher metrics are consistent with the deliberately
linear synthetic data-generating process. They are not evidence that Linear
universally outperforms LightGBM.

## Commands

Dry-run validates every frozen and environment fingerprint without writing:

```powershell
stock-research reproduce-qlib-lightgbm --dry-run
```

The official local-recorder command plans two runs:

```powershell
stock-research reproduce-qlib-lightgbm --batch-id <unique-id>
```

## Evidence boundary and next decision

Neither blocked diagnostic is itself a reproduction. The separate successful
two-run batch supports the `synthetic_reproduced` status only within its frozen
offline fictional dataset and protocol.
