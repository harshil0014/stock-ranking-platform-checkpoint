from __future__ import annotations
from pathlib import Path
import hashlib, json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
DIR=ROOT/"experiments/current-data-recovery-20261003"
IN=DIR/"current_company_facts_recovered_v3_screener.csv.gz"
SCR=Path(r"C:\Users\Harshil\Downloads\query-results.csv")
OUT=DIR/"current_company_facts_recovered_v5_fresh_screener.csv.gz"
OBSERVED_AT="2026-10-03"

d=pd.read_csv(IN,low_memory=False)
orig=d.copy(deep=True)
q=pd.read_csv(SCR,low_memory=False)
if q["ISIN Code"].duplicated().any():
    raise RuntimeError("fresh Screener export contains duplicate ISINs")
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
"Net Profit latest quarter":"screener_latest_quarter_net_profit_crore",
"YOY Quarterly profit growth":"screener_quarterly_profit_growth_pct",
"Sales latest quarter":"screener_latest_quarter_sales_crore",
"YOY Quarterly sales growth":"screener_quarterly_sales_growth_pct",
"Return on capital employed":"screener_roce_pct",
"Price to book value":"screener_pb_ratio",
"Return on assets":"screener_return_on_assets_pct",
"Debt to equity":"screener_debt_to_equity",
"Return on equity":"screener_roe_pct",
"EPS":"screener_eps",
"Debt":"screener_total_debt_crore",
"Promoter holding":"screener_promoter_holding_pct",
"Change in promoter holding":"screener_promoter_holding_change_pct",
"Pledged percentage":"screener_pledged_pct",
"Public holding":"screener_public_holding_pct",
"FII holding":"screener_fii_holding_pct",
"Change in FII holding":"screener_fii_holding_change_pct",
"DII holding":"screener_dii_holding_pct",
"Change in DII holding":"screener_dii_holding_change_pct",
"Number of equity shares":"screener_number_equity_shares_crore",
"Book value":"screener_book_value",
"Working Capital Days":"screener_working_capital_days",
"Debtor days":"screener_debtor_days",
"Cash Conversion Cycle":"screener_cash_conversion_cycle_days",
"Days Inventory Outstanding":"screener_inventory_days",
"Asset Turnover Ratio":"screener_asset_turnover",
"Return over 3months":"screener_return_3m_pct",
"Return over 6months":"screener_return_6m_pct",
"Volume 1month average":"screener_volume_1month_avg",
"Volume 1week average":"screener_volume_1week_avg",
"Volume":"screener_volume",
"High price":"screener_high_price",
"Low price":"screener_low_price",
"High price all time":"screener_all_time_high_price",
"Low price all time":"screener_all_time_low_price",
"Return over 1day":"screener_return_1d_pct",
"Return over 1week":"screener_return_1week_pct",
"Return over 1month":"screener_return_1month_pct",
"Return over 1year":"screener_return_1y_pct",
"Return over 3years":"screener_return_3y_pct",
"Return over 5years":"screener_return_5y_pct",
"Profit after tax latest quarter":"screener_latest_quarter_pat_crore",
"Operating profit latest quarter":"screener_latest_quarter_operating_profit_crore",
"OPM latest quarter":"screener_latest_quarter_opm_pct",
"NPM latest quarter":"screener_latest_quarter_npm_pct",
"EPS latest quarter":"screener_latest_quarter_eps",
"Last result date":"screener_last_result_date",
"Sales growth 3Years":"screener_sales_growth_3y_pct",
"Sales":"screener_sales_crore",
"OPM":"screener_operating_margin_pct",
"Profit after tax":"screener_profit_after_tax_crore",
"Earnings yield":"screener_earnings_yield_pct",
}
SOURCE_SHA256=hashlib.sha256(SCR.read_bytes()).hexdigest()
for target in set(MAP.values()):
    if target not in d.columns:
        if target in {"screener_company_name","screener_nse_code","screener_industry_group",
                      "screener_industry","screener_last_result_date"}:
            d[target]=pd.Series([None]*len(d),dtype="object")
        else:
            d[target]=np.nan
for col in ["screener_fresh_export_observed_at","screener_fresh_export_sha256",
            "screener_fresh_export_match_method"]:
    if col not in d.columns:
        d[col]=pd.Series([None]*len(d),dtype="object")

TEXT_TARGETS={"screener_company_name","screener_nse_code","screener_industry_group",
              "screener_industry"}
for col in TEXT_TARGETS | {"screener_last_result_date"}:
    if col in d.columns:
        d[col]=d[col].astype("object")
ledger=[]

def clean_result_date(raw):
    if pd.isna(raw):
        return None
    s=str(raw).strip()
    try:
        n=int(float(s))
        if 190001 <= n <= 299912:
            y=n//100; m=n%100
            if 1 <= m <= 12:
                return f"{y:04d}-{m:02d}"
    except Exception:
        pass
    t=pd.to_datetime(s,errors="coerce")
    return None if pd.isna(t) else t.date().isoformat()

