from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
DIR=ROOT/"experiments/current-data-recovery-20261003"
IN=DIR/"current_company_facts_recovered_v2.csv.gz"
SCR=Path(r"C:\Users\Harshil\Downloads\_Organized\Documents\SCREENER_MASTER_SNAPSHOT_2026-09-02.csv")
OUT=DIR/"current_company_facts_recovered_v3_screener.csv.gz"

d=pd.read_csv(IN,low_memory=False)
orig=d.copy(deep=True)
s=pd.read_csv(SCR,low_memory=False)
if s["ISIN Code"].duplicated().any():
    raise RuntimeError("Screener master has duplicate ISIN")
s=s.set_index("ISIN Code",drop=False)
MAP={
"Name":"screener_company_name","BSE Code":"screener_bse_code","NSE Code":"screener_nse_code",
"Industry Group":"screener_industry_group","Industry":"screener_industry",
"Current Price":"screener_current_price","Market Capitalization":"screener_market_cap_crore",
"Return on capital employed":"screener_roce_pct","Profit after tax":"screener_profit_after_tax_crore",
"Profit after tax latest quarter":"screener_latest_quarter_pat_crore","Sales":"screener_sales_crore",
"OPM":"screener_operating_margin_pct","Sales latest quarter":"screener_latest_quarter_sales_crore",
"YOY Quarterly sales growth":"screener_quarterly_sales_growth_pct","Price to Earning":"screener_pe_ratio",
"YOY Quarterly profit growth":"screener_quarterly_profit_growth_pct","Price to book value":"screener_pb_ratio",
"Dividend yield":"screener_dividend_yield_pct","Return on assets":"screener_return_on_assets_pct",
"Return on equity":"screener_roe_pct","EPS":"screener_eps","Debt":"screener_total_debt_crore",
"Sales growth 3Years":"screener_sales_growth_3y_pct","Sales growth 5Years":"screener_sales_growth_5y_pct",
"Profit growth 3Years":"screener_profit_growth_3y_pct","Profit growth 5Years":"screener_profit_growth_5y_pct",
"Average return on equity 5Years":"screener_roe_5y_avg_pct","Average return on equity 3Years":"screener_roe_3y_avg_pct",
"Return over 1year":"screener_return_1y_pct","Return over 5years":"screener_return_5y_pct",
"Return over 3years":"screener_return_3y_pct","Debt to equity":"screener_debt_to_equity",
"Return over 6months":"screener_return_6m_pct","Return over 3months":"screener_return_3m_pct",
"PEG Ratio":"screener_peg_ratio","Interest Coverage Ratio":"screener_interest_coverage",
"Current ratio":"screener_current_ratio","Enterprise Value":"screener_enterprise_value_crore",
"EVEBITDA":"screener_ev_ebitda","Price to Free Cash Flow":"screener_price_to_free_cash_flow",
"Price to Sales":"screener_price_to_sales","Profit growth":"screener_profit_growth_pct",
"Industry PE":"screener_industry_pe","Sales growth":"screener_sales_growth_pct",
"Pledged percentage":"screener_pledged_pct","Earnings yield":"screener_earnings_yield_pct",
"Change in promoter holding":"screener_promoter_holding_change_pct","Promoter holding":"screener_promoter_holding_pct",
}
TEXT_TARGETS={"screener_company_name","screener_nse_code","screener_industry_group","screener_industry"}
ledger=[]
matched=0
for i,row in d.iterrows():
    isin=str(row.get("isin",""))
    if isin not in s.index:
        continue
    matched+=1
    src=s.loc[isin]
    for source,target in MAP.items():
        if target not in d.columns or pd.notna(d.at[i,target]):
            continue
        raw=src.get(source)
        if pd.isna(raw) or str(raw).strip()=="":
            continue
        if target in TEXT_TARGETS:
            value=str(raw).strip()
        elif target=="screener_bse_code":
            value=pd.to_numeric(pd.Series([raw]),errors="coerce").iloc[0]
            if pd.isna(value): continue
            value=float(value)
        else:
            value=pd.to_numeric(pd.Series([raw]),errors="coerce").iloc[0]
            if pd.isna(value): continue
            value=float(value)
        d.at[i,target]=value
        ledger.append({"row":int(i),"isin":isin,"ticker":row.get("ticker"),"field":target,
                       "value":value,"source":"SCREENER_PREMIUM_MASTER_2026-09-02",
                       "source_column":source})
filled_rows={x["row"] for x in ledger}
for i in filled_rows:
    for field,value in [
        ("screener_source_isin",str(d.at[i,"isin"])),
        ("screener_current_status","ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE"),
        ("screener_match_method","EXACT_ISIN"),
        ("screener_source_observed_at","2026-09-02"),
    ]:
        if field in d.columns and pd.isna(d.at[i,field]):
            d.at[i,field]=value

def fill_num(i,target,value,source):
    if target not in d.columns or pd.notna(d.at[i,target]) or value is None or not np.isfinite(value):
        return
    d.at[i,target]=float(value)
    ledger.append({"row":int(i),"isin":d.at[i,"isin"],"ticker":d.at[i,"ticker"],
                   "field":target,"value":float(value),"source":source,"source_column":"DERIVED_FROM_SCREENER"})

