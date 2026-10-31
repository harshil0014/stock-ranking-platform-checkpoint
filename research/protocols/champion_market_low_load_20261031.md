# Laptop resource constraint

The user reported excessive laptop heat on31October2026 and requested that research continue under substantially less load. This execution preference applies to all remaining stages of this benchmark.

- One supervised research worker at a time; no concurrent CPU/GPU training queues.
- One compute thread via OMP/OpenBLAS/MKL/NumExpr, PyTorch and estimator settings.
- Windows job-object CPU hard cap12.5%of total machine CPU, idle process priority, inherited by the worker's child processes. GPU workloads run2seconds then pause4seconds; CPU workloads run4seconds then pause2seconds.
- GPU temperature sampled at each cooling pause. Pause at58C and wait until52C before resuming. These are conservative operational triggers, not hardware safety guarantees or CPU temperature measurements.
- The governor only controls processes it creates. It changes no global power plan, clock, fan or GPU setting. Other applications can still generate heat independently.
- Completed annual objectives are retained; saved per-seed forest/network checkpoints are replayed instead of retrained. Seeds, epochs, features, labels and tree budgets remain unchanged. Runtime now includes pacing and is not a speed benchmark.
- `work/champion-vs-market-20261031/low_load_status.json` records the active stage and applied limits. Creating `low_load_control.json` with `{"pause":true}` pauses the active worker at the next cycle; setting it false resumes under the same limits.
- `champion_market_low_load_20261031.py --probe` passed a controlled child-process start/pause/resume/exit test and queried the Windows CPU cap successfully before the real queue was restarted.
- The queue produces local reports and an evidence bundle after checks pass. Result interpretation, plot inspection and public result publication remain a separate review step. No prospective-ledger history is rewritten.
