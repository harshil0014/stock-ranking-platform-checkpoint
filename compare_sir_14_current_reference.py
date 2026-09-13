from pathlib import Path
import json
import pandas as pd
import numpy as np

ROOT = Path(".")
state_path = ROOT / "data" / "company_facts" / "accepted_state.json"
state = json.loads(state_path.read_text(encoding="utf-8"))
snapshot = ROOT / "data" / "company_facts" / state["snapshot_path"] / "company_facts.csv"

d = pd.read_csv(snapshot, low_memory=False, dtype={"exchange_security_id": str})
d["exchange_security_id"] = (
    d["exchange_security_id"]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.replace(r"\.0$", "", regex=True)
)

# Sir's supplied global order.
targets = [
    (1, "BOM:539997", None, "539997"),
    (2, "NSE:SHAILY", "SHAILY", None),
    (3, "NSE:TDPOWERSYS", "TDPOWERSYS", None),
    (4, "GVT&D", "GVT&D", None),
    (5, "NSE:V2RETAIL", "V2RETAIL", None),
    (6, "BOM:524717", None, "524717"),
    (7, "NSE:TERASOFT", "TERASOFT", None),
    (8, "NSE:KRISHANA", "KRISHANA", None),
    (9, "NSE:LUMAXTECH", "LUMAXTECH", None),
    (10, "NSE:APOLLO", "APOLLO", None),
    (11, "NSE:INDOTECH", "INDOTECH", None),
    (12, "NSE:WELCORP", "WELCORP", None),
    (13, "NSE:CEMPRO", "CEMPRO", None),
    (14, "BOM:522195", None, "522195"),
]

# Presentation-only current/reference composite.
# Higher percentile = better within the stock's own product sector.
higher_better = [
    "screener_roce_pct",
    "screener_roe_pct",
    "screener_profit_growth_pct",
    "screener_sales_growth_pct",
    "screener_return_1y_pct",
    "screener_earnings_yield_pct",
]
lower_better = [
    "screener_debt_to_equity",
]

for col in higher_better + lower_better:
    d[col] = pd.to_numeric(d[col], errors="coerce")
    d.loc[~np.isfinite(d[col]), col] = np.nan

pct_cols = []
for col in higher_better:
    out = f"pct__{col}"
    d[out] = d.groupby("product_sector", dropna=False)[col].rank(
        method="average", pct=True, ascending=True
    )
    pct_cols.append(out)

for col in lower_better:
    out = f"pct__{col}"
    d[out] = d.groupby("product_sector", dropna=False)[col].rank(
        method="average", pct=True, ascending=False
    )
    pct_cols.append(out)

d["current_ref_factor_count"] = d[pct_cols].notna().sum(axis=1)
d["current_ref_score"] = d[pct_cols].mean(axis=1, skipna=True) * 100.0
d.loc[d["current_ref_factor_count"] < 4, "current_ref_score"] = np.nan

resolved = []
unresolved = []

for sir_rank, sir_code, ticker, bse_code in targets:
    if ticker is not None:
        hit = d.loc[d["ticker"].eq(ticker)]
    else:
        hit = d.loc[
            d["primary_exchange"].astype(str).str.upper().eq("BSE")
            & d["exchange_security_id"].eq(str(bse_code))
        ]

    if len(hit) != 1:
        unresolved.append((sir_rank, sir_code, len(hit)))
        continue

    row = hit.iloc[0].copy()
    row["sir_rank"] = sir_rank
    row["sir_code"] = sir_code
    resolved.append(row)

x = pd.DataFrame(resolved)
if x.empty:
    raise SystemExit("No Sir-list stocks resolved.")

x["current_ref_rank_14"] = x["current_ref_score"].rank(
    method="min", ascending=False
)

# Rank agreement across resolved names.
valid = x.dropna(subset=["current_ref_rank_14"]).copy()
rank_corr = (
    valid["sir_rank"].astype(float).corr(valid["current_ref_rank_14"].astype(float))
    if len(valid) >= 2 else float("nan")
)

cols = [
    "sir_rank", "sir_code", "ticker", "company",
    "product_sector", "product_industry",
    "current_ref_rank_14", "current_ref_score", "current_ref_factor_count",
    "product_baseline_eligible", "product_baseline_sector_rank", "product_baseline_score",
    "v2_eligible", "research_v2_sector_rank", "research_v2_score", "v2_reason_code",
]

print("\nPRESENTATION-ONLY CURRENT REFERENCE COMPOSITE")
print("NOT Research V2. NOT PIT. Does not modify any accepted ranking model.\n")
print(x.sort_values("sir_rank")[cols].to_string(index=False))
print(f"\nResolved: {len(x)}/14")
print(f"Sir-vs-current-reference rank correlation: {rank_corr:.4f}" if pd.notna(rank_corr) else "Rank correlation: unavailable")

if unresolved:
    print("\nUNRESOLVED:")
    for item in unresolved:
        print(item)

out_dir = ROOT / "data" / "analysis"
out_dir.mkdir(parents=True, exist_ok=True)
out = out_dir / "sir_14_current_reference_comparison.csv"
x.sort_values("sir_rank")[cols].to_csv(out, index=False)
print(f"\nSaved: {out}")
