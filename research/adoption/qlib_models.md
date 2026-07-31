# Qlib adoption specifications

All Qlib work is isolated from the Python 3.13 product environment and pinned
to Qlib v0.9.7 at commit `da920b7`. The official Qlib Linear implementation has
now been reproduced twice on the frozen offline fictional dataset. The two
runs had identical coefficients and predictions at the fixed `1e-12`
tolerance. This synthetic-only result is not real-market validation,
investment evidence, or an upstream benchmark reproduction.

1. Research V2 is exported as the stable, explicitly non-ML
   `research_v2_baseline`.
2. Qlib Linear uses the official class with recorded parameters, seeds,
   features, package lock, datasets, and model configuration fingerprint. Its
   stable reproduced signal ID is `qlib_linear_ols_v0_9_7`.
3. Qlib LightGBM has two preserved diagnostics. An uninitialized workflow
   trains and then fails at `R.log_metrics`. The subsequently authorized
   official local `MLflowExpManager` path initializes Qlib but the installed
   MLflow rejects filesystem tracking unless
   `MLFLOW_ALLOW_FILE_STORE=true` is explicitly set. After that setting was
   authorized for LightGBM child processes only, two fresh official runs
   completed with zero prediction and feature-importance differences at
   `1e-12`. Its `synthetic_reproduced` status is limited to this frozen
   fictional protocol and is not real-market or investment evidence.
4. DoubleEnsemble follows only after both simpler models reproduce cleanly.
   Its frozen reproduction uses the official Qlib 0.9.7 `DEnsembleModel`,
   three GBM submodels, and the accepted synthetic protocol. Promotion remains
   conditional on two-run reproducibility and the complete acceptance suite.
   The first fixed attempt trained successfully but produced three one-tree,
   zero-split submodels and a constant test signal. It stopped before run 2,
   so the model remains `adoption_specified`.
5. TRA follows after a separate PyTorch environment and security/resource
   review; PyTorch is not part of the initial Qlib environment.
6. No hybrid is proposed as a result until all adopted components have
   reproduced results and required ablations.

Alpha158 and Alpha360 are candidate upstream handlers. Before use, every
feature must pass the point-in-time availability contract and the underlying
market data must have documented redistribution and research rights.

The shared comparison boundary is the `evaluation_protocol_fingerprint`, not a
model configuration fingerprint. Coverage differences are retained in every
comparison.
