from pathlib import Path
import hashlib
import json
import shutil
import sys

import pandas as pd

ROOT = Path(r"C:\Users\Harshil\Downloads\stock-ranking-platform-fresh-canonical-verified")
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from research.runners.build_deep_personalized_panel_20261002 import _date_overlap

V9 = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v9"
SHARD = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v10-older-shard"
OUT = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v10"
CUTOFF = pd.Timestamp("2026-09-18")
NEW_DATES = (
    "2015-03-31", "2015-06-30", "2015-09-30", "2015-12-31",
    "2016-03-31", "2016-09-30", "2017-03-31", "2017-09-30",
    "2018-03-31", "2018-09-30", "2019-03-31", "2019-09-30",
)

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

if OUT.exists():
    raise FileExistsError(f"fresh output required: {OUT}")
OUT.mkdir(parents=True)
v9_summary = json.loads((V9 / "summary.json").read_text(encoding="utf-8"))
base = pd.read_csv(V9 / "deep_panel.csv.gz", low_memory=False)

checkpoints = []
checkpoint_hashes = {}
for date in NEW_DATES:
    path = SHARD / "checkpoints" / f"deep_added-{date}.csv.gz"
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, low_memory=False)
    if set(frame["decision_date"].astype(str)) != {date}:
        raise ValueError(f"checkpoint date mismatch: {path.name}")
    checkpoints.append(frame)
    checkpoint_hashes[path.name] = sha(path)

added = pd.concat(checkpoints, ignore_index=True)
if set(added["decision_date"].astype(str)) != set(NEW_DATES):
    raise ValueError("new-date set mismatch")
if not added["partition"].astype(str).eq("DEEP_ADDED").all():
    raise ValueError("older shard partition drift")

keys = ["decision_date", "profile_name", "isin"]
overlap_keys = base[keys].merge(added[keys], on=keys, how="inner")
if not overlap_keys.empty:
    raise ValueError("V9 and older shard overlap on panel keys")
panel = pd.concat([base, added], ignore_index=True)
if panel.duplicated(keys).any():
    raise ValueError("duplicate panel keys after V10 merge")
panel["endpoint"] = pd.to_datetime(panel["endpoint"], errors="raise")
decision = pd.to_datetime(panel["decision_date"], errors="raise")
if panel["endpoint"].gt(CUTOFF).any():
    raise ValueError("unmatured outcome entered V10")
if decision.ge(panel["endpoint"]).any():
    raise ValueError("decision date is not strictly before endpoint")

panel.to_csv(
    OUT / "deep_panel.csv.gz",
    index=False,
    compression={"method": "gzip", "mtime": 0},
)

all_dates = sorted(panel["decision_date"].astype(str).unique())
date_coverage = panel.groupby("decision_date", as_index=False).agg(
    rows=("isin", "size"),
    identities=("isin", "nunique"),
    profiles=("profile_name", "nunique"),
    endpoint=("endpoint", "max"),
    available=("status", lambda x: int(x.eq("AVAILABLE").sum())),
)
date_coverage.to_csv(OUT / "date_coverage.csv", index=False)

window_overlap = _date_overlap(all_dates)
window_overlap.to_csv(OUT / "outcome_window_overlap.csv", index=False)
shutil.copy2(V9 / "provider_lookup_quarantine.csv", OUT / "provider_lookup_quarantine.csv")

source_rows = int(v9_summary["total_matured_observations"]) - int(v9_summary["matured_observation_increase"])
summary = dict(v9_summary)
summary["schema_version"] = "deep_personalized_execution_panel_v2"
summary["parent_panel"] = str(V9.relative_to(ROOT)).replace("\\", "/")
summary["older_regime_extension"] = {
    "dates": list(NEW_DATES),
    "reason": "Quarterly 2015 plus missing Mar/Sep quarters in 2016-2019.",
    "earliest_decision_date": min(NEW_DATES),
    "official_action_ledger_min_date": "2010-01-15",
    "boundary_rule": "Earliest added decision is after a full 60-month lookback from the official-action ledger start.",
    "sealed_final_outcomes_inspected_for_extension": False,
}
summary["additional_dates"] = sorted(set(v9_summary["additional_dates"]) | set(NEW_DATES))
summary["all_dates"] = all_dates
summary["decision_date_increase"] = len(all_dates) - len(v9_summary["source_dates"])
summary["matured_observation_increase"] = int(len(panel) - source_rows)
summary["total_matured_observations"] = int(len(panel))
summary["overlap"] = {
    "adjacent_mean_fraction": float(
        window_overlap.loc[window_overlap.horizon_overlap_fraction.gt(0), "horizon_overlap_fraction"].mean()
    ),
    "pairs_with_overlap": int(window_overlap.horizon_overlap_fraction.gt(0).sum()),
    "total_pairs": int(len(window_overlap)),
}
summary["leakage_checks"] = dict(v9_summary["leakage_checks"])
summary["leakage_checks"]["older_extension_after_full_action_ledger_60m_boundary"] = True
summary["leakage_checks"]["untouched_final_labels_read_for_extension"] = False
summary["input_sha256"] = dict(v9_summary.get("input_sha256", {}))
summary["input_sha256"]["real-panel-v9/deep_panel.csv.gz"] = sha(V9 / "deep_panel.csv.gz")
summary["input_sha256"]["real-panel-v9/summary.json"] = sha(V9 / "summary.json")
summary["older_regime_extension"]["checkpoint_sha256"] = checkpoint_hashes
summary["output_sha256"] = {
    "deep_panel.csv.gz": sha(OUT / "deep_panel.csv.gz"),
    "date_coverage.csv": sha(OUT / "date_coverage.csv"),
    "outcome_window_overlap.csv": sha(OUT / "outcome_window_overlap.csv"),
    "provider_lookup_quarantine.csv": sha(OUT / "provider_lookup_quarantine.csv"),
}

(OUT / "summary.json").write_text(
    json.dumps(summary, indent=2, default=str) + "\n",
    encoding="utf-8",
)
print(json.dumps({
    "dates": len(all_dates),
    "new_dates": len(NEW_DATES),
    "rows": len(panel),
    "added_rows_vs_v9": len(panel) - len(base),
    "increase_vs_original": len(panel) - source_rows,
    "output": str(OUT),
}, indent=2))
