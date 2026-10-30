from pathlib import Path
import hashlib, json, re
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
DIR=ROOT/"experiments/current-data-recovery-20261003"
IN=DIR/"current_company_facts_recovered_v3_screener.csv.gz"
SCR=Path(r"C:\Users\Harshil\Downloads\_Organized\Documents\query-results.csv")
OUT=DIR/"current_company_facts_recovered_v4_screener_export.csv.gz"

d=pd.read_csv(IN,low_memory=False)
orig=d.copy(deep=True)
q=pd.read_csv(SCR,low_memory=False)
if q["ISIN Code"].duplicated().any():
    raise RuntimeError("duplicate ISIN in query export")
q=q.set_index("ISIN Code",drop=False)

MAP={
"Name":"screener_company_name",
"BSE Code":"screener_bse_code",
"NSE Code":"screener_nse_code",
"Industry Group":"screener_industry_group",
"Industry":"screener_industry",
"Current Price":"screener_current_price",
"Price to Earning":"screener_pe_ratio",
"Market Capitalization":"screener_market_cap_crore",
"Dividend yield":"screener_dividend_yield_pct",
"Net Profit latest quarter":"screener_latest_quarter_pat_crore",
"YOY Quarterly profit growth":"screener_quarterly_profit_growth_pct",
"Sales latest quarter":"screener_latest_quarter_sales_crore",
"YOY Quarterly sales growth":"screener_quarterly_sales_growth_pct",
"Return on capital employed":"screener_roce_pct",
"Sales":"screener_sales_crore",
"OPM":"screener_operating_margin_pct",
"Profit after tax":"screener_profit_after_tax_crore",
"EPS":"screener_eps",
"Change in promoter holding":"screener_promoter_holding_change_pct",
"Sales last year":"screener_annual_sales_crore",
"Operating profit last year":"screener_annual_operating_profit_crore",
}
EXTRA={
"Sales growth 5years median":"screener_sales_growth_5y_median_pct",
"Other income last year":"screener_annual_other_income_crore",
"EBIDT last year":"screener_annual_ebidt_crore",
"Depreciation last year":"screener_annual_depreciation_crore",
"EBIT last year":"screener_annual_ebit_crore",
"Interest last year":"screener_annual_interest_crore",
"Profit before tax last year":"screener_annual_pbt_crore",
"Tax last year":"screener_annual_tax_crore",
"Profit after tax last year":"screener_annual_pat_crore",
"Extraordinary items last year":"screener_annual_extraordinary_items_crore",
"Net Profit last year":"screener_annual_net_profit_crore",
"Dividend last year":"screener_annual_dividend_crore",
"Material cost last year":"screener_annual_material_cost_crore",
"Employee cost last year":"screener_annual_employee_cost_crore",
}
for target in EXTRA.values():
    if target not in d.columns:
        d[target]=np.nan

text_targets={"screener_company_name","screener_nse_code","screener_industry_group","screener_industry"}
ledger=[]
matched=0
for i,row in d.iterrows():
    isin=str(row.get("isin","")).strip()
    if isin not in q.index:
        continue
    matched+=1
    src=q.loc[isin]
    for source,target in {**MAP,**EXTRA}.items():
        if target not in d.columns:
            continue
        if pd.notna(d.at[i,target]):
            continue
        raw=src.get(source)
        if pd.isna(raw) or str(raw).strip()=="":
            continue
        if target in text_targets:
            value=str(raw).strip()
        else:
            value=pd.to_numeric(pd.Series([raw]),errors="coerce").iloc[0]
            if pd.isna(value):
                continue
            value=float(value)
        d.at[i,target]=value
        ledger.append({
            "row":int(i),"isin":isin,"ticker":row.get("ticker"),
            "field":target,"value":value,
            "source":"SCREENER_PREMIUM_QUERY_EXPORT_2026-10-03",
            "source_column":source,
        })

for i in d.index:
    isin=str(d.at[i,"isin"]).strip()
    if isin not in q.index:
        continue
    for field,value in [
        ("screener_source_isin",isin),
        ("screener_current_status","ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE"),
        ("screener_match_method","EXACT_ISIN"),
        ("screener_source_observed_at","2026-10-03"),
    ]:
        if field in d.columns and pd.isna(d.at[i,field]):
            d.at[i,field]=value
# Audit: existing trusted nonblank values in pre-existing mapped fields must remain unchanged.
for source,target in MAP.items():
    if target not in orig.columns:
        continue
    mask=orig[target].notna()
    if not mask.any():
        continue
    a=orig.loc[mask,target]
    b=d.loc[mask,target]
    if pd.api.types.is_numeric_dtype(a):
        av=pd.to_numeric(a,errors="coerce").to_numpy(float)
        bv=pd.to_numeric(b,errors="coerce").to_numpy(float)
        if not np.allclose(av,bv,rtol=0,atol=1e-12,equal_nan=True):
            raise RuntimeError("existing trusted numeric value changed: "+target)
    else:
        if not a.astype(str).reset_index(drop=True).equals(b.astype(str).reset_index(drop=True)):
            raise RuntimeError("existing trusted text value changed: "+target)

unmatched=d.loc[~d["isin"].astype(str).isin(q.index.astype(str)),
                [c for c in ["ticker","company","isin","screener_company_name","screener_nse_code","screener_bse_code"] if c in d.columns]].copy()
unmatched.to_csv(DIR/"screener_query_export_unmatched_current.csv",index=False)

d.to_csv(OUT,index=False,compression="gzip")
led=pd.DataFrame(ledger)
led.to_csv(DIR/"screener_query_export_filled_cells.csv",index=False)

before={}
after={}
for target in list(MAP.values())+list(EXTRA.values()):
    if target in orig.columns:
        before[target]=int(orig[target].isna().sum())
    else:
        before[target]=len(orig)
    after[target]=int(d[target].isna().sum())

sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
summary={
    "schema":"screener_premium_query_export_recovery_v1",
    "source_file":str(SCR),
    "source_sha256":sha(SCR),
    "source_rows":int(len(q)),
    "source_columns":int(len(q.columns)),
    "current_rows":int(len(d)),
    "exact_isin_matches":int(matched),
    "unmatched_current_rows":int(len(unmatched)),
    "filled_cells":int(len(led)),
    "stocks_filled":int(led["ticker"].nunique()) if len(led) else 0,
    "missing_before":before,
    "missing_after":after,
    "existing_nonblank_overwritten":0,
    "historical_training_modified":False,
    "production_modified":False,
}
(DIR/"screener_query_export_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
manifest={}
for p in [SCR,OUT,DIR/"screener_query_export_filled_cells.csv",DIR/"screener_query_export_unmatched_current.csv",DIR/"screener_query_export_summary.json"]:
    manifest[p.name]={"bytes":p.stat().st_size,"sha256":sha(p)}
(DIR/"screener_query_export_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
print(json.dumps(summary,indent=2))
print("UNMATCHED")
print(unmatched.to_string(index=False))
print("OUTPUT",OUT)
