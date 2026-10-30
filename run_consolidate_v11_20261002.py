from pathlib import Path
import hashlib, json, shutil, sys
import pandas as pd

ROOT = Path(r"C:\Users\Harshil\Downloads\stock-ranking-platform-fresh-canonical-verified")
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from research.runners.build_deep_personalized_panel_20261002 import _date_overlap

V10 = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v10"
BOUNDARY = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v11-boundary-shard"
OUT = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v11"
CUTOFF = pd.Timestamp("2026-09-18")
NEW_DATES = ("2015-01-31", "2015-02-28")

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

if OUT.exists():
    raise FileExistsError(f"fresh output required: {OUT}")
OUT.mkdir(parents=True)
base_summary = json.loads((V10 / "summary.json").read_text(encoding="utf-8"))
base = pd.read_csv(V10 / "deep_panel.csv.gz", low_memory=False)
parts = []
checkpoint_hashes = {}
for date in NEW_DATES:
    p = BOUNDARY / "checkpoints" / f"deep_added-{date}.csv.gz"
    if not p.is_file():
        raise FileNotFoundError(p)
    d = pd.read_csv(p, low_memory=False)
    if set(d["decision_date"].astype(str)) != {date}:
        raise ValueError(f"date mismatch: {date}")
    parts.append(d)
    checkpoint_hashes[p.name] = sha(p)

added = pd.concat(parts, ignore_index=True)
keys = ["decision_date", "profile_name", "isin"]
if not base[keys].merge(added[keys], on=keys, how="inner").empty:
    raise ValueError("V10/boundary key overlap")
panel = pd.concat([base, added], ignore_index=True)
if panel.duplicated(keys).any():
    raise ValueError("duplicate panel keys")
panel["endpoint"] = pd.to_datetime(panel["endpoint"], errors="raise")
decision = pd.to_datetime(panel["decision_date"], errors="raise")
if panel["endpoint"].gt(CUTOFF).any() or decision.ge(panel["endpoint"]).any():
    raise ValueError("maturity/leakage boundary violated")

panel.to_csv(OUT / "deep_panel.csv.gz", index=False,
             compression={"method": "gzip", "mtime": 0})
dates = sorted(panel["decision_date"].astype(str).unique())
coverage = panel.groupby("decision_date", as_index=False).agg(
    rows=("isin", "size"), identities=("isin", "nunique"),
    profiles=("profile_name", "nunique"), endpoint=("endpoint", "max"),
    available=("status", lambda x: int(x.eq("AVAILABLE").sum())))
coverage.to_csv(OUT / "date_coverage.csv", index=False)
overlap = _date_overlap(dates)
overlap.to_csv(OUT / "outcome_window_overlap.csv", index=False)
shutil.copy2(BOUNDARY / "provider_lookup_quarantine.csv",
             OUT / "provider_lookup_quarantine_boundary_v2.csv")
shutil.copy2(V10 / "provider_lookup_quarantine.csv",
             OUT / "provider_lookup_quarantine_v10.csv")

summary = dict(base_summary)
summary["schema_version"] = "deep_personalized_execution_panel_v3"
summary["parent_panel"] = str(V10.relative_to(ROOT)).replace("\\", "/")
summary["all_dates"] = dates
summary["additional_dates"] = sorted(set(base_summary["additional_dates"]) | set(NEW_DATES))
summary["decision_date_increase"] = len(dates) - len(base_summary["source_dates"])
summary["matured_observation_increase"] = int(base_summary["matured_observation_increase"]) + len(added)
summary["total_matured_observations"] = int(len(panel))
summary["boundary_extension_v11"] = {
    "dates": list(NEW_DATES),
    "rows_added": int(len(added)),
    "provider_split_ledger": "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2",
    "official_action_ledger_min_date": "2010-01-15",
    "full_60m_lookback_boundary_satisfied": True,
    "sealed_final_outcomes_inspected_for_extension": False,
    "checkpoint_sha256": checkpoint_hashes,
}
summary["overlap"] = {
    "adjacent_mean_fraction": float(overlap.loc[overlap.horizon_overlap_fraction.gt(0), "horizon_overlap_fraction"].mean()),
    "pairs_with_overlap": int(overlap.horizon_overlap_fraction.gt(0).sum()),
    "total_pairs": int(len(overlap)),
}
summary["leakage_checks"] = dict(base_summary["leakage_checks"])
summary["leakage_checks"]["v11_boundary_after_full_action_ledger_60m_boundary"] = True
summary["leakage_checks"]["untouched_final_labels_read_for_v11_extension"] = False
summary["input_sha256"] = dict(base_summary.get("input_sha256", {}))
summary["input_sha256"]["real-panel-v10/deep_panel.csv.gz"] = sha(V10 / "deep_panel.csv.gz")
summary["input_sha256"]["yahoo-split-ledger-v2/split_ledger.csv"] = sha(ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2/split_ledger.csv")
summary["output_sha256"] = {
    "deep_panel.csv.gz": sha(OUT / "deep_panel.csv.gz"),
    "date_coverage.csv": sha(OUT / "date_coverage.csv"),
    "outcome_window_overlap.csv": sha(OUT / "outcome_window_overlap.csv"),
}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
print(json.dumps({
    "dates": len(dates),
    "rows": len(panel),
    "added_rows_vs_v10": len(added),
    "earliest": dates[0],
    "latest": dates[-1],
    "output": str(OUT),
}, indent=2))
