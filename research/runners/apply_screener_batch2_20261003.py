from pathlib import Path
import hashlib, json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
DIR=ROOT/"experiments/current-data-recovery-20261003"
IN=DIR/"current_company_facts_recovered_v5_fresh_screener.csv.gz"
SCR=Path(r"C:\Users\Harshil\Downloads\_Organized\Documents\query-results (1)_20261003_182233.csv")
OUT=DIR/"current_company_facts_recovered_v6_full_screener.csv.gz"

d=pd.read_csv(IN,low_memory=False)
orig=d.copy(deep=True)
q=pd.read_csv(SCR,low_memory=False)
if q["ISIN Code"].duplicated().any():
    raise RuntimeError("duplicate ISIN in batch2")
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
"Industry PE":"screener_industry_pe",
"Sales growth":"screener_sales_growth_pct",
"Profit growth":"screener_profit_growth_pct",
"Price to Sales":"screener_price_to_sales",
"Price to Free Cash Flow":"screener_price_to_free_cash_flow",
"EVEBITDA":"screener_ev_ebitda",
"Enterprise Value":"screener_enterprise_value_crore",
"Current ratio":"screener_current_ratio",
"Interest Coverage Ratio":"screener_interest_coverage",
"PEG Ratio":"screener_peg_ratio",
"Sales growth 3Years":"screener_sales_growth_3y_pct",
"Sales growth 5Years":"screener_sales_growth_5y_pct",
"Profit growth 3Years":"screener_profit_growth_3y_pct",
"Profit growth 5Years":"screener_profit_growth_5y_pct",
"Average return on equity 3Years":"screener_roe_3y_avg_pct",
"Average return on equity 5Years":"screener_roe_5y_avg_pct",
"Cash Conversion Quality":"screener_cash_conversion_quality",
"Cash from operations last year":"screener_operating_cash_flow_crore",
"Free cash flow last year":"screener_free_cash_flow_crore",
"ROCE3yr avg":"screener_roce_3y_avg_pct",
"Return on invested capital":"screener_roic_pct",
"CROIC":"screener_croic_pct",
"Equity capital":"screener_equity_capital_crore",
"Reserves":"screener_reserves_crore",
"Total Assets":"screener_total_assets_crore",
"Current assets":"screener_current_assets_crore",
"Current liabilities":"screener_current_liabilities_crore",
"Inventory":"screener_inventory_crore",
"Trade receivables":"screener_trade_receivables_crore",
"Contingent liabilities":"screener_contingent_liabilities_crore",
"Cash from investing last year":"screener_cash_from_investing_crore",
"Cash from financing last year":"screener_cash_from_financing_crore",
"Net cash flow last year":"screener_net_cash_flow_crore",
"Sales last year":"screener_annual_sales_crore",
"Operating profit last year":"screener_annual_operating_profit_crore",
"Profit after tax last year":"screener_annual_pat_crore",
"OPM last year":"screener_annual_opm_pct",
"NPM last year":"screener_annual_npm_pct",
"Last annual result date":"screener_last_annual_result_date",
"Sales preceding year":"screener_prior_annual_sales_crore",
"Profit after tax preceding year":"screener_prior_annual_pat_crore",
}
SOURCE_SHA256=hashlib.sha256(SCR.read_bytes()).hexdigest()
TEXT_TARGETS={"screener_company_name","screener_nse_code","screener_industry_group","screener_industry",
              "screener_last_annual_result_date"}
for target in set(MAP.values()):
    if target not in d.columns:
        if target in TEXT_TARGETS:
            d[target]=pd.Series([None]*len(d),dtype="object")
        else:
            d[target]=np.nan
for col in TEXT_TARGETS:
    if col in d.columns:
        d[col]=d[col].astype("object")
for col in ["screener_batch2_observed_at","screener_batch2_sha256","screener_batch2_match_method"]:
    if col not in d.columns:
        d[col]=pd.Series([None]*len(d),dtype="object")

def clean_yyyymm(raw):
    if pd.isna(raw): return None
    s=str(raw).strip()
    try:
        n=int(float(s))
        if 190001 <= n <= 299912:
            y=n//100; m=n%100
            if 1 <= m <= 12: return f"{y:04d}-{m:02d}"
    except Exception:
        pass
    t=pd.to_datetime(s,errors="coerce")
    return None if pd.isna(t) else t.date().isoformat()

ledger=[]; matched=0
for i,row in d.iterrows():
    isin=str(row.get("isin","")).strip()
    if isin not in q.index: continue
    matched+=1
    src=q.loc[isin]
    d.at[i,"screener_batch2_observed_at"]="2026-10-03"
    d.at[i,"screener_batch2_sha256"]=SOURCE_SHA256
    d.at[i,"screener_batch2_match_method"]="EXACT_ISIN"
    for source,target in MAP.items():
        if pd.notna(d.at[i,target]): continue
        raw=src.get(source)
        if pd.isna(raw) or str(raw).strip()=="": continue
        if target=="screener_last_annual_result_date":
            value=clean_yyyymm(raw)
            if value is None: continue
        elif target in TEXT_TARGETS:
            value=str(raw).strip()
        else:
            value=pd.to_numeric(pd.Series([raw]),errors="coerce").iloc[0]
            if pd.isna(value): continue
            value=float(value)
        d.at[i,target]=value
        ledger.append({"row":int(i),"isin":isin,"ticker":row.get("ticker"),"field":target,
                       "value":value,"source":"SCREENER_PREMIUM_BATCH2_2026-10-03",
                       "source_column":source})
# Preserve all original nonblank values from V5.
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

unmapped=[c for c in q.columns if c not in MAP and c!="ISIN Code"]
if unmapped:
    raise RuntimeError("unmapped batch2 columns: "+repr(unmapped))
unmatched=d.loc[~d["isin"].astype(str).isin(q.index.astype(str)),
                [c for c in ["ticker","company","isin"] if c in d.columns]].copy()
unmatched.to_csv(DIR/"screener_batch2_unmatched_current.csv",index=False)

d.to_csv(OUT,index=False,compression="gzip")
led=pd.DataFrame(ledger)
led.to_csv(DIR/"screener_batch2_filled_cells.csv",index=False)

tracked=list(dict.fromkeys(MAP.values()))
before={c:int(orig[c].isna().sum()) if c in orig.columns else len(orig) for c in tracked}
after={c:int(d[c].isna().sum()) for c in tracked}
summary={
"schema":"screener_premium_batch2_recovery_v1",
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
(DIR/"screener_batch2_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest={}
for p in [SCR,OUT,DIR/"screener_batch2_filled_cells.csv",
          DIR/"screener_batch2_unmatched_current.csv",
          DIR/"screener_batch2_summary.json"]:
    manifest[p.name]={"bytes":p.stat().st_size,"sha256":sha(p)}
(DIR/"screener_batch2_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
print(json.dumps(summary,indent=2))
print("UNMATCHED")
print(unmatched.to_string(index=False))
print("OUTPUT",OUT)
