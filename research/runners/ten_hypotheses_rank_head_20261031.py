"""Feature ablations inside the existing price ranking head; fixed champion mix."""
import argparse,json
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
import ten_hypotheses_20261031 as c
ROOT,BASE=c.ROOT,c.OUT

def run(kronos=False):
    out=BASE/('kronos_rank_head' if kronos else 'rank_head_round');out.mkdir(exist_ok=True)
    def save(name,obj):(out/name).write_text(json.dumps(obj,indent=2,default=str))
    save('protocol.json',dict(scope='Modify only the existing 25% price head; retain all other active champion scores/overlays.',features='Same fixed volume, peers and analog families; Kronos matched sample separate.',training='Original 180-tree rank_xendcg_balanced recipe; annual strictly mature outcomes; no new parameter search.',selection='Highest development equal-date rank IC; name tie break. Lock before exposed scoring. Goal attainment and drawdown also reported.',fresh_validation=False,website_changed=False,kronos_temporal_contamination_risk=kronos))
    x=pd.read_pickle(BASE/'panel.pkl.gz',compression='gzip')
    for name in ['isin','profile_name','sector','period']:x[name]=x[name].astype(str)
    if kronos:
        index=pd.read_csv(BASE/'kronos_input_keys.csv');index['embedding_row']=np.arange(len(index))
        embedding=np.load(BASE/'kronos_embeddings.npy');x=x.merge(index,on=['isin','decision_date'],validate='many_to_one')
        families={'matched_head':list(c.old.COLS),'kronos_head':list(c.old.COLS)+[f'kronos_pca{j}' for j in range(16)]}
    else:
        x=x.merge(pd.read_pickle(BASE/'extra_features.pkl.gz',compression='gzip'),on=['isin','decision_date'],how='left',validate='many_to_one')
        x=x.merge(pd.read_pickle(BASE/'analog_features.pkl.gz',compression='gzip'),on=c.KEYS,how='left',validate='one_to_one')
        original=list(c.old.COLS)
        families={'head_control':original,'head_volume':original+c.VOL,'head_peers':original+c.PEER,'head_analogs':original+c.ANALOG,'head_combined':original+c.VOL+c.PEER+c.ANALOG}
    predictions=[];audit=[]
    for year in range(2020,2026):
        cutoff=f'{year}-01-01';train=x[x.endpoint.lt(cutoff)].copy();test=x[x.decision_date.str.startswith(str(year))].copy()
        eligible=train.dropna(subset=['future_xirr','future_drawdown','future_shortfall'])
        eligible=eligible[eligible.evidence_fraction.gt(0)&eligible.sector.ne('Unclassified')]
        eligible=eligible[eligible.groupby(c.GROUP)['isin'].transform('size').ge(5)]
        if kronos:
            unique=np.unique(train.embedding_row);pca=PCA(n_components=16,random_state=c.SEED).fit(embedding[unique]);cols=[f'kronos_pca{j}' for j in range(16)]
            for g in [train,test]:g[cols]=pca.transform(embedding[g.embedding_row])
        for name,cols in families.items():
            file=out/f'{name}_{year}.csv.gz'
            if file.exists():
                test[name]=pd.read_csv(file)[name].to_numpy()
                error=float(np.max(np.abs(test[name]-test[c.ANCHOR]))) if name=='head_control' else None
                if error is not None:assert error<1e-12
                audit.append(dict(year=year,model=name,max_training_endpoint=eligible.endpoint.max(),training_rows=len(eligible),features=len(cols),control_replay_error=error))
                continue
            prior=c.old.COLS;c.old.COLS=cols
            try:
                model,t=c.old.fit(train,dict(loss='rank_xendcg',target='balanced'))
                raw=pd.Series(model.predict(test[cols]),index=test.index)
            finally:c.old.COLS=prior
            percentile=raw.groupby([test[k] for k in c.GROUP]).rank(pct=True).where(test.evidence_fraction.gt(0),.5)
            error=float(np.max(np.abs(percentile-test.rank_xendcg_balanced)))
            if name=='head_control':assert error<1e-12,error
            test[name]=(test[c.ANCHOR]+.25*(percentile-test.rank_xendcg_balanced)).where(test.evidence_fraction.gt(0),test[c.ANCHOR])
            model.booster_.save_model(str(out/f'{name}_{year}.txt'));test[c.KEYS+[name]].to_csv(file,index=False)
            audit.append(dict(year=year,model=name,max_training_endpoint=t.endpoint.max(),training_rows=len(t),features=len(cols),control_replay_error=error if name=='head_control' else None))
            print('RANK HEAD',name,year,len(t),flush=True)
        predictions.append(test[c.KEYS+['sector','evidence_fraction','goal_hit','future_xirr','future_drawdown','future_shortfall',c.ANCHOR]+list(families)])
    z=c.valid(pd.concat(predictions,ignore_index=True));models=list(families);baseline='matched_head' if kronos else c.ANCHOR
    dev=c.metrics(z[z.decision_date.lt('2024-01-01')],[c.ANCHOR]+models)
    stats=dev.groupby(['model','decision_date']).rank_ic.mean().groupby('model').mean()
    competitors=[n for n in models if n not in ['head_control','matched_head']];chosen=stats.loc[sorted(competitors)].idxmax()
    save('development_lock.json',dict(selected=chosen,development_ic=stats.to_dict(),baseline=baseline))
    recent=c.metrics(z[z.decision_date.ge('2024-01-01')],[c.ANCHOR]+models)
    q=pd.concat([dev,recent]);q.to_csv(out/'queries.csv.gz',index=False)
    summary=q.assign(period=np.where(q.decision_date.lt('2024-01-01'),'development','exposed')).groupby(['period','model','decision_date'])[['rank_ic','achievement','xirr','drawdown']].mean().groupby(['period','model']).mean().reset_index();summary['selected']=summary.model.eq(chosen);summary.to_csv(out/'summary.csv',index=False)
    pd.DataFrame(audit).to_csv(out/'training_audit.csv',index=False)
    floors=[]
    d=dev.pivot(index=c.GROUP,columns='model',values='rank_ic').dropna();d=d[competitors].subtract(d[baseline],axis=0).groupby('decision_date').mean()
    for span in [365,730]:
        result=c.block_floor(d.to_numpy(),d.index,span);result['observed_best_delta']=float(d.mean().max());floors.append(result)
    pd.DataFrame(floors).to_csv(out/'selection_noise_floor.csv',index=False)
    print('RANK SUMMARY',summary.to_dict('records'),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--kronos',action='store_true');args=a.parse_args();run(args.kronos)
