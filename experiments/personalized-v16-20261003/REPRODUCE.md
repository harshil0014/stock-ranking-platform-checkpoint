# Reproduce V16

Frozen research experiment: do not rerun into the completed output root. Use a separate checkout/output root. Python3.13 with pandas, numpy, lightgbm, scipy and sklearn from the recorded environment. No remote service calls are required.

Stages (in order, from repository root):

```powershell
python research/runners/personalized_v16_20261003.py autopsy
python research/runners/personalized_v16_20261003.py inspect
python research/runners/personalized_v16_20261003.py hypothesis
python research/runners/personalized_v16_20261003.py development
python research/runners/personalized_v16_20261003.py current
python research/runners/personalized_v16_20261003.py exposed
python research/runners/personalized_v16_20261003.py supplemental
python research/runners/personalized_v16_20261003.py report
python research/runners/personalized_v16_20261003.py audit
```

Autopsy reconstructs frozen V15 development scores and checks all metric deltas (<1e-10). Attribution uses exactly the same labeled eligibility as ranking_metrics. Inspect adds development-only selection behavior and feature-state attribution. Hypothesis writes the immutable three-candidate grid and unchanged V15 gates before candidates. Development locks selection before current/exposed access. Current reuses the immutable audited V15 replay from the exact V7 file; restores original float32 feature/confidence types and verifies V15 score reproduction. Exposed reuses frozen maturity-purged V15 evaluation model; never refits or tunes. Supplemental is post-lock mechanism/robustness diagnostics only. Audit checks protected hashes and creates manifest.

Inputs: frozen V15 runner/models/protocol and current V7 replay; V12 prepared panel, raw historical panel, V14 dated historical growth and maturity-purged champion benchmark scores. No edits to these inputs. Model dependencies and exact hashes are recorded in input_inventory.json and protected_before.json; V15 remains a required read-only dependency. Median attribution is paired and uses512 seeded permutation orders, seed20261003. Year bootstrap uses2000 four-year block resamples with the same seed.

Historical fundamentals/industries unavailable; no current backfill. All horizons12 months; lookback12/36/60 differ. Known2024–2025 is exposed supporting evidence only. Production remains d499580, no deployment.
