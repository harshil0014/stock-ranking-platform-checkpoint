import pandas as pd
d=pd.read_csv(r"experiments/current-data-recovery-20261003/current_company_facts_recovered_v6_full_screener.csv.gz",low_memory=False)
for c in ["market_cap","shares_outstanding","latest_price","beta"]:
    print(c,int(d[c].isna().sum()))
print(d.loc[d["market_cap"].isna(),["ticker","company","isin","bulk_classification_provider_symbol","screener_nse_code","screener_bse_code"]].to_string(index=False))