for i in d.index:
    def n(col):
        if col not in d.columns: return None
        x=pd.to_numeric(pd.Series([d.at[i,col]]),errors="coerce").iloc[0]
        return None if pd.isna(x) else float(x)
    roe=n("screener_roe_pct"); sg=n("screener_sales_growth_pct")
    pg=n("screener_profit_growth_pct"); opm=n("screener_operating_margin_pct")
    if roe is not None: fill_num(i,"return_on_equity",roe/100,"SCREENER_PREMIUM_CURRENT_FALLBACK")
    if sg is not None: fill_num(i,"revenue_growth",sg/100,"SCREENER_PREMIUM_CURRENT_FALLBACK")
    if pg is not None: fill_num(i,"secondary_profit_growth",pg/100,"SCREENER_PREMIUM_CURRENT_FALLBACK")
    if opm is not None: fill_num(i,"operating_margin",opm/100,"SCREENER_PREMIUM_CURRENT_FALLBACK")
    mc=n("screener_market_cap_crore"); pe=n("screener_pe_ratio"); pb=n("screener_pb_ratio")
    eps=n("screener_eps"); dy=n("screener_dividend_yield_pct"); cp=n("screener_current_price")
    pat=n("screener_profit_after_tax_crore"); sales=n("screener_sales_crore")
    if mc is not None: fill_num(i,"market_cap",mc*10_000_000,"SCREENER_PREMIUM_CURRENT_FALLBACK")
    if pe is not None: fill_num(i,"pe_ratio",pe,"SCREENER_PREMIUM_CURRENT_FALLBACK")
    if pb is not None: fill_num(i,"pb_ratio",pb,"SCREENER_PREMIUM_CURRENT_FALLBACK")
    if eps is not None: fill_num(i,"trailing_eps",eps,"SCREENER_PREMIUM_CURRENT_FALLBACK")
    if dy is not None: fill_num(i,"dividend_yield",dy/100,"SCREENER_PREMIUM_CURRENT_FALLBACK")
    if cp not in (None,0) and pb not in (None,0):
        fill_num(i,"book_value",cp/pb,"SCREENER_PREMIUM_CURRENT_FALLBACK")
    if mc is not None and cp not in (None,0):
        fill_num(i,"shares_outstanding",mc*10_000_000/cp,"SCREENER_PREMIUM_CURRENT_FALLBACK")
    if pat is not None and sales not in (None,0):
        fill_num(i,"profit_margin",pat/sales,"SCREENER_PREMIUM_CURRENT_FALLBACK")
    for target,src in [
        ("promoter_holding_pct","screener_promoter_holding_pct"),
        ("promoter_pledge_pct","screener_pledged_pct"),
    ]:
        v=n(src)
        if v is not None: fill_num(i,target,v,"SCREENER_PREMIUM_CURRENT_FALLBACK")
for i in d.index:
    for target,src in [
        ("product_baseline_yoy_growth","screener_return_1y_pct"),
        ("product_baseline_cagr_3y","screener_return_3y_pct"),
        ("product_baseline_cagr_5y","screener_return_5y_pct"),
    ]:
        if target in d.columns and pd.isna(d.at[i,target]):
            x=pd.to_numeric(pd.Series([d.at[i,src]]),errors="coerce").iloc[0]
            if pd.notna(x):
                d.at[i,target]=float(x)/100.0
                ledger.append({"row":int(i),"isin":d.at[i,"isin"],"ticker":d.at[i,"ticker"],
                               "field":target,"value":float(x)/100.0,
                               "source":"SCREENER_PREMIUM_CURRENT_FALLBACK",
                               "source_column":src})

touched=sorted({x["field"] for x in ledger})
for col in touched:
    if col not in orig.columns:
        continue
    mask=orig[col].notna()
    if mask.any():
        a=orig.loc[mask,col]
        b=d.loc[mask,col]
        if pd.api.types.is_numeric_dtype(a):
            if not np.allclose(pd.to_numeric(a,errors="coerce"),pd.to_numeric(b,errors="coerce"),
                               rtol=0,atol=1e-12,equal_nan=True):
                raise RuntimeError("existing nonblank changed: "+col)
        elif not a.astype(str).reset_index(drop=True).equals(b.astype(str).reset_index(drop=True)):
            raise RuntimeError("existing nonblank changed: "+col)
d.to_csv(OUT,index=False,compression="gzip")
led=pd.DataFrame(ledger)
led.to_csv(DIR/"screener_premium_filled_cells.csv",index=False)
key=[
"product_baseline_yoy_growth","product_baseline_cagr_3y","product_baseline_cagr_5y",
"return_on_equity","revenue_growth","secondary_profit_growth","operating_margin",
"screener_roce_pct","screener_roe_pct","screener_debt_to_equity","screener_profit_growth_pct",
"screener_sales_growth_pct","screener_return_1y_pct","screener_return_3y_pct","screener_return_5y_pct",
"screener_market_cap_crore","screener_current_price","screener_pe_ratio","screener_pb_ratio"
]
before={c:int(orig[c].isna().sum()) for c in key if c in orig.columns}
after={c:int(d[c].isna().sum()) for c in key if c in d.columns}
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
summary={
"schema":"screener_premium_current_recovery_v1",
"screener_snapshot":str(SCR),
"screener_snapshot_sha256":sha(SCR),
"screener_rows":int(len(s)),"exact_isin_matches":int(matched),
"filled_cells":int(len(led)),"stocks_filled":int(led["ticker"].nunique()) if len(led) else 0,
"missing_before":before,"missing_after":after,
"existing_nonblank_overwritten":0,"historical_training_modified":False,"production_modified":False,
}
(DIR/"screener_premium_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
manifest={}
for p in [OUT,DIR/"screener_premium_filled_cells.csv",DIR/"screener_premium_summary.json"]:
    manifest[p.name]={"bytes":p.stat().st_size,"sha256":sha(p)}
(DIR/"screener_premium_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
print(json.dumps(summary,indent=2))
print("OUTPUT",OUT)
