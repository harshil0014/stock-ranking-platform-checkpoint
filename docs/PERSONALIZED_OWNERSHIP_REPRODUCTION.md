# Reproducing the ownership research

Run from the repository root on `personalized-investing-20260922`. The accepted production snapshots must remain unchanged. The research cutoff is 2026-09-18.

## Preserved inputs

The local `external_research_pack/`, `data/live_market/`, `data/company_facts/`, and provider history caches are required. Raw evidence and large prediction panels are deliberately excluded from Git. This is a local reproducible research checkpoint, not a self-contained public dataset. Source and overlay hashes are recorded in `research/data/ownership-recovery-20260925/history_recovery_audit.csv`; frozen output manifests record artifact hashes. Verify the original evidence before regenerating any overlays:

```powershell
.venv-qlib\Scripts\python.exe research\runners\verify_ownership_inputs.py --validate-only
```

`prepare_ownership_recovery.py` normalizes the documented resulting-security terms. `recover_ownership_history.py` regenerates overlays from the preserved local sources. Neither changes an accepted production cache. Do not regenerate these inputs merely to suppress a hash mismatch; investigate source drift first.

## Frozen datasets

The accepted research output is `experiments/personalized-official-action-freeze/build-06`. Its independent rebuild is `build-06-rebuild-check`. Use a new output directory when reproducing:

```powershell
.venv-qlib\Scripts\python.exe research\runners\run_personalized_official_action_freeze.py `
  --output experiments/personalized-official-action-freeze/reproduction `
  --evidence-pack external_research_pack `
  --frozen-root experiments/personalized-data-freeze/build-01 `
  --previous-tournament experiments/personalized-final-tournament/build-02 `
  --previous-freeze experiments/personalized-official-action-freeze/build-04 `
  --residual-pack external_research_pack/residual_recovery_20260925 `
  --history-cache data/live_market/history_cache `
  --split-root external_research_pack/corporate_actions/yahoo_secondary
```

Run the same command with output `reproduction-rebuild-check`. Compare the deterministic manifest fingerprints; timing in `summary.json` is observational.

## Tournament and finalization

The completed tournament lives in `experiments/personalized-final-tournament/build-04`. Its checkpoints are in `checkpoints-03`; each panel carries a context hash, and mismatched contexts are rejected. A clean reproduction should use fresh output and checkpoint directories:

```powershell
$workbookPath = 'C:\Users\Harshil\Downloads\_Organized\Documents\Copy of OK Strategy - Master Sheet v4.3 (1).xlsx'
.venv-qlib\Scripts\python.exe research\runners\run_personalized_official_action_tournament.py `
  --output experiments/personalized-final-tournament/reproduction `
  --official-freeze experiments/personalized-official-action-freeze/reproduction `
  --frozen-root experiments/personalized-data-freeze/build-01 `
  --history-cache data/live_market/history_cache `
  --split-root external_research_pack/corporate_actions/yahoo_secondary `
  --workbook $workbookPath `
  --previous-tournament experiments/personalized-final-tournament/build-02 `
  --checkpoint-root experiments/personalized-final-tournament/reproduction-checkpoints `
  --protocol research/protocols/personalized_ownership_tournament_v2.json `
  --protocol-sha256 de55e44ab11e2e95778d90cdaae8a0bde950ad896995f710df5de586d401ea96

.venv-qlib\Scripts\python.exe research\runners\finalize_ownership_research.py `
  --tournament experiments/personalized-final-tournament/reproduction `
  --freeze experiments/personalized-official-action-freeze/reproduction `
  --workbook $workbookPath

.venv-qlib\Scripts\python.exe research\runners\audit_ownership_result.py `
  --tournament experiments/personalized-final-tournament/reproduction
```

The finalizer requires the independent freeze rebuild, checks protected input hashes and strict training-label maturity, evaluates the fixed and training-only learned ensembles, then compares the selected individual with the workbook. Finalization updates the research report; preserve prior committed reports before running a new investigation. The saved rights sensitivity is descriptive and hypothetical, and is not used for model selection.

## Verification and interpretation

```powershell
$env:PYTHONPATH = 'src;.'
.venv-test\Scripts\python.exe -m pytest -q --basetemp .pytest-tmp-ownership-reproduction -p no:cacheprovider
```

Read `ownership_audit.json`, `verification_summary.json`, `final_assessment.json`, `paired_date_uncertainty.csv`, and `professor_comparison_summary.json` in the tournament directory. The selected goal model minimizes mean top-20 goal shortfall across six historical dates and nine profiles. The same common cohort is used for model comparisons; executable coverage is a separate, broader measure. These are retrospective research results, with current-universe survivorship and gross price-only execution. No production deployment is authorized by this checkpoint.