matched=0
for i,row in d.iterrows():
    isin=str(row.get("isin","")).strip()
    if isin not in q.index:
        continue
    matched+=1
    src=q.loc[isin]
    d.at[i,"screener_fresh_export_observed_at"]=OBSERVED_AT
    d.at[i,"screener_fresh_export_sha256"]=SOURCE_SHA256
    d.at[i,"screener_fresh_export_match_method"]="EXACT_ISIN"
    for source,target in MAP.items():
        if pd.notna(d.at[i,target]):
            continue
        raw=src.get(source)
        if pd.isna(raw) or str(raw).strip()=="":
            continue
        if target=="screener_last_result_date":
            value=clean_result_date(raw)
            if value is None:
                continue
        elif target in TEXT_TARGETS:
            value=str(raw).strip()
        else:
            value=pd.to_numeric(pd.Series([raw]),errors="coerce").iloc[0]
            if pd.isna(value):
                continue
            value=float(value)
        d.at[i,target]=value
        ledger.append({"row":int(i),"isin":isin,"ticker":row.get("ticker"),
                       "field":target,"value":value,
                       "source":"SCREENER_PREMIUM_FRESH_EXPORT_2026-10-03",
                       "source_column":source})
# Fill the ranking growth fields only when still blank. Screener returns are percentages.
for i in d.index:
    for target,source,srcfield in [
        ("product_baseline_yoy_growth","screener_return_1y_pct","product_baseline_yoy_growth_source"),
        ("product_baseline_cagr_3y","screener_return_3y_pct","product_baseline_cagr_3y_source"),
        ("product_baseline_cagr_5y","screener_return_5y_pct","product_baseline_cagr_5y_source"),
    ]:
        if target not in d.columns or pd.notna(d.at[i,target]):
            continue
        x=pd.to_numeric(pd.Series([d.at[i,source]]),errors="coerce").iloc[0]
        if pd.isna(x):
            continue
        value=float(x)/100.0
        d.at[i,target]=value
        if srcfield in d.columns:
            d.at[i,srcfield]="SCREENER_PREMIUM_FRESH_EXPORT"
        ledger.append({"row":int(i),"isin":d.at[i,"isin"],"ticker":d.at[i,"ticker"],
                       "field":target,"value":value,
                       "source":"SCREENER_PREMIUM_FRESH_EXPORT_2026-10-03",
                       "source_column":source})

# Preserve every original nonblank value in the V3 base.
for col in orig.columns:
    if col not in d.columns:
        raise RuntimeError("column disappeared: "+col)
    mask=orig[col].notna()
    if not mask.any():
        continue
    a=orig.loc[mask,col]
    b=d.loc[mask,col]
    if pd.api.types.is_numeric_dtype(a):
        av=pd.to_numeric(a,errors="coerce").to_numpy(float)
        bv=pd.to_numeric(b,errors="coerce").to_numpy(float)
        if not np.allclose(av,bv,rtol=0,atol=1e-12,equal_nan=True):
            raise RuntimeError("existing trusted numeric value changed: "+col)
    else:
        if not a.astype(str).reset_index(drop=True).equals(b.astype(str).reset_index(drop=True)):
            raise RuntimeError("existing trusted text value changed: "+col)
unmapped_source=[c for c in q.columns if c not in MAP and c!="ISIN Code"]
if unmapped_source:
    raise RuntimeError("fresh Screener columns were not absorbed: "+repr(unmapped_source))

unmatched=d.loc[~d["isin"].astype(str).isin(q.index.astype(str)),
                [c for c in ["ticker","company","isin","screener_company_name",
                             "screener_nse_code","screener_bse_code"] if c in d.columns]].copy()
unmatched.to_csv(DIR/"screener_fresh_export_unmatched_current.csv",index=False)

d.to_csv(OUT,index=False,compression="gzip")
led=pd.DataFrame(ledger)
led.to_csv(DIR/"screener_fresh_export_filled_cells.csv",index=False)

tracked=list(dict.fromkeys(list(MAP.values())+[
    "product_baseline_yoy_growth","product_baseline_cagr_3y","product_baseline_cagr_5y"
]))
before={c:int(orig[c].isna().sum()) if c in orig.columns else len(orig) for c in tracked}
after={c:int(d[c].isna().sum()) for c in tracked}
summary={
    "schema":"screener_premium_fresh_export_recovery_v1",
    "observed_at":OBSERVED_AT,
    "source_file":str(SCR),
    "source_sha256":SOURCE_SHA256,
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
    "all_source_columns_absorbed":True,
    "historical_training_modified":False,
    "production_modified":False,
}
(DIR/"screener_fresh_export_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest={}
for p in [SCR,OUT,DIR/"screener_fresh_export_filled_cells.csv",
          DIR/"screener_fresh_export_unmatched_current.csv",
          DIR/"screener_fresh_export_summary.json"]:
    manifest[p.name]={"bytes":p.stat().st_size,"sha256":sha(p)}
(DIR/"screener_fresh_export_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
print(json.dumps(summary,indent=2))
print("UNMATCHED")
print(unmatched.to_string(index=False))
print("OUTPUT",OUT)
