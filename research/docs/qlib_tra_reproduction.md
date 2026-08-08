# Qlib TRA frozen synthetic reproduction

This milestone uses the unmodified Qlib 0.9.7
`qlib.contrib.model.pytorch_tra.TRAModel` and
`qlib.contrib.data.dataset.MTSDatasetH`. It is an offline frozen-synthetic
reproduction contract, not an Alpha360 or paper-result reproduction, Indian
market validation, portfolio result, profitability claim, or investment
evidence.

## Environment and provenance

TRA runs in `.venv-tra`, a separate Python 3.12.10 environment. The accepted
Qlib dependency lock was installed from PyPI first. The Windows CPython 3.12
CPU wheel `torch-2.4.1+cpu-cp312-cp312-win_amd64.whl` was then downloaded from
the official PyTorch CPU index, verified at SHA-256
`3a570e5c553415cdbddfe679207327b3a3806b21c6adea14fba77684d1619e97`,
and installed without dependency resolution. TorchVision and TorchAudio are
not installed. The wheel's declared Windows runtime dependencies (`fsspec`,
`networkx`, `sympy`, and SymPy's `mpmath`) are pinned in the resolved lock and
were installed from PyPI. An initial pre-fit diagnostic that omitted these
dependencies is retained under generated evidence; it performed no training
or prediction.

The pinned Qlib files are recorded in the environment report and must retain
their source hashes. Product Python never imports Qlib, Torch, or LightGBM.

## Dataset contract and leakage audit

The model input width is 10. The dataset `input_size` is deliberately `None`;
these settings serve different roles. In Qlib 0.9.7, a non-null dataset
`input_size` activates the legacy flattened Alpha360 reshape. `None` makes the
official dataset construct 60-by-10 backward-looking sequences.

The exact dataset configuration is sequence length 60, horizon 1, three
states, sample memory, batch size 1024, shuffle enabled, and incomplete
training batches dropped. Upstream evaluation mode changes to daily sampling,
disables shuffling, and retains incomplete batches. Early training sequences
use official left padding because the frozen panel begins on the first
training date.

Validation occurs in two stages. A standard-library pre-import audit derives
the expected boundaries from copied bytes. After the verified Qlib import,
the runner inspects actual official batches and requires feature shapes
`[batch, 60, 10]`, memory shapes `[batch, 59, 3]`, matching endpoints,
instrument identity, padding, and timestamps. Any disagreement stops before
fit.

`MTSDatasetH` segment views share loss memory. With horizon 1, a sample's
current loss cannot enter its own routing state, while causally earlier
realized losses may be historical context.

## Fixed model and upstream behavior

The frozen model is Qlib's two-layer LSTM RNN backbone with attention, hidden
width 64, three routed predictors, an LSTM router of width 32, pretraining,
router transport, validation IC checkpoint selection, and seed 20260730.
There is no tuning or fallback.

Pretraining and routed training append to one upstream `evals_result`. The
runner preserves the phase boundary using official log markers and phase
lengths, records each phase's `best score ... @ epoch`, and treats only the
routed phase as the final selected checkpoint.

With `eval_test=False`, Qlib skips per-epoch test evaluation. Its unmodified
`fit` still performs final train, validation, and test inference after
checkpoint selection, so test labels are accessed in that post-selection
diagnostic. They do not affect gradients, early stopping, checkpoint choice,
or configuration. Project comparisons use the separate frozen evaluator.

`logdir=None` prevents Qlib's optional model and pickle outputs. The project
stores only CSV, JSON, tensor-byte hash manifests, and plain-text logs.

## Reproducibility and scientific limits

Run 2 begins only after run 1 has 1,200 unique finite predictions, exactly
three state-score columns, multiple nonconstant dates, valid IC and Rank IC
dates, finite tensors, and a passed sequence audit. Two independent CPU
processes must agree within `1e-12` for routed and per-state predictions and
exactly for phase, tensor, sequence, environment, model, and protocol
fingerprints.

The accepted batch `official-frozen-tra-20260731` contains two independent
successful processes. Routed scores and `score_0`, `score_1`, and `score_2`
had zero maximum difference. Both runs retained 1,200 predictions across 40
nonconstant test dates, and the separate evaluator produced 40 valid IC and
40 valid Rank IC observations. The comparison preserves one protocol
fingerprint and four distinct model-configuration fingerprints; it makes no
winner or investment claim. DoubleEnsemble appears only as a status-only
compatibility blocker.

The frozen generator is largely linear and need not favor a temporal-routing
neural architecture. TRA is not required to outperform Linear or LightGBM.
DoubleEnsemble remains a status-only constant-signal compatibility blocker.

The next milestone is a real Indian-market point-in-time data and walk-forward
validation foundation.
