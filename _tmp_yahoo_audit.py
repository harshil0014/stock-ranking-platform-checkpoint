import pandas as pd
d=pd.read_csv(r"experiments/current-data-recovery-20261003/current_company_facts_recovered_v7_yahoo_full.csv.gz",low_memory=False)
print("STATUS",d["yahoo_status"].value_counts(dropna=False).to_dict())
for c in ["market_cap","shares_outstanding","latest_price","high_52w","recorded_high","product_baseline_days_since_recorded_high","current_history_months","current_downside_volatility_1y"]:
    print(c,int(d[c].isna().sum()))
u=d[d["yahoo_status"]!="OK"]
print("\nUNRESOLVED",len(u))
cols=["ticker","company","isin","primary_exchange","bulk_classification_provider_symbol","screener_nse_code","screener_bse_code","screener_current_price","screener_all_time_high_price","listing_date","yahoo_status"]
print(u[cols].head(180).to_string(index=False))
