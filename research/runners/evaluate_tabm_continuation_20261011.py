"""Fixed chronological evaluation for the registered neural continuation."""
import json
import sys
import numpy as np
import pandas as pd
import sector_tabm_continuation_20261011 as n


def main(stage):
    p=n.s.p;out=n.OUT;anchor=n.s.h.ANCHOR
    development=stage=='development'
    names=n.NAMES if development else json.loads((out/'locked_finalists.json').read_text())['finalists']
    years=[2020,2021,2022,2023] if development else [2024,2025]
    frame=n.s.h.load();frame=frame[frame.decision_date.str[:4].astype(int).isin(years)]
    predictions=pd.concat([pd.read_csv(out/f'predictions_{year}.csv.gz',usecols=p.KEYS+names) for year in years],ignore_index=True)
    frame=frame.merge(predictions,on=p.KEYS,validate='one_to_one')
    summaries=[]
    for start in range(0,len(names),12):
        batch=names[start:start+12]
        for scope in ['common','expanded']:
            z=frame[frame.sector_incumbent.notna()].copy() if scope=='common' else frame.copy()
            for cap in [False,True]:
                path=out/f'queries_{stage}_{scope}_{cap}_{start}.csv.gz'
                if path.exists():
                    q=pd.read_csv(path)
                else:
                    subset=z.copy()
                    if cap:
                        subset.future_xirr=subset.future_xirr.clip(-1,1)
                    q=p.metrics(subset,[anchor]+batch,top_ns=(1,3,5))
                    q.to_csv(path,index=False)
                assert set(q.model)==set([anchor]+batch)
                aggregated=q.groupby(['model','period','profile','top_n','sector'])[p.METRICS].mean().groupby(['model','period','profile','top_n']).mean().reset_index()
                aggregated['scope']=scope;aggregated['return_treatment']='capped' if cap else 'raw'
                summaries.append(aggregated)
                print('EVALUATED',stage,start,scope,cap,flush=True)
    summary=pd.concat(summaries).drop_duplicates(['model','period','profile','top_n','scope','return_treatment'])
    summary.to_csv(out/f'summary_{stage}.csv',index=False)
    indexed=summary.set_index(['model','period','profile','top_n','scope','return_treatment'])[p.METRICS]
    records=[]
    for name in names:
        d=(indexed.loc[name]-indexed.loc[anchor]).reset_index();d.shortfall=-d.shortfall
        nonreturn=[metric for metric in p.METRICS if metric!='xirr']
        values=d[p.METRICS].to_numpy()
        records.append(dict(model=name,rank_ic=float(summary[summary.model.eq(name)&summary.scope.eq('expanded')&summary.return_treatment.eq('raw')&summary.top_n.eq(3)].rank_ic.mean()),
            improved=int((values>1e-12).sum()),regressed=int((values< -1e-12).sum()),
            nonreturn_regressions=int((d[nonreturn].to_numpy()< -1e-12).sum()),
            top3_nonreturn_regressions=int((d[d.top_n.eq(3)][nonreturn].to_numpy()< -1e-12).sum())))
    trials=pd.DataFrame(records);trials.to_csv(out/f'trials_{stage}.csv',index=False)
    if development:
        ordered=trials.sort_values(['rank_ic','nonreturn_regressions','model'],ascending=[False,True,True])
        chosen=[]
        for family in n.FAMILIES:
            for epoch in n.CHECKPOINTS:
                chosen.append(ordered[ordered.model.str.startswith(f'{family}_e{epoch}_')].iloc[0].model)
        conservative=trials.sort_values(['top3_nonreturn_regressions','nonreturn_regressions','model']).iloc[0].model
        n.write('locked_finalists.json',dict(finalists=list(dict.fromkeys(chosen+[conservative])),conservative=conservative,development_sha256=n.s.digest(out/'trials_development.csv'),selection_mean_xirr_weight=0))
    print(trials.sort_values('rank_ic',ascending=False).to_string(index=False),flush=True)


if __name__=='__main__':
    assert sys.argv[1] in ['development','recent']
    main(sys.argv[1])
