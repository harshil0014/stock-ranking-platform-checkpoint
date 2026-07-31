# Research layer

This directory contains source-controlled contracts, provenance, environment
specifications, adoption controls, and fictional examples. Generated reports,
manifests, model files, caches, cloned repositories, and datasets are ignored.

The `stock-research` executable runs in the main Python 3.13 environment and
does not import Qlib. Qlib is confined to `.venv-qlib`, created only by
`environment/setup.ps1` when Python 3.12 is available.

Quick validation:

```powershell
stock-research registry-validate
stock-research contract-validate --kind features --input research\examples\features.csv
stock-research contract-validate --kind labels --input research\examples\labels.csv
stock-research contract-validate --kind split --input research\examples\split.json
stock-research environment-inspect
stock-research reproduce-qlib-linear --dry-run
stock-research reproduce-qlib-lightgbm --dry-run
```

See `docs/evaluation_methodology.md`, `docs/open_source_policy.md`, and
`adoption/qlib_models.md` before adding an experiment.

The pinned Qlib v0.9.7 Python 3.12 environment and official LinearModel have
now passed the offline synthetic reproduction. See
[`docs/qlib_linear_reproduction.md`](docs/qlib_linear_reproduction.md) for the
frozen data, execution, artifact, and evidence boundaries. This result is
synthetic-only and is not real-market validation or investment evidence.

The official Qlib LightGBM wrapper has a preserved uninitialized-workflow
diagnostic and a separate local-recorder attempt. Qlib initialization passed,
but installed MLflow required an unapproved filesystem-store environment
opt-in before `R.start` could create the recorder. The opt-in was later
authorized for LightGBM child processes only, and two fresh official runs
completed reproducibly on the frozen fictional protocol. See
[`docs/qlib_lightgbm_compatibility.md`](docs/qlib_lightgbm_compatibility.md).
The successful result is synthetic-only; neither earlier blocked diagnostic is
a reproduction claim.

The DoubleEnsemble milestone is specified in
[`docs/qlib_doubleensemble_reproduction.md`](docs/qlib_doubleensemble_reproduction.md).
Its product orchestration remains Qlib-free; the official Qlib class runs only
in `.venv-qlib` against copied, hash-verified frozen inputs. The first fixed
attempt produced only constant signals and stopped before the second run; it
is compatibility evidence, not a reproduced model result.
