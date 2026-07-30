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
```

See `docs/evaluation_methodology.md`, `docs/open_source_policy.md`, and
`adoption/qlib_models.md` before adding an experiment.
