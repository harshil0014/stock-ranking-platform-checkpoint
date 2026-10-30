"""Post-lock full-value comparison of ten original source dates in V11/V12."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import hashlib
import json
import pandas as pd

BASE=ROOT/"experiments/personalized-deep-history-20261002"
V11=BASE/"real-panel-v11/deep_panel.csv.gz"
V12=BASE/"real-panel-v12/deep_panel.csv.gz"
OUT=BASE/"real-panel-v12/source_value_audit.json"
SUMMARY=json.loads((BASE/"real-panel-v12/summary.json").read_text())
LOCK=ROOT/"experiments/personalized-deep-championship-20261002/v3/locked_selection.json"
EVAL=ROOT/"experiments/personalized-deep-championship-20261002/v3/evaluation_record.json"
if not LOCK.exists() or not EVAL.exists():
    raise RuntimeError("full-value audit is post-lock only")
dates=set(SUMMARY["source_dates"])

def source_rows(path):
    blocks=[]
    for chunk in pd.read_csv(path,low_memory=False,chunksize=100000):
        selected=chunk.loc[chunk.decision_date.isin(dates)]
        if len(selected):blocks.append(selected)
    return pd.concat(blocks,ignore_index=True).sort_values(
        ["decision_date","profile_name","isin"]).reset_index(drop=True)

a=source_rows(V11)
b=source_rows(V12)
pd.testing.assert_frame_equal(a,b,check_dtype=False,check_exact=False,rtol=1e-12,atol=1e-12)
assert len(a)==304670
record={"schema":"personalized_v12_source_value_audit_v1",
        "post_lock_only":True,"source_dates":len(dates),"source_rows":len(a),
        "all_columns_compared":list(a.columns),"values_identical_within_csv_roundtrip_tolerance":True,
        "rtol":1e-12,"atol":1e-12,
        "v11_sha256":hashlib.sha256(V11.read_bytes()).hexdigest(),
        "v12_sha256":hashlib.sha256(V12.read_bytes()).hexdigest()}
OUT.write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
print("full source-value audit passed",len(a),"rows",len(a.columns),"columns")
