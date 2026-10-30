import pandas as pd
cur=pd.read_csv(r"experiments/current-data-recovery-20261003/current_company_facts_recovered_v3_screener.csv.gz",low_memory=False)
q=pd.read_csv(r"C:\Users\Harshil\Downloads\_Organized\Documents\query-results.csv",low_memory=False)
print("rows",len(q),"cols",len(q.columns),"unique isin",q["ISIN Code"].nunique(),"dup",q["ISIN Code"].duplicated().sum())
print("cols")
for c in q.columns: print(c)
m=cur.merge(q,left_on="isin",right_on="ISIN Code",how="left",indicator=True)
print("exact matches",int((m["_merge"]=="both").sum()),"of",len(cur))
print("unmatched current",int((m["_merge"]!="both").sum()))
print("query missing per col")
for c in q.columns:
    print(c,int(q[c].isna().sum()))
