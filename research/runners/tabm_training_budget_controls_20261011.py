"""Matched original checkpoints for each development-selected continuation."""
import json
import re
import pandas as pd
import sector_tabm_continuation_20261011 as n


def main():
    out=n.OUT/'matched_12epoch_controls';out.mkdir(exist_ok=True)
    names=json.loads((n.OUT/'locked_finalists.json').read_text())['finalists']
    mapping={name:re.sub(r'_e(?:24|48)_','_',name) for name in names}
    originals=list(dict.fromkeys(mapping.values()))
    x=n.s.h.load()
    new=pd.concat([pd.read_csv(n.OUT/f'predictions_{year}.csv.gz',usecols=n.s.p.KEYS+names) for year in range(2020,2026)],ignore_index=True)
    old=pd.concat([pd.read_csv(n.s.OUT/f'combined_{year}.csv.gz',usecols=n.s.p.KEYS+originals) for year in range(2020,2026)],ignore_index=True)
    x=x.merge(new,on=n.s.p.KEYS,validate='one_to_one').merge(old,on=n.s.p.KEYS,validate='one_to_one')
    assert len(x)==797443
    summaries=[]
    for scope in ['common','expanded']:
        z=x[x.sector_incumbent.notna()].copy() if scope=='common' else x.copy()
        for cap in [False,True]:
            path=out/f'queries_{scope}_{cap}.csv.gz'
            if path.exists():
                q=pd.read_csv(path)
            else:
                zz=z.copy()
                if cap:
                    zz.future_xirr=zz.future_xirr.clip(-1,1)
                q=n.s.p.metrics(zz,names+originals,top_ns=(1,3,5));q.to_csv(path,index=False)
            assert set(q.model)==set(names+originals)
            a=q.groupby(['model','period','profile','top_n','sector'])[n.s.p.METRICS].mean().groupby(['model','period','profile','top_n']).mean().reset_index()
            a['scope']=scope;a['return_treatment']='capped' if cap else 'raw';summaries.append(a)
            print('MATCHED CONTROL',scope,cap,flush=True)
    summary=pd.concat(summaries);summary.to_csv(out/'summary.csv',index=False)
    index=summary.set_index(['model','period','profile','top_n','scope','return_treatment'])[n.s.p.METRICS]
    differences=[];trials=[]
    for name,original in mapping.items():
        d=index.loc[name]-index.loc[original];d.shortfall=-d.shortfall
        d=d.reset_index();d['model']=name;d['original_12epoch_control']=original;differences.append(d)
        values=d[n.s.p.METRICS].to_numpy()
        trials.append(dict(model=name,original=original,improved=int((values>1e-12).sum()),regressed=int((values< -1e-12).sum()),ties=int((abs(values)<=1e-12).sum())))
    pd.concat(differences).to_csv(out/'oriented_differences.csv',index=False)
    pd.DataFrame(trials).to_csv(out/'trials.csv',index=False)
    (out/'verification.json').write_text(json.dumps(dict(rows=len(x),mapping=mapping,selection_changed=False,fresh_validation=False,
        qualification='Same source checkpoint, features, training rows, target heads, and blend weights. Continuation also changes learning rate, batch size, gradient clipping, optimizer state, device and PyTorch version; the comparison measures the continuation recipe, not an isolated causal epoch effect.'),indent=2),encoding='utf-8')
    print(pd.DataFrame(trials).to_string(index=False),flush=True)


if __name__=='__main__':
    main()
