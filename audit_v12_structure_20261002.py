from pathlib import Path
import json
import pandas as pd

ROOT = Path(r"C:\Users\Harshil\Downloads\stock-ranking-platform-fresh-canonical-verified")
V11 = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v11"
V12 = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v12"
CUTOFF = pd.Timestamp("2026-09-18")

s11 = json.loads((V11 / "summary.json").read_text(encoding="utf-8"))
s12 = json.loads((V12 / "summary.json").read_text(encoding="utf-8"))
source_dates = set(s12["source_dates"])
additional_dates = set(s12["additional_dates"])

usecols = ["decision_date","profile_name","isin","endpoint","status","partition"]
d = pd.read_csv(V12 / "deep_panel.csv.gz", usecols=usecols, low_memory=False)
keys = ["decision_date","profile_name","isin"]
endpoint = pd.to_datetime(d["endpoint"], errors="raise")
decision = pd.to_datetime(d["decision_date"], errors="raise")
assert len(d) == s12["total_matured_observations"]
assert d["decision_date"].nunique() == 50
assert d["profile_name"].nunique() == 9
assert not d.duplicated(keys).any()
assert not endpoint.gt(CUTOFF).any()
assert not decision.ge(endpoint).any()
assert set(d["decision_date"].astype(str).unique()) == source_dates | additional_dates
added = d.loc[d["decision_date"].astype(str).isin(additional_dates)]
assert added["partition"].astype(str).eq("DEEP_ADDED").all()

cov = pd.read_csv(V12 / "date_coverage.csv")
delta = pd.read_csv(V12 / "coverage_delta_vs_v11.csv")
assert len(cov) == 50
assert int(delta["rows_delta"].sum()) == len(d) - s11["total_matured_observations"]
assert int((delta["rows_delta"] > 0).sum()) == 38
assert int((delta["available_delta"] > 0).sum()) == 38
assert int(delta["rows_delta"].max()) == 599

def source_rows(path):
    parts = []
    for chunk in pd.read_csv(path, chunksize=100000, low_memory=False):
        x = chunk.loc[chunk["decision_date"].astype(str).isin(source_dates)]
        if not x.empty:
            parts.append(x)
    return pd.concat(parts, ignore_index=True)
left = source_rows(V11 / "deep_panel.csv.gz")
right = source_rows(V12 / "deep_panel.csv.gz")
assert left.shape == right.shape
assert list(left.columns) == list(right.columns)
pd.testing.assert_frame_equal(left, right, check_dtype=False, check_exact=True)

sealed = cov.loc[cov["decision_date"].isin(["2025-01-31","2025-08-31"]),
                 ["decision_date","rows","identities","profiles","available"]]
result = {
    "rows": len(d),
    "dates": int(d["decision_date"].nunique()),
    "profiles": int(d["profile_name"].nunique()),
    "duplicate_keys": int(d.duplicated(keys).sum()),
    "maturity_violations": int(endpoint.gt(CUTOFF).sum() + decision.ge(endpoint).sum()),
    "source_rows_exactly_unchanged": True,
    "source_rows": int(len(left)),
    "v11_rows": int(s11["total_matured_observations"]),
    "rows_delta_vs_v11": int(len(d) - s11["total_matured_observations"]),
    "available": int(d["status"].eq("AVAILABLE").sum()),
    "available_delta_vs_v11": int(delta["available_delta"].sum()),
    "dates_with_row_gain": int((delta["rows_delta"] > 0).sum()),
    "dates_with_available_gain": int((delta["available_delta"] > 0).sum()),
    "max_identity_gain_per_date": int(delta["identities_delta"].max()),
    "sealed_date_metadata_only": sealed.to_dict("records"),
}
print(json.dumps(result, indent=2))
