# Provenance status

The machine-readable registry pins Microsoft Qlib v0.9.7 to tag `v0.9.7` and
commit `da920b7`. Official package metadata declares Python 3.12 support and
lists LightGBM as a dependency. Qlib repository code is MIT licensed; every
dataset requires its own rights review.

Registry status means only:

- `provenance_verified`: the named source/release/licence metadata was checked.
- `adoption_specified`: a local adoption sequence and controls are documented.

No Qlib model, Alpha handler, paper result, or benchmark is marked reproduced.
The candidate LightGBM, NumPy, and pandas constraints are specifications to
test. Compatibility becomes verified only after a clean Python 3.12
installation, captured `pip freeze`, and successful import smoke checks.
