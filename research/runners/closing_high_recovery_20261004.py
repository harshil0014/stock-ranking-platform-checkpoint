"""Evaluate one predeclared continuity correction, retaining all period results."""
from pathlib import Path
import sys, json, gc
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'research/runners')]
from stock_ranker.closing_high_review import high_component, recovery_freshness, RECOVERY_BAND
import v17_peak_confirmation_20261004 as prior

OUT = ROOT/'experiments/closing-high-recovery-20261004'

def run():
    OUT.mkdir(exist_ok=True)
    protocol = {'recovery_band': RECOVERY_BAND, 'formula': 'age_freshness + (1-age_freshness)*exp(-(depth/0.05)^2)',
                'purpose': 'Remove score discontinuity at old highs; retain 30% closing-high weight',
                'selection': 'One fixed correction; no historical optimization of the band',
                'historical_scope': 'Previously exposed dates; current financial/SME flags never backfilled into history'}
    (OUT/'protocol.json').write_text(json.dumps(protocol, indent=2))
    winner=json.loads((prior.O/'selection_lock.json').read_text())['winner']
    results=[]
    for period in ['development','early','exposed']:
        # Read only the attribution inputs. No model refitting or wide panel joins.
        z=pd.read_csv(prior.O/f'{period}_scores.csv.gz').rename(columns={'new_score':'old_score'})
        fields=prior.p.KEYS+['days_since_recorded_high','distance_from_recorded_high']
        source=pd.read_pickle(prior.v.PREP,compression='gzip') if period=='exposed' else pd.read_pickle(prior.a.s.O/'historical.pkl')
        inputs=source[fields].copy();del source;gc.collect()
        z=z.merge(inputs,on=prior.p.KEYS,validate='one_to_one');del inputs;gc.collect()
        dates=set(z.decision_date)
        pieces=[]
        for chunk in pd.read_csv(prior.v.PANEL,usecols=prior.p.KEYS+prior.v.OUTCOME,chunksize=50000):
            pieces.append(chunk[chunk.decision_date.isin(dates)])
        outcomes=pd.concat(pieces,ignore_index=True)
        z=z.merge(outcomes,on=prior.p.KEYS,validate='one_to_one');del pieces,outcomes;gc.collect()
        original_age=np.exp(-z.days_since_recorded_high.clip(lower=0)/1095.75)
        z['recovery_score']=z.old_score+.15*(recovery_freshness(z.days_since_recorded_high,z.distance_from_recorded_high)-original_age)
        assert z.old_score.notna().equals(z.recovery_score.notna())
        for model in ['old_score','recovery_score']:
            metrics=prior.v.evaluate(z,model)
            metrics['period']=period; metrics['model']=model
            results.append(metrics)
        z[prior.p.KEYS+['old_score','recovery_score']].to_csv(OUT/f'{period}_scores.csv.gz',index=False)
        all_metrics=pd.concat(results,ignore_index=True)
        all_metrics.to_csv(OUT/'metrics.csv',index=False)
        all_metrics.groupby(['period','model'])[prior.v.METRICS].mean().to_csv(OUT/'summary.csv')
        print('DONE',period,flush=True)
        del z;gc.collect()
    current=pd.read_csv(prior.O/'current_rankings.csv.gz',low_memory=False)
    current['closing_high_component']=high_component(current.days_since_recorded_high,current.distance_from_recorded_high,current.high52_freshness)
    current['recovery_score']=prior.score(current,winner)
    current['recovery_rank']=prior.v.ranked(current,'recovery_score')
    current.to_csv(OUT/'current_rankings.csv.gz',index=False)
    current[current.recovery_rank.le(100)].to_csv(OUT/'current_top100.csv',index=False)
    assert all_metrics.decision_date.nunique()==44 and all_metrics.profile.nunique()==9
    print('COMPLETE 396 paired date/profile comparisons',flush=True)

if __name__=='__main__':run()
