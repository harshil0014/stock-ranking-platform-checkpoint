import pandas as pd
d=pd.read_csv(r"experiments/current-data-recovery-20261003/current_company_facts_recovered_v6_full_screener.csv.gz",low_memory=False)
print(d[["ticker","company","primary_exchange","exchange_security_id","bulk_classification_provider_symbol"]].head(40).to_string(index=False))
print("\nEXCH",d["primary_exchange"].value_counts(dropna=False).to_dict())
print("\nprovider suffix",d["bulk_classification_provider_symbol"].dropna().astype(str).str.extract(r"(\.NS|\.BO)$")[0].value_counts(dropna=False).to_dict())
