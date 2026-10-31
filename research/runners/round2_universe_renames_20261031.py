"""Reconcile membership name changes only when a dated official rename exists."""
import pandas as pd
from round2_universe_20261031 import OUT,RAW,key,write_json,members_on

def reconstruct_with_renames(events,renames):
 active={};intervals=[];errors=[];counts=[];bridges=[]
 timeline=sorted(set(events.effective_date)|set(renames.effective_date))
 for day in timeline:
  for r in renames[renames.effective_date.eq(day)].to_dict('records'):
   old,new=r['old_key'],r['new_key']
   if old==new or old not in active:continue
   if new in active:
    errors.append(dict(effective_date=day,company_key=new,error='RENAME_COLLIDES_WITH_ACTIVE_IDENTITY'));continue
   previous=active.pop(old);previous['end_exclusive']=day;intervals.append(previous.copy())
   active[new]=dict(previous,company_key=new,company=r['new_name'],start_inclusive=day,end_exclusive=None)
   bridges.append(dict(effective_date=day,old_key=old,new_key=new,symbol=r['symbol'],issuer_key=previous['issuer_key']))
  g=events[events.effective_date.eq(day)]
  for action in ['EXCLUDE','INCLUDE']:
   for r in g[g.action.eq(action)].to_dict('records'):
    issuer=r['company_key']
    if action=='EXCLUDE':
     if issuer not in active:errors.append(dict(effective_date=day,company_key=issuer,error='EXCLUSION_WITHOUT_VERIFIED_ACTIVE_IDENTITY'));continue
     previous=active.pop(issuer);previous['end_exclusive']=day;intervals.append(previous.copy())
    elif issuer in active:errors.append(dict(effective_date=day,company_key=issuer,error='DUPLICATE_INCLUSION'))
    else:active[issuer]=dict(company_key=issuer,issuer_key=issuer,company=r['company'],start_inclusive=day,end_exclusive=None)
  if len(g):counts.append(dict(effective_date=day,member_count=len(active),sequence_errors_so_far=len(errors)))
 intervals.extend(active.values())
 return pd.DataFrame(intervals),pd.DataFrame(errors),pd.DataFrame(counts),pd.DataFrame(bridges)

def run():
 e=pd.read_csv(OUT/'official_membership_events.csv');r=pd.read_csv(RAW/'namechange.csv').rename(columns={'SYMBOL':'symbol','OLD NAME OF THE COMPANY':'old_name','NEW NAME OF THE COMPANY':'new_name','EFFECTIVE DATE':'date'})
 r['old_key']=r.old_name.map(key);r['new_key']=r.new_name.map(key);r['effective_date']=pd.to_datetime(r.date,format='%d-%b-%Y',errors='coerce').dt.strftime('%Y-%m-%d')
 r=r.dropna(subset=['effective_date']).drop_duplicates(['old_key','new_key','effective_date'])
 # The event workbook's pre-2012 names are a separate unresolved identity
 # vintage. Preserve its exact 500-name starting registry; do not push modern
 # aliases backwards across demergers or historically reused names.
 r=r[r.effective_date.ge('2012-01-01')]
 intervals,errors,counts,bridges=reconstruct_with_renames(e,r)
 for name,x in [('rename_membership_intervals',intervals),('rename_sequence_errors',errors),('rename_member_counts',counts),('official_rename_bridges',bridges)]:x.to_csv(OUT/(name+'.csv'),index=False)
 monthly=[]
 for day in pd.date_range('2012-01-31','2019-12-31',freq='ME'):
  d=str(day.date());m=members_on(intervals,d);monthly.append(dict(decision_date=d,members=len(m),prior_sequence_errors=int(errors.effective_date.le(d).sum()),independent_snapshot_verified=False,verified_terminal_outcomes=0))
 pd.DataFrame(monthly).to_csv(OUT/'rename_monthly_readiness.csv',index=False)
 snapshot=pd.read_csv(RAW/'snapshot_20150325112154.csv');snapshot['company_key']=snapshot['Company Name'].map(key)
 m=members_on(intervals,'2015-03-25');actual=set(snapshot.company_key);replayed=set(m.company_key)
 snapshot.to_csv(OUT/'archived_snapshot_capture_20150325.csv',index=False)
 write_json('snapshot_20150325_reconciliation.json',dict(archive_capture_timestamp='20150325112154',source_content_as_of=None,capture_is_not_certified_effective_date=True,snapshot_rows=len(snapshot),snapshot_unique_isins=snapshot['ISIN Code'].nunique(),replayed_names=len(replayed),exact_name_matches=len(actual&replayed),snapshot_only=sorted(actual-replayed),event_replay_only=sorted(replayed-actual),independently_complete_membership_verified=False,price_continuity_verified=False))
 write_json('rename_reconciliation.json',dict(official_rename_bridges=len(bridges),remaining_sequence_conflicts=len(errors),original_sequence_conflicts=15,price_outcomes_verified=False,primary_status='BLOCKED_UNVERIFIED_PRICE_TERMINALS_AND_REMAINING_MEMBERSHIP_CONFLICTS',interpretation='Dated official company rename from2012 onward only; pre2012 event-name registry preserved. No global name union or interpolation. Remaining conflicts and independent snapshot differences are preserved. Name membership is not verified price continuity.'))
 print('RECONCILED',len(bridges),len(errors),flush=True)
if __name__=='__main__':run()
