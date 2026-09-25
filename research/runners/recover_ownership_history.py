"""Recover research histories from validated local sources without changing accepted caches."""
from pathlib import Path
from hashlib import sha256
import json
import numpy as np
import pandas as pd
from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
ROOT=Path(__file__).resolve().parents[2]
def run():
 cache=ROOT/'data/live_market/history_cache'; out=ROOT/'external_research_pack/ownership_history_20260925';out.mkdir(exist_ok=True)
 normalized=ROOT/'research/data/ownership-recovery-20260925'
 facts=load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT/'data/company_facts')).facts
 state=json.loads((ROOT/'data/live_market/accepted_state.json').read_text());live_path=ROOT/'data/live_market'/state['bundle_path']/'live_market.csv'; live=pd.read_csv(live_path).set_index('isin')
 actions=pd.read_csv(ROOT/'experiments/personalized-official-action-freeze/build-05/normalized_official_action_ledger.csv.gz')
 candidates={}
 for audit in sorted((ROOT/'data/live_market').glob('history_cache_candidate_bse*_audit/per_code_decision.csv')):
  frame=pd.read_csv(audit,dtype={'bse_code':str});directory=audit.parent.with_name(audit.parent.name.removesuffix('_audit'))
  for row in frame.itertuples(index=False):
   if str(row.status).startswith('PROMOTED'):
    path=directory/(str(row.ticker)+'.csv')
    if path.exists(): candidates.setdefault(row.ticker,[]).append((path,str(getattr(row,'isin',''))))
 rows=[]
 for item in facts[['isin','ticker']].itertuples(index=False):
  path=cache/(item.ticker+'.csv');source=path;basis='YAHOO_SPLIT_ADJUSTED';frame=None
  if path.exists(): frame=pd.read_csv(path)
  for candidate,candidate_isin in reversed(candidates.get(item.ticker,[])):
   if candidate_isin and candidate_isin != item.isin:continue
   c=pd.read_csv(candidate)
   if frame is None:
    frame=c;source=candidate;basis='OFFICIAL_NOMINAL';break
   overlap=frame.merge(c,on='date',suffixes=('_live','_candidate'))
   if len(overlap)>=min(30,len(frame)) and np.isclose(overlap.raw_close_live,overlap.raw_close_candidate,atol=1e-8,rtol=1e-8).all():
    basis='OFFICIAL_NOMINAL';break
  if frame is None:
   rows.append(dict(isin=item.isin,ticker=item.ticker,status='NO_VALIDATED_LOCAL_HISTORY'));continue
  valid=np.isfinite(frame[['raw_close','adjusted_close']]).all(axis=1)&frame[['raw_close','adjusted_close']].gt(0).all(axis=1)
  dropped=int((~valid).sum());frame=frame.loc[valid & frame.date.le('2026-09-18')].copy()
  if frame.empty or frame.date.duplicated().any():continue
  original_last=frame.date.max();append=False;reason=''
  if item.isin in live.index:
   market=live.loc[item.isin];day=str(market.trade_date)
   if original_last<day<='2026-09-18' and market.snapshot_status=='AVAILABLE' and market.latest_price>0:
    gap=actions.loc[actions['isin'].eq(item.isin)&actions.event_date.gt(original_last)&actions.event_date.le(day)]
    if gap.empty:
     # Adjusted endpoint is inferred for compatibility; executable research uses price-only risk.
     ratio=frame.adjusted_close.iloc[-1]/frame.raw_close.iloc[-1]
     frame=pd.concat([frame,pd.DataFrame([dict(date=day,raw_close=market.latest_price,adjusted_close=market.latest_price*ratio)])],ignore_index=True);append=True
    else:reason='ACTION_IN_TERMINAL_GAP'
  changed=dropped or append or source!=path
  if changed: frame.to_csv(out/path.name,index=False,lineterminator='\n')
  rows.append(dict(isin=item.isin,ticker=item.ticker,status='OVERLAY' if changed else 'UNCHANGED',raw_basis=basis,provider_adjustment_through=original_last,removed_invalid_rows=dropped,appended_official_terminal=append,terminal_gap_reason=reason,source=str(source.relative_to(ROOT)),source_sha256=sha256(source.read_bytes()).hexdigest(),overlay_sha256=sha256((out/path.name).read_bytes()).hexdigest() if changed else '',terminal_source_sha256=sha256(live_path.read_bytes()).hexdigest() if append else ''))
 audit=pd.DataFrame(rows);audit.to_csv(normalized/'history_recovery_audit.csv',index=False,lineterminator='\n');print(audit.groupby(['status','raw_basis'],dropna=False).size().to_string(),flush=True)
if __name__=='__main__':run()
