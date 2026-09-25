from pathlib import Path
import pandas as pd,json,hashlib
from stock_ranker.company_facts import load_company_fact_snapshot,resolve_company_fact_snapshot
root=Path('.'); dest=Path('research/data/ownership-recovery-20260925')
f=load_company_fact_snapshot(resolve_company_fact_snapshot(Path('data/company_facts'))).facts.set_index('ticker')
batches=Path('external_research_pack/event_terms_round2')
parsed=pd.concat([pd.read_csv(p).assign(source_path=str(p)) for p in batches.glob('batch_*/parsed_event_terms.csv')])
web=pd.concat([pd.read_csv(p).assign(source_path=str(p)) for p in batches.glob('batch_*/supplemental_web_terms.csv')])
critical=pd.read_csv('external_research_pack/residual_recovery_20260925/critical_event_terms_recovered.csv')
entries=[('RELIANCE','2023-07-20','JIOFIN',1,1,'https://archives.nseindia.com/content/circulars/FAOP57525.pdf'),('NIITLTD','2023-06-08','NIITMTS',1,1,'https://www.niit.com/india/press-release/niit-ltd-completes-demerger-of-corporate-learning-business-into-niit-learning-systems-ltd'),('SIEMENS','2025-04-07','ENRIN',1,1,''),('SANOFI','2024-06-13','SANOFICONR',1,1,''),('STLTECH','2025-04-24','STLNETWORK',1,1,''),('QUESS','2025-04-15','DIGITIDE',1,1,''),('QUESS','2025-04-15','BLUSPRING',1,1,''),('RAYMOND','2025-05-14','RAYMONDREL',1,1,''),('STAR','2024-12-06','ONESOURCE',1,2,''),('CHEMBOND','2025-05-09','CHEMBONDCH',2,1,''),('CPCAP','2025-05-09','CPEDU',1,1,''),('SKFINDIA','2025-10-15','SKFINDUS',1,1,''),('ABFRL','2025-05-22','ABLBL',1,1,'')]
entries.extend([
 ('MOTHERSON','2022-01-14','MSUMI',1,1,'https://nsearchives.nseindia.com/corporate/MOTHERSUMI_04012022214320_Disclosure_Record_Date.pdf'),
 ('MIRZAINT','2023-03-29','REDTAPE',1,1,'https://www.mirza.co.in/assets/pdf/Letter_to_SE_Cost_of_Acquisition_15042023.pdf'),
 ('NMDC','2022-10-27','NSLNISP',1,1,'https://www.nmdc.co.in/cms-admin/Upload/Investor_News_Documents/1e58eb7121db40d49f40999d76313e53_20220506154315900.pdf')])
entries.extend([
 ('GHCL','2023-04-06','GHCLTEXTIL',1,1,'https://ghcl.co.in/wp-content/uploads/2023/08/GHCL_Investor_Presentation_Q1FY24_August7_2023.pdf'),
 ('DHAMPURSUG','2022-05-13','DBOL',1,1,'https://api.dhampursugar.com/uploads/DSML_Annual_Report_for_the_year_ended_31_03_2022_1_0e533f1cc9.pdf'),
 ('RAYMOND','2024-07-11','RAYMONDLSL',4,5,'https://raymondlifestyle.com/uploads/invester_reports/Information%20Memorandum.pdf')])
entries.append(('ITC','2025-01-06','ITCHOTELS',1,10,'https://itcportal.com/content/dam/itc-corporate/pdfs/2023/demerger%20of%20hotels%20business.pdf'))
rows=[]
for parent,day,child,num,den,url in entries:
 isin=f.loc[parent,'isin']; source_path=''; snippet=''; source_hash=''
 p=parsed[(parsed['isin']==isin)&(parsed.event_date==day)]
 w=web[(web['isin']==isin)&(web.event_date==day)]
 c=critical[(critical['isin']==isin)&(critical.ledger_event_date==day)]
 if not url and len(w):
  url=w.iloc[0].source_url;source_path=w.iloc[0].source_path;snippet=w.iloc[0].note
 elif not url and len(c):
  url=c.iloc[0].source_url;source_path='external_research_pack/residual_recovery_20260925/critical_event_terms_recovered.csv';snippet=c.iloc[0].economic_terms
 elif not url and len(p):
  source_path=p.iloc[0].source_path; snippet=str(p.iloc[0].scheme_terms_snippets)
  inventory=pd.read_csv(Path(source_path).parent/'attachment_inventory.csv')
  urls=inventory[inventory.event_id.eq(p.iloc[0].event_id)].attachment_url.dropna().unique()
  url='|'.join(urls)
 if source_path: source_hash=hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
 rows.append(dict(parent_isin=isin,parent_ticker=parent,event_date=day,child_isin=f.loc[child,'isin'],child_ticker=child,numerator=num,denominator=den,source_url=url,source_path=source_path,source_sha256=source_hash,evidence_note=snippet[:1200],assumption='Hold resulting equity through terminal; no synthetic prelisting quote; unknown fractional cash blocks; price-only wealth'))
pd.DataFrame(rows).to_csv(dest/'resulting_equity_terms.csv',index=False)
json.dump({'protected_head':'097643b73d10f57a32cfb8ceb03d5edd17b6ddfe','cutoff':'2026-09-18','rights_policy_source':'https://www.nseindia.com/static/trade/members-faqs-rights-entitlement-trading','price_basis_evidence':'RELIANCE cached Close 1327.849976 on 2024-10-25 and 1334.349976 on 2024-10-28 around official 1:1 bonus: split-adjusted Close. Undo provider factor before whole-share purchases.','validation_policy':'Training endpoints strictly before each scoring decision. No reuse of old checkpoints.','return_scope':'Price capital gains and residual cash; dividend cash not modeled. Risk drawdown and CAGRs remain parent-security features, not combined portfolio drawdown.'},open(dest/'checkpoint_and_policy.json','w'),indent=2)
