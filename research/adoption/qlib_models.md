# Qlib adoption specifications

These are implementation specifications, not reproduction claims. All Qlib work
is isolated from the Python 3.13 product environment and pinned to Qlib v0.9.7
at commit `da920b7`.

1. Research V2 is exported as the stable, explicitly non-ML
   `research_v2_baseline`.
2. Qlib Linear is the first reproduction target. Use the official class and
   record its parameters, seeds, features, package lock, datasets, and model
   configuration fingerprint.
3. Qlib LightGBM follows under the same evaluation protocol. Its distinct
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
