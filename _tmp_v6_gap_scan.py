import pandas as pd
d=pd.read_csv(r"experiments/current-data-recovery-20261003/current_company_facts_recovered_v6_full_screener.csv.gz",low_memory=False)
for c in d.columns:
    lc=c.lower()
    if any(k in lc for k in ["risk","downside","draw","underwater","vol","history_month","listing_date","history_start","history_end","recovery"]):
        print(c,int(d[c].isna().sum()))
