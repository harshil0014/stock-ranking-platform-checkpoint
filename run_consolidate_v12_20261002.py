from pathlib import Path
import hashlib, json, shutil, sys
import pandas as pd

ROOT = Path(r"C:\Users\Harshil\Downloads\stock-ranking-platform-fresh-canonical-verified")
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from research.runners.build_deep_personalized_panel_20261002 import _date_overlap

V11 = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v11"
BOUNDARY = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v11-boundary-shard"
V2 = ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2"
OUT = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v12"
CUTOFF = pd.Timestamp("2026-09-18")
SHARDS = {
    "A": ROOT / "experiments/personalized-deep-history-20261002/real-panel-v12-v2-shardA",
    "B": ROOT / "experiments/personalized-deep-history-20261002/real-panel-v12-v2-shardB",
    "C": ROOT / "experiments/personalized-deep-history-20261002/real-panel-v12-v2-shardC",
    "D": ROOT / "experiments/personalized-deep-history-20261002/real-panel-v12-v2-shardD",
}

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()
if OUT.exists():
    raise FileExistsError(f"fresh output required: {OUT}")
summary11 = json.loads((V11 / "summary.json").read_text(encoding="utf-8"))
source_dates = set(summary11["source_dates"])
additional_dates = set(summary11["additional_dates"])
base = pd.read_csv(V11 / "deep_panel.csv.gz", low_memory=False)
source = base.loc[base["decision_date"].astype(str).isin(source_dates)].copy()
if set(source["decision_date"].astype(str).unique()) != source_dates:
    raise ValueError("source-date contract drift")

checkpoint_roots = [BOUNDARY / "checkpoints"] + [SHARDS[x] / "checkpoints" for x in "ABCD"]
by_date = {}
checkpoint_hashes = {}
for root in checkpoint_roots:
    if not root.is_dir():
        raise FileNotFoundError(root)
    for p in sorted(root.glob("deep_added-*.csv.gz")):
        date = p.name.removeprefix("deep_added-").removesuffix(".csv.gz")
        if date not in additional_dates:
            continue
        if date in by_date:
            raise ValueError(f"duplicate V2 checkpoint date: {date}")
        frame = pd.read_csv(p, low_memory=False)
        if set(frame["decision_date"].astype(str)) != {date}:
            raise ValueError(f"checkpoint date mismatch: {p}")
        if not frame["partition"].astype(str).eq("DEEP_ADDED").all():
            raise ValueError(f"partition drift: {p}")
        by_date[date] = frame
        checkpoint_hashes[date] = sha(p)
missing = sorted(additional_dates - set(by_date))
extra = sorted(set(by_date) - additional_dates)
if missing or extra:
    raise ValueError(f"checkpoint coverage mismatch missing={missing} extra={extra}")

rebuilt = pd.concat([by_date[d] for d in sorted(by_date)], ignore_index=True)
keys = ["decision_date", "profile_name", "isin"]
panel = pd.concat([source, rebuilt], ignore_index=True)
if panel.duplicated(keys).any():
    raise ValueError("duplicate V12 panel keys")
if set(panel["decision_date"].astype(str).unique()) != source_dates | additional_dates:
    raise ValueError("V12 date set mismatch")
panel["endpoint"] = pd.to_datetime(panel["endpoint"], errors="raise")
decision = pd.to_datetime(panel["decision_date"], errors="raise")
if panel["endpoint"].gt(CUTOFF).any() or decision.ge(panel["endpoint"]).any():
    raise ValueError("maturity/leakage boundary violated")

OUT.mkdir(parents=True)
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
coverage11 = pd.read_csv(V11 / "date_coverage.csv")
compare = coverage.merge(
    coverage11[["decision_date","rows","identities","available"]],
    on="decision_date", how="left", suffixes=("_v12","_v11"))
for c in ("rows","identities","available"):
    compare[f"{c}_delta"] = compare[f"{c}_v12"] - compare[f"{c}_v11"]
compare.to_csv(OUT / "coverage_delta_vs_v11.csv", index=False)

v2_summary = json.loads((V2 / "summary.json").read_text(encoding="utf-8"))
summary = dict(summary11)
summary["schema_version"] = "deep_personalized_execution_panel_v4"
summary["parent_panel"] = str(V11.relative_to(ROOT)).replace("\\", "/")
summary["all_dates"] = dates
summary["total_matured_observations"] = int(len(panel))
original_rows = len(source)
summary["matured_observation_increase"] = int(len(panel) - original_rows)
summary["provider_v2_propagation"] = {
    "scope": "all reconstructed/additional dates only; original source dates unchanged",
    "reconstructed_dates": len(additional_dates),
    "checkpoint_sha256": checkpoint_hashes,
    "ledger_path": str(V2.relative_to(ROOT)).replace("\\", "/"),
    "ledger_sha256": sha(V2 / "split_ledger.csv"),
    "audit_sha256": sha(V2 / "acquisition_audit.csv"),
    "successful_identities": int(v2_summary["status_counts"]["SUCCESS"]),
    "remaining_failed_identities": int(v2_summary["remaining_failed_identities"]),
    "split_event_count": int(v2_summary["split_event_count"]),
    "sealed_final_outcomes_inspected_for_collection": False,
}
summary["overlap"] = {
    "adjacent_mean_fraction": float(overlap.loc[overlap.horizon_overlap_fraction.gt(0), "horizon_overlap_fraction"].mean()),
    "pairs_with_overlap": int(overlap.horizon_overlap_fraction.gt(0).sum()),
    "total_pairs": int(len(overlap)),
}
summary["leakage_checks"] = dict(summary11["leakage_checks"])
summary["leakage_checks"]["all_reconstructed_dates_use_provider_v2"] = True
summary["leakage_checks"]["untouched_final_labels_read_for_v12_collection"] = False
summary["output_sha256"] = {
    "deep_panel.csv.gz": sha(OUT / "deep_panel.csv.gz"),
    "date_coverage.csv": sha(OUT / "date_coverage.csv"),
    "outcome_window_overlap.csv": sha(OUT / "outcome_window_overlap.csv"),
    "coverage_delta_vs_v11.csv": sha(OUT / "coverage_delta_vs_v11.csv"),
}
(OUT / "summary.json").write_text(
    json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
print(json.dumps({
    "dates": len(dates),
    "rows": len(panel),
    "source_rows_unchanged": len(source),
    "rebuilt_rows_v2": len(rebuilt),
    "rows_delta_vs_v11": len(panel) - len(base),
    "available": int(panel["status"].eq("AVAILABLE").sum()),
    "output": str(OUT),
}, indent=2))
