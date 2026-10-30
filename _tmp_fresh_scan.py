import pandas as pd
cur=pd.read_csv(r"experiments/current-data-recovery-20261003/current_company_facts_recovered_v3_screener.csv.gz",low_memory=False)
q=pd.read_csv(r"C:\Users\Harshil\Downloads\query-results.csv",low_memory=False)
print("rows",len(q),"cols",len(q.columns),"unique isin",q["ISIN Code"].nunique(),"dup",q["ISIN Code"].duplicated().sum())
m=cur[["ticker","company","isin"]].merge(q[["ISIN Code"]],left_on="isin",right_on="ISIN Code",how="left",indicator=True)
print("matches",int((m["_merge"]=="both").sum()),"unmatched",int((m["_merge"]!="both").sum()))
print(m.loc[m["_merge"]!="both",["ticker","company","isin"]].to_string(index=False))
print("source missing")
for c in q.columns: print(c,int(q[c].isna().sum()))
