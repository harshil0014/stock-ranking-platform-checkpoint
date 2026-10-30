"""Dated OHLCV, correlation peers, historical analogs and path diagnostics."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','3')
from pathlib import Path
import argparse,json,gc,hashlib
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import SplineTransformer
from sklearn.linear_model import LinearRegression
from scipy.optimize import brentq
from scipy.spatial import cKDTree
from threadpoolctl import threadpool_limits
import ten_hypotheses_20261031 as core
ROOT,OUT=core.ROOT,core.OUT
CACHE=ROOT/'experiments/current-data-recovery-20261003/yahoo-full-recovery-v1'

def build():
    core.protocol()
    if (OUT/'ohlcv_build_complete.json').exists():return
    f=pd.read_pickle(core.old.OUT/'price_features.pkl.gz',compression='gzip').reset_index(drop=True)
    count=len(f);paths=np.full((count,64),np.nan,dtype='float32');rets=np.full((count,380),np.nan,dtype='float32')
    for c in core.VOL:f[c]=np.nan
    m=pd.read_csv(CACHE/'yahoo_symbol_map.csv').dropna(subset=['yahoo_symbol'])
    mapping=m.groupby('yahoo_symbol').isin.apply(list).to_dict()
    byisin={isin:g.index.to_numpy() for isin,g in f.groupby('isin')}
    sampled=set(sorted(byisin,key=lambda s:hashlib.sha256(s.encode()).hexdigest())[:512])
    krows=[];kdata=[];future=[];source=[];seen=set();errors=[]
    # Forward path is explanatory ONLY; never merged into model feature tables.
    for batch in sorted((CACHE/'history-cache').glob('batch_*.pkl')):
        obj=pd.read_pickle(batch)
        for symbol,h in obj['frames'].items():
            if symbol not in mapping or symbol in seen:continue
            seen.add(symbol)
            h=h.copy();h.columns=[str(c) for c in h.columns]
            h=h.dropna(subset=['Close']);h=h[h.Close.gt(0)].sort_index();h=h[~h.index.duplicated()]
            if h.empty:continue
            ds=pd.to_datetime(h.index).tz_localize(None).to_numpy(dtype='datetime64[D]');close=h.Close.to_numpy(float);volume=h.Volume.fillna(0).to_numpy(float)
            oh=h[['Open','High','Low','Close','Volume']].to_numpy(float)
            for isin in mapping[symbol]:
                if isin not in byisin:continue
                for row in byisin[isin]:
                    day=np.datetime64(f.at[row,'decision_date'],'D');end=int(np.searchsorted(ds,day,side='right'))
                    if end<253 or f.at[row,'evidence_fraction']<=0:continue
                    if int((day-ds[end-1]).astype(int))>14:continue
                    prices=close[end-252:end];vol=volume[end-252:end]
                    expected=f.at[row,'return252'];actual=close[end-1]/close[end-253]-1
                    if np.isfinite(expected) and abs(expected-actual)>max(.005,.005*abs(expected)):
                        errors.append(dict(isin=isin,decision_date=str(day),saved_return252=float(expected),recovered_return252=float(actual)));continue
                    f.at[row,'abnormal_volume21']=np.mean(vol[-21:])/max(np.mean(vol),1)
                    f.at[row,'abnormal_volume5']=np.mean(vol[-5:])/max(np.mean(vol),1)
                    f.at[row,'high_volume_interaction']=f.at[row,'abnormal_volume5']*(prices[-1]/prices.max())**10
                    f.at[row,'volume_trend']=np.mean(vol[-21:])/max(np.mean(vol[-63:-21]),1)
                    f.at[row,'volume_zero_fraction']=np.mean(vol<=0)
                    f.at[row,'log_dollar_volume']=np.log1p(np.median(prices*vol))
                    curve=np.log(prices/prices[0]);paths[row]=np.interp(np.linspace(0,251,64),np.arange(252),curve)
                    dr=np.diff(np.log(close[end-253:end]));rd=ds[end-252:end];positions=(rd-(day-np.timedelta64(379,'D'))).astype(int)
                    ok=(positions>=0)&(positions<380);rets[row,positions[ok]]=dr[ok]
                    if isin in sampled:
                        candle=oh[end-252:end].copy();amount=candle[:,3]*candle[:,4];candle=np.column_stack([candle,amount])
                        if np.isfinite(candle).all() and (candle[:,:4]>0).all():
                            # Kronos predictor's per-window feature normalization.
                            candle=np.clip((candle-candle.mean(0))/(candle.std(0)+1e-5),-5,5).astype('float32')
                            krows.append(dict(isin=isin,decision_date=str(day)));kdata.append(candle)
                    endpoint=day+np.timedelta64(365,'D');finish=int(np.searchsorted(ds,endpoint,side='right'))
                    if finish>end+180 and finish<len(ds)+1 and abs(int((endpoint-ds[finish-1]).astype(int)))<=7:
                        pp=close[end-1:finish];dd=ds[end-1:finish];logr=np.diff(np.log(pp));high=np.maximum.accumulate(pp);under=pp/high<.999999
                        # Recovery duration: largest elapsed observations below running high.
                        runs=[];run=0
                        for b in under:run=run+1 if b else 0;runs.append(run)
                        schedule=day+np.arange(12)*np.timedelta64(30,'D');buy=np.searchsorted(ds,schedule,side='left')
                        if (buy<finish).all() and ((ds[buy]-schedule).astype(int)<=7).all():
                            terminal=close[finish-1]*np.sum(1/close[buy]);years=(ds[finish-1]-schedule).astype(float)/365.25
                            try:irr=brentq(lambda r:np.sum((1+r)**years)-terminal,-.9999,100)
                            except ValueError:irr=np.nan
                            future.append(dict(isin=isin,decision_date=str(day),endpoint=str(ds[finish-1]),lump_return=pp[-1]/pp[0]-1,forward_vol=float(np.std(logr)*np.sqrt(252)),time_underwater=float(under.mean()),max_recovery_duration=max(runs)/252,fractional_sip_xirr=irr))
        source.append(dict(file=batch.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(batch.read_bytes()).hexdigest()))
        print('OHLCV',batch.name,len(seen),'windows',int(np.isfinite(paths[:,0]).sum()),flush=True)
    np.save(OUT/'paths64.npy',paths);np.save(OUT/'returns380.npy',rets)
    np.save(OUT/'kronos_inputs.npy',np.stack(kdata));pd.DataFrame(krows).to_csv(OUT/'kronos_input_keys.csv',index=False)
    f[['isin','decision_date']+core.VOL].to_pickle(OUT/'volume_features.pkl.gz',compression='gzip')
    f[['isin','decision_date','sector','return21','return63','evidence_fraction']].to_pickle(OUT/'window_index.pkl.gz',compression='gzip')
    pd.DataFrame(future).to_pickle(OUT/'forward_path_diagnostic.pkl.gz',compression='gzip')
    pd.DataFrame(errors).to_csv(OUT/'price_basis_disagreements.csv',index=False)
    core.save('ohlcv_build_complete.json',dict(windows=int(np.isfinite(paths[:,0]).sum()),total_stock_dates=count,kronos_windows=len(krows),sampled_stocks=len(sampled),price_basis_disagreements=len(errors),sources=source))

def peers():
    f=pd.read_pickle(OUT/'window_index.pkl.gz',compression='gzip');ret=np.load(OUT/'returns380.npy',mmap_mode='r');rows=[]
    for day,g in f.groupby('decision_date',sort=True):
        dest=OUT/f'peers_{day}.csv.gz'
        if dest.exists():continue
        ids=g.index.to_numpy();r=np.array(ret[ids]);ok=np.isfinite(r).sum(axis=1)>=200;ids=ids[ok];r=r[ok];g=f.loc[ids].copy()
        if len(g)<26:continue
        with threadpool_limits(limits=3):
            mask=np.isfinite(r).astype('float32');v=np.nan_to_num(r);n=mask@mask.T;s=v@mask.T;ss=(v*v)@mask.T;cross=v@v.T
            variance=np.maximum(ss-s*s/np.maximum(n,1),0);den=np.sqrt(variance*variance.T)
            corr=np.divide(cross-s*s.T/np.maximum(n,1),den,out=np.full_like(cross,-np.inf),where=den>1e-12)
            corr[n<200]=-np.inf;np.fill_diagonal(corr,-np.inf)
            best=np.argpartition(-corr,24,axis=1)[:,:25];values=np.take_along_axis(corr,best,axis=1)
            enough=np.isfinite(values).all(axis=1);v21=g.return21.to_numpy();v63=g.return63.to_numpy()
            g['corr_peer_return21']=np.nanmean(v21[best],axis=1);g['corr_peer_return63']=np.nanmean(v63[best],axis=1)
            g['corr_peer_lag']=g.corr_peer_return21-g.return21;g['corr_peer_correlation']=values.mean(axis=1)
            g.loc[~enough,core.PEER]=np.nan
        g[['isin','decision_date']+core.PEER].to_csv(dest,index=False)
        print('PEERS',day,len(g),flush=True)
    p=pd.concat([pd.read_csv(file) for file in sorted(OUT.glob('peers_*.csv.gz'))],ignore_index=True)
    extra=pd.read_pickle(OUT/'volume_features.pkl.gz',compression='gzip').merge(p,on=['isin','decision_date'],how='left',validate='one_to_one');extra.to_pickle(OUT/'extra_features.pkl.gz',compression='gzip')
    core.save('peer_coverage.json',dict(stock_dates_with_peers=int(extra.corr_peer_lag.notna().sum()),unclassified_with_peers=int(f.merge(p,on=['isin','decision_date']).sector.eq('Unclassified').sum()),neighbors=25,alignment='Calendar-aligned observed daily returns; pairwise-complete Pearson with >=200 common observations'))

def analogs():
    x=pd.read_pickle(OUT/'panel.pkl.gz',compression='gzip');f=pd.read_pickle(OUT/'window_index.pkl.gz',compression='gzip');paths=np.load(OUT/'paths64.npy');good=np.isfinite(paths).all(axis=1)
    # Zero mean/unit variance describes shape while retaining an explicit distance.
    paths=(paths-paths.mean(axis=1,keepdims=True))/(paths.std(axis=1,keepdims=True)+1e-6)
    f['path_row']=np.arange(len(f));keys=['isin','decision_date']
    labels=x[core.KEYS+['endpoint','future_xirr','goal_hit']].merge(f[keys+['path_row']],on=keys,validate='many_to_one')
    out=[];audit=[]
    for year in range(2018,2026):
        cutoff=f'{year}-01-01';lib=labels[labels.endpoint.lt(cutoff)&labels.future_xirr.notna()].copy();lib=lib[good[lib.path_row.to_numpy()]]
        target=labels[labels.decision_date.str.startswith(str(year))].copy();target=target[good[target.path_row.to_numpy()]]
        if lib.empty or target.empty:continue
        lr=np.sort(lib.path_row.unique());tr=np.sort(target.path_row.unique());pca=PCA(n_components=8,random_state=core.SEED).fit(paths[lr])
        a=pca.transform(paths[lr]);b=pca.transform(paths[tr]);a/=np.linalg.norm(a,axis=1,keepdims=True)+1e-8;b/=np.linalg.norm(b,axis=1,keepdims=True)+1e-8
        # Euclidean neighbors on unit vectors are exactly cosine neighbors;
        # the KD tree avoids a huge query-by-library distance matrix.
        tree=cKDTree(a)
        dist,neighbors=tree.query(b,k=min(200,len(a)),workers=3)
        dist=dist**2/2
        look={r:(neighbors[i],dist[i]) for i,r in enumerate(tr)}
        library_isins=f.iloc[lr]['isin'].to_numpy()
        for profile,z in target.groupby('profile_name',observed=True):
            l=lib[lib.profile_name.eq(profile)].drop_duplicates('path_row').set_index('path_row');y=l.future_xirr.reindex(lr).to_numpy();hit=l.goal_hit.reindex(lr).to_numpy(dtype=float)
            for r in z.itertuples(index=False):
                nn,dd=look[r.path_row];valid=np.isfinite(y[nn])&(library_isins[nn]!=r.isin);nn=nn[valid][:50];dd=dd[valid][:50]
                if len(nn)<50:continue
                out.append(dict(isin=r.isin,decision_date=r.decision_date,profile_name=profile,analog_xirr=float(np.mean(np.clip(y[nn],-1,3))),analog_attainment=float(np.mean(hit[nn])),analog_dispersion=float(np.std(np.clip(y[nn],-1,3))),analog_distance=float(dd.mean())))
        audit.append(dict(year=year,max_library_endpoint=lib.endpoint.max(),library_windows=len(lr),test_windows=len(tr),pca_variance=float(pca.explained_variance_ratio_.sum())))
        print('ANALOGS',year,len(out),flush=True)
    pd.DataFrame(out).to_pickle(OUT/'analog_features.pkl.gz',compression='gzip');pd.DataFrame(audit).to_csv(OUT/'analog_maturity_audit.csv',index=False)

def path():
    a=pd.read_pickle(OUT/'forward_path_diagnostic.pkl.gz',compression='gzip')
    x=pd.read_pickle(OUT/'panel.pkl.gz',compression='gzip');x=x[x.profile_name.eq('base7500')][['isin','decision_date','sector','future_xirr']]
    a=a.merge(x,on=['isin','decision_date'],how='inner',validate='one_to_one').dropna();a=a[a.decision_date.ge('2020-01-01')&a.decision_date.lt('2026-01-01')]
    a['period']=np.where(a.decision_date.lt('2024-01-01'),'development','exposed');rows=[]
    fields=['forward_vol','time_underwater','max_recovery_duration']
    for period,g in a.groupby('period'):
        # Controls learned without cross-period pooling. Forward-path terms are NOT predictors.
        control=SplineTransformer(n_knots=8,degree=3).fit_transform(g[['lump_return']].clip(-1,5))
        fixed=pd.get_dummies(g[['sector','decision_date']].astype(str),drop_first=True).to_numpy(float);control=np.column_stack([control,fixed])
        xp=g[fields].to_numpy();xp=(xp-xp.mean(0))/xp.std(0)
        # Frisch-Waugh-Lovell residualization provides transparent partial coefficients.
        rx=xp-LinearRegression().fit(control,xp).predict(control)
        for outcome in ['fractional_sip_xirr','future_xirr']:
            y=g[outcome].clip(-1,3).to_numpy();ry=y-LinearRegression().fit(control,y).predict(control);coef=np.linalg.lstsq(rx,ry,rcond=None)[0]
            # Cluster wild bootstrap signs on whole calendar years, preserving overlapping windows.
            fit=rx@coef;resid=ry-fit;years=pd.to_datetime(g.decision_date).dt.year.to_numpy();unique=np.unique(years);rng=np.random.default_rng(core.SEED);draw=[]
            inverse=np.linalg.pinv(rx)
            for _ in range(1000):
                signs=dict(zip(unique,rng.choice([-1,1],len(unique))));draw.append(inverse@(fit+resid*np.array([signs[y] for y in years])))
            for j,field in enumerate(fields):
                rows.append(dict(period=period,outcome=outcome,feature=field,coefficient_per_sd=coef[j],ci025=np.quantile(np.array(draw)[:,j],.025),ci975=np.quantile(np.array(draw)[:,j],.975),rows=len(g),year_clusters=len(unique)))
    pd.DataFrame(rows).to_csv(OUT/'path_regression.csv',index=False);a.to_csv(OUT/'path_diagnostic_rows.csv.gz',index=False)
    print('PATH',rows,flush=True)

def current_analogs():
    """Explainable examples at the frozen Oct3 snapshot, not a live ranking."""
    x=pd.read_pickle(OUT/'panel.pkl.gz',compression='gzip');f=pd.read_pickle(OUT/'window_index.pkl.gz',compression='gzip');paths=np.load(OUT/'paths64.npy')
    good=np.isfinite(paths).all(1);paths=(paths-paths.mean(1,keepdims=True))/(paths.std(1,keepdims=True)+1e-6)
    f['path_row']=np.arange(len(f));lib=x[x.profile_name.eq('base7500')&x.endpoint.lt('2026-10-03')&x.future_xirr.notna()][['isin','decision_date','endpoint','future_xirr','goal_hit']].merge(f[['isin','decision_date','path_row']],on=['isin','decision_date'],validate='one_to_one')
    lib=lib[good[lib.path_row.to_numpy()]].reset_index(drop=True)
    target=f[f.decision_date.eq('2026-10-03')&good].copy();target=target.sort_values('isin').head(5)
    pca=PCA(n_components=8,random_state=core.SEED).fit(paths[lib.path_row]);a=pca.transform(paths[lib.path_row]);b=pca.transform(paths[target.path_row]);a/=np.linalg.norm(a,axis=1,keepdims=True)+1e-8;b/=np.linalg.norm(b,axis=1,keepdims=True)+1e-8
    dist,indices=cKDTree(a).query(b,k=200,workers=3);out=[]
    for j,row in enumerate(target.itertuples(index=False)):
        keep=[(int(i),float(d*d/2)) for i,d in zip(indices[j],dist[j]) if lib.iloc[int(i)]['isin']!=row.isin][:50]
        for rank,(i,d) in enumerate(keep,1):
            n=lib.iloc[i];out.append(dict(query_isin=row.isin,query_snapshot=row.decision_date,neighbor_rank=rank,neighbor_isin=n['isin'],neighbor_date=n.decision_date,outcome_endpoint=n.endpoint,cosine_distance=d,realized_forward_sip_xirr=n.future_xirr,goal_hit=n.goal_hit))
    examples=pd.DataFrame(out)
    identities=pd.read_csv(core.old.OUT/'current_all_stock_rankings.csv',usecols=['isin','ticker','company'])
    examples=examples.merge(identities.rename(columns={'isin':'query_isin','ticker':'query_ticker','company':'query_company'}),on='query_isin',validate='many_to_one')
    examples=examples.merge(identities.rename(columns={'isin':'neighbor_isin','ticker':'neighbor_ticker','company':'neighbor_company'}),on='neighbor_isin',validate='many_to_one')
    examples.to_csv(OUT/'current_analog_examples.csv',index=False)
    print('CURRENT ANALOG EXAMPLES',len(out),'latest_library_endpoint',lib.endpoint.max(),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('stage',choices=['build','peers','analogs','path','current_analogs']);args=a.parse_args();globals()[args.stage]()
