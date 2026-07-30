# Open-source quant research policy

Upstream code adoption requires a pinned official source, paper citation where
applicable, code-licence review, dependency/security review, and a reproducible
environment record. Repository-code licences never imply permission to use or
redistribute datasets.

Upstream behavior must be reproduced before modification. Benchmark numbers
remain upstream claims until the project reproduces them under a recorded
protocol. Failed and abandoned runs are retained with reasons. A proposed
modification requires an upstream baseline, a one-change-at-a-time ablation,
coverage reporting, leakage checks, and predefined rejection criteria.

Reject adoption when provenance is incomplete, data rights are unclear,
point-in-time availability cannot be established, dependencies cannot be
isolated, results are not reproducible, or benefits disappear under fair
coverage and protocol controls. Acceptable future novelty may include
India-specific point-in-time features, explainability, robustness, or model
combination only after upstream reproduction and ablation.

This repository intentionally has no project licence. Owner licence selection
is a blocker to public distribution. Upstream MIT notices do not resolve the
project’s own licensing decision.
