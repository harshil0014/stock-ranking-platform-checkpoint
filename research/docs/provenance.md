# Provenance status

The machine-readable registry pins Microsoft Qlib v0.9.7 to tag `v0.9.7` and
commit `da920b7`. Official package metadata declares Python 3.12 support and
lists LightGBM as a dependency. Qlib repository code is MIT licensed; every
dataset requires its own rights review.

Registry status means only:

- `provenance_verified`: the named source/release/licence metadata was checked.
- `adoption_specified`: a local adoption sequence and controls are documented.
- `environment_verified`: the pinned package installed in the isolated Python
  3.12 environment, its resolved lock was captured, and required imports passed.
- `synthetic_reproduced`: the official implementation reproduced deterministically
  on the frozen offline fictional dataset and protocol.

Qlib Linear is `synthetic_reproduced`; this is not real-market validation,
investment evidence, or an upstream benchmark reproduction. Qlib LightGBM,
DoubleEnsemble, TRA, Alpha158, and Alpha360 remain unreproduced. Candidate
constraints for later environments remain specifications until separately
installed and tested.
