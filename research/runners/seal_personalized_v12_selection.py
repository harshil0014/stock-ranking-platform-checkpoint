"""Add immutable source fingerprints before any V12 final outcome is revealed."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"experiments/personalized-deep-championship-20261002/v3"
LOCK=OUT/"locked_selection.json"
INITIAL=OUT/"locked_selection_initial.json"
SOURCES=(
    "research/runners/personalized_deeper_championship_v2.py",
    "research/runners/personalized_deeper_championship_v12.py",
    "research/runners/audit_personalized_deeper_championship_v2.py",
    "research/runners/probe_v12_score_adjustments.py",
    "research/runners/probe_v12_age_downside.py",
    "experiments/history-enrichment-20261002/final-data-quality-v3/history_enrichment.csv.gz",
    "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2/split_ledger.csv",
)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def run():
    if INITIAL.exists() or (OUT/"evaluation_record.json").exists() or (OUT/"untouched_final_profiles.csv").exists():
        raise FileExistsError("source seal must precede the single final evaluation")
    lock=json.loads(LOCK.read_text())
    if lock["final_evaluated"] or lock["selection_uses_untouched_final"]:
        raise ValueError("selection lock is not clean")
    INITIAL.write_bytes(LOCK.read_bytes())
    lock["initial_lock_sha256"]=sha(INITIAL)
    lock["source_sha256"]={name:sha(ROOT/name) for name in SOURCES}
    lock["source_seal_before_final"]=True
    LOCK.write_text(json.dumps(lock,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"final_lock_sha256":sha(LOCK),"initial_lock_sha256":lock["initial_lock_sha256"],
                      "sources":len(SOURCES),"winner":lock["winner"]["candidate"]},indent=2))

if __name__=="__main__":run()
