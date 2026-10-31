"""A separate frozen strength curve; never modifies majority-family outputs."""
import argparse,json,hashlib
import numpy as np
import pandas as pd
import professor_majority_20261031 as base

ROOT=base.ROOT
OUT=ROOT/'experiments/professor-weight-curve-20261031'
PROTOCOL=ROOT/'research/protocols/professor_weight_curve_20261031.json'
SHARES={f'factor{int(100*w)}_fixed':w for w in [.1,.2,.35,.5]}


def blend(frame,share):
    if share not in SHARES.values():raise ValueError('Unregistered weight')
    core=frame[['q_'+c for c in base.FACTOR_COLUMNS]].mean(axis=1,skipna=False)
    return (share*core+(1-share)*frame.champion_percentile).where(frame.factor_eligible)


def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['score','evaluate','portfolio']);a=p.parse_args()
    if not PROTOCOL.exists():raise RuntimeError('Freeze follow-up protocol first')
    OUT.mkdir(exist_ok=True)
    source=ROOT/'experiments/professor-majority-20261031/scored.pkl.gz'
    base.OUT=OUT;base.PROTOCOL=PROTOCOL;base.NAMES=['active_champion']+list(SHARES)
    if a.stage=='score':
        if (OUT/'scored.pkl.gz').exists():return
        x=pd.read_pickle(source,compression='gzip')
        for name,w in SHARES.items():x[name]=blend(x,w)
        x.to_pickle(OUT/'scored.pkl.gz',compression='gzip')
        current=x.loc[x.decision_date.eq('2026-10-03')].copy()
        current.to_csv(OUT/'current_rankings.csv.gz',index=False)
        base.save('source_receipt.json',dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),protocol_sha256=hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),trained=False,fresh_holdout=False))
        base.save('candidate_weights.json',{name:dict(factor_core=w,per_factor=w/5,champion=1-w) for name,w in SHARES.items()})
        print('SCORED separate four-candidate curve; no fitting',flush=True)
    elif a.stage=='evaluate':base.evaluate()
    else:base.portfolio()


if __name__=='__main__':main()
