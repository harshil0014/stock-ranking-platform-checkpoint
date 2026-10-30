"""Fail-closed research audit of provider/official multiplier alignment."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'experiments/sector-action-integrity-20261008'
PROVIDER=ROOT/'experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2/split_ledger.csv'
OFFICIAL=ROOT/'experiments/personalized-official-action-freeze/build-06/normalized_official_action_ledger.csv.gz'

def align(provider,official):
    p=provider.copy();o=official.copy();p.event_date=pd.to_datetime(p.event_date);o.event_date=pd.to_datetime(o.event_date)
    rows=[]
    for r in p.itertuples():
        nearby=o[o['isin'].eq(r.isin)&o.event_date.between(r.event_date-pd.Timedelta(days=7),r.event_date+pd.Timedelta(days=7))]
        auto=nearby[nearby.mechanics_status.eq('AUTO_MULTIPLIER')]
        observed=float(auto.total_share_multiplier.prod()) if len(auto) else np.nan
        status='ALIGNED_MULTIPLIER' if len(auto) and np.isclose(observed,r.split_ratio,rtol=.002,atol=1e-9) else 'UNRESOLVED_PROVIDER_OFFICIAL_MISMATCH'
        rows.append(dict(isin=r.isin,ticker=r.ticker,event_date=r.event_date.date().isoformat(),provider_ratio=r.split_ratio,official_ratio=observed,nearby_official_events=len(nearby),status=status,provider_source=r.source_url))
    return pd.DataFrame(rows)

def flagged_windows(frame,events):
    flags=pd.Series(False,index=frame.index)
    for isin,g in events[events.status.eq('UNRESOLVED_PROVIDER_OFFICIAL_MISMATCH')].groupby('isin'):
        indexes=frame.index[frame['isin'].eq(isin)]
        if not len(indexes):continue
        part=frame.loc[indexes]
        for day in g.event_date:
            flags.loc[indexes] |= part.decision_date.lt(day)&part.endpoint.ge(day)
    return flags

def run():
    OUT.mkdir(exist_ok=True)
    p=pd.read_csv(PROVIDER);o=pd.read_csv(OFFICIAL);events=align(p,o);events.to_csv(OUT/'provider_official_alignment.csv',index=False)
    x=pd.read_pickle(ROOT/'experiments/profile-aware-sector-20261008/prepared.pkl.gz',compression='gzip')
    flags=flagged_windows(x,events)
    x.loc[flags,['isin','decision_date','endpoint','profile_name','sector','future_xirr','future_drawdown','future_shortfall']].to_csv(OUT/'unreconciled_outcome_windows.csv.gz',index=False)
    from stock_research.personalized_official_actions import OfficialActionHistoryBook
    from stock_research.personalized_executable_tournament import load_protocol
    identities=pd.DataFrame([dict(isin='INE955I01044',ticker='SEJALLTD')]);_,profiles=load_protocol(ROOT/'research/protocols/personalized_official_action_tournament_v1.json')
    records=[]
    for variant in ['retained_ledger','documented_consolidation','retained_ledger_with_guard']:
        ledger=o.copy()
        if variant=='documented_consolidation':
            row={c:None for c in ledger.columns};row.update(isin='INE955I01044',ticker='SEJALLTD',event_date='2021-05-07',event_type='CONSOLIDATION',mechanics_status='AUTO_MULTIPLIER',total_share_multiplier=100000/33550000,source_text='Issuer 2021-22 annual report share consolidation; provider ex-date 2021-05-07; record date 2021-05-10',evidence_url='https://sejalglass.co.in/document/Annual%20Report%202021-2022.pdf')
            ledger=pd.concat([ledger,pd.DataFrame([row])],ignore_index=True)
        book=OfficialActionHistoryBook(identities,ROOT/'data/live_market/history_cache',PROVIDER.parent,ledger,as_of_date='2026-10-03',enforce_provider_alignment=variant!='retained_ledger')
        r=book.simulate(profiles['base7500'],'2022-03-31',months=12,include_journal=False);r['variant']=variant;records.append(r)
    replay=pd.concat(records);replay.to_csv(OUT/'sejal_simulation_replay.csv',index=False)
    assert np.isclose(replay.loc[replay.variant.eq('retained_ledger'),'xirr'].iloc[0],9086.008636,rtol=1e-8)
    assert replay.loc[replay.variant.eq('documented_consolidation'),'status'].iloc[0]=='UNRESOLVED_FRACTIONAL_ENTITLEMENT'
    assert replay.loc[replay.variant.eq('retained_ledger_with_guard'),'status'].iloc[0]=='UNRESOLVED_CORPORATE_ACTION'
    assert replay.loc[replay.variant.eq('retained_ledger_with_guard'),'xirr'].isna().all()
    details={'provider_events':len(events),'unreconciled_events':int(events.status.ne('ALIGNED_MULTIPLIER').sum()),'historical_rows':len(x),'outcome_windows_flagged':int(flags.sum()),'finite_outcome_windows_flagged':int((flags&x.future_xirr.notna()).sum()),'flagged_above_1000_percent':int((flags&x.future_xirr.gt(10)).sum()),'sejal_extreme_label_reproduced':True,'sejal_event_correction_requires_fractional_entitlement_resolution':True,'source_data_modified':False,'interpretation':'Alignment is an evidence gate, not proof every flagged provider event is correct or every unflagged outcome is valid. Identity changes and event-date/multiplier differences require adjudication. No provider action is silently promoted to official authority.'}
    details['sha256']={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [PROVIDER,OFFICIAL,OUT/'provider_official_alignment.csv',OUT/'sejal_simulation_replay.csv']}
    (OUT/'verification.json').write_text(json.dumps(details,indent=2))
    # Preserve all source rows/scores; guard only unresolved outcome labels.
    guarded=x.copy();guarded.loc[flags,['future_xirr','future_drawdown','future_shortfall']]=np.nan
    guarded.to_pickle(OUT/'guarded_training.pkl.gz',compression='gzip')
    print(json.dumps({k:v for k,v in details.items() if k!='sha256'},indent=2),flush=True)

if __name__=='__main__':run()
