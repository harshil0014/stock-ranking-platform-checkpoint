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
3. Qlib LightGBM is the exact next reproduction under the frozen synthetic
   dataset and protocol, without test-driven tuning. Its distinct
   parameters and model fingerprint are expected and must be preserved.
4. DoubleEnsemble follows only after both simpler models reproduce cleanly.
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
