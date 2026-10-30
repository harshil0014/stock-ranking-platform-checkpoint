"""Small feature improvements to the champion's existing 25% ranking component."""
import json
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
import sector_price_rebuild_20261010 as p
from sector_learned_blend_20261010 import load as load_reference, ANCHOR

OUT = p.ROOT / 'experiments/champion-peer-context-20261017'
FIELDS = ['momentum12_1', 'high_gap252', 'near_high_fraction', 'downside252', 'drawdown252']
STRENGTH = ['peer_z_' + c for c in FIELDS[:3]]
RISK = ['peer_z_' + c for c in FIELDS[3:]]
CONFIGS = {'peer_strength': STRENGTH, 'peer_risk': RISK, 'peer_both': STRENGTH + RISK}
BASE_COLS = list(p.COLS)

def peer_features(x):
    """Same-date, valid, distinct-company leave-one-out standardized deviations."""
    keys = ['decision_date', 'isin']
    selected = keys + ['sector', 'evidence_fraction'] + FIELDS
    # A profile must never change the price evidence of a company.
    assert x.groupby(keys)[FIELDS + ['evidence_fraction']].nunique(dropna=False).max().max() <= 1
    u = x[selected].drop_duplicates(keys).copy()
    group = [u.decision_date, u.sector]
    for col in FIELDS:
        value = u[col].where(u.evidence_fraction.gt(0) & u.sector.ne('Unclassified'))
        count = value.groupby(group).transform('count') - value.notna().astype(int)
        total = value.groupby(group).transform('sum') - value.fillna(0)
        squares = value.pow(2).groupby(group).transform('sum') - value.fillna(0).pow(2)
        mean = total / count.where(count > 0)
        var = (squares / count.where(count > 0) - mean.pow(2)).clip(lower=0)
        score = ((value - mean) / np.sqrt(var).where(var > 1e-12)).clip(-5, 5)
        u['peer_z_' + col] = score.where(count.ge(4)).astype('float32')
    return x.merge(u[keys + STRENGTH + RISK], on=keys, how='left', validate='many_to_one')

def write(name, obj):
    (OUT/name).write_text(json.dumps(obj, indent=2), encoding='utf-8')

def protocol():
    OUT.mkdir(parents=True, exist_ok=True)
    doc = dict(scope='Improve existing rank_xendcg component; all inherited components and .75/.25 blend fixed',
        configs=CONFIGS, feature_definition='Leave-one-out sector/date standardized deviation, >=4 valid other companies, clipped +/-5; constant peers/missing evidence => NaN',
        selection='Development 2020-23: minimize Top3 non-XIRR metric regressions, then all non-XIRR regressions, then maximize expanded capped rankIC; deterministic name tie break. Lock one patch before recent evaluation.',
        promotion='Both development and recent: no non-XIRR metric/profile/scope/top-k cell regresses beyond 1e-12, at least one improves; XIRR no selection weight but report all return regressions as additional veto.',
        training='Existing 180-tree balanced rank_xendcg hyperparameters and exact mature-label filters; annual endpoint < January1, current endpoint < October3 2026',
        coverage='Same champion fallback score exactly where evidence_fraction <=0; no new data coverage claims',
        sources=['https://arxiv.org/abs/2106.10159','https://arxiv.org/abs/2110.13716'],
        adaptation='Simple peer-statistics features inspired by relationship research; no graph network, imported weights, or claimed paper reproduction',
        fresh_validation=False, website_changed=False)
    file=OUT/'protocol.json'
    if file.exists(): assert json.loads(file.read_text()) == doc
    else: write('protocol.json',doc)

def fit(x, cutoff, name, year):
    cols=BASE_COLS+CONFIGS[name]
    previous=p.COLS
    try:
        p.COLS=cols
        model,t=p.fit(x[x.endpoint.lt(cutoff)],dict(loss='rank_xendcg',target='balanced'))
    finally: p.COLS=previous
    assert t.endpoint.max()<cutoff
    path=OUT/f'{name}_{year}.txt'; model.booster_.save_model(str(path))
    write(f'{name}_{year}_audit.json',dict(cutoff=cutoff,max_training_endpoint=t.endpoint.max(),training_rows=len(t),features=cols,model_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return model, cols

def infer(model, z, cols):
    raw=pd.Series(model.predict(z[cols]),index=z.index)
    rank=raw.groupby([z.decision_date,z.profile_name,z.sector]).rank(pct=True).where(z.evidence_fraction.gt(0),.5)
    # Change only the existing R component; preserve exact missing-evidence fallback.
    return (.75*z.guarded_previous+.25*rank).where(z.evidence_fraction.gt(0),z[ANCHOR])

def learn_year(x, ref, year, names):
    dest=OUT/f'predictions_{year}.csv.gz'
    if dest.exists(): return
    if year=='current':
        z=pd.read_csv(p.OUT/'current_all_stock_rankings.csv')
        z[ANCHOR]=z.rebuilt_score; z['guarded_previous']=z.guarded_model_score
        z=peer_features(z); cutoff=p.ASOF
    else:
        z=x[x.decision_date.str.startswith(str(year))].copy()
        z=z.merge(ref[p.KEYS+[ANCHOR,'guarded_previous']],on=p.KEYS,validate='one_to_one')
        cutoff=f'{year}-01-01'
    for name in names:
        m,cols=fit(x,cutoff,name,year); z[name]=infer(m,z,cols)
        replay=infer(lgb.Booster(model_file=str(OUT/f'{name}_{year}.txt')),z,cols)
        np.testing.assert_allclose(z[name],replay,atol=0,rtol=0)
        assert np.isfinite(z[name]).all()
        np.testing.assert_array_equal(z.loc[z.evidence_fraction.le(0),name],z.loc[z.evidence_fraction.le(0),ANCHOR])
        print('FIT',year,name,len(z),flush=True)
    if year=='current':
        assert len(z)==4436 and z['isin'].is_unique
        for name in [ANCHOR]+names:z[name+'_sector_rank']=z[name].groupby(z.sector).rank(method='min',ascending=False)
        z['rank_change']=z[ANCHOR+'_sector_rank']-z[names[0]+'_sector_rank']
        z.to_csv(OUT/'current_all_4436_patch_audit.csv',index=False)
    z[p.KEYS+['sector',ANCHOR]+names].to_csv(dest,index=False)

def evaluate(ref, stage, names):
    years=range(2020,2024) if stage=='development' else range(2024,2026)
    scores=pd.concat([pd.read_csv(OUT/f'predictions_{y}.csv.gz') for y in years],ignore_index=True)
    z=ref.merge(scores[p.KEYS+names],on=p.KEYS,validate='one_to_one')
    summaries=[]
    for scope in ['common','expanded']:
        base=z[z.sector_incumbent.notna()].copy() if scope=='common' else z.copy()
        for treatment in ['raw','capped']:
            zz=base.copy()
            if treatment=='capped': zz.future_xirr=zz.future_xirr.clip(-1,1)
            q=p.metrics(zz,[ANCHOR]+names,top_ns=(1,3,5))
            q.to_csv(OUT/f'queries_{stage}_{scope}_{treatment}.csv.gz',index=False)
            s=q.groupby(['model','period','profile','top_n','sector'])[p.METRICS].mean().groupby(['model','period','profile','top_n']).mean().reset_index()
            s['scope']=scope;s['return_treatment']=treatment;summaries.append(s)
            print('METRICS',stage,scope,treatment,flush=True)
    s=pd.concat(summaries); s.to_csv(OUT/f'summary_{stage}.csv',index=False)
    a=s.set_index(['model','period','profile','top_n','scope','return_treatment'])[p.METRICS]
    trials=[]; deltas=[]; nonreturn=[c for c in p.METRICS if c!='xirr']
    for name in names:
        d=(a.loc[name]-a.loc[ANCHOR]).reset_index();d.shortfall=-d.shortfall;d['model']=name;deltas.append(d)
        v=d[nonreturn].to_numpy(); top=d[d.top_n.eq(3)][nonreturn].to_numpy()
        trials.append(dict(model=name,nonreturn_regressions=int((v< -1e-12).sum()),nonreturn_improvements=int((v>1e-12).sum()),top3_nonreturn_regressions=int((top< -1e-12).sum()),xirr_regressions=int(d.xirr.lt(-1e-12).sum()),rank_ic=float(s[s.model.eq(name)&s.scope.eq('expanded')&s.return_treatment.eq('capped')&s.top_n.eq(3)].rank_ic.mean()),passes=bool((v>=-1e-12).all() and (v>1e-12).any() and d.xirr.ge(-1e-12).all())))
    tr=pd.DataFrame(trials).sort_values(['top3_nonreturn_regressions','nonreturn_regressions','rank_ic','model'],ascending=[True,True,False,True])
    tr.to_csv(OUT/f'trials_{stage}.csv',index=False);pd.concat(deltas).to_csv(OUT/f'deltas_{stage}.csv',index=False)
    return tr

def main():
    protocol();ref=load_reference();x=pd.read_pickle(p.OUT/'prepared.pkl.gz',compression='gzip');x=peer_features(x)
    for year in range(2020,2024):learn_year(x,ref,year,list(CONFIGS))
    dev=evaluate(ref,'development',list(CONFIGS)); name=dev.iloc[0].model
    write('development_lock.json',dict(selected=name,trial_sha256=hashlib.sha256((OUT/'trials_development.csv').read_bytes()).hexdigest(),fresh_validation=False))
    for year in [2024,2025,'current']:learn_year(x,ref,year,[name])
    recent=evaluate(ref,'recent',[name])
    accepted=bool(dev.iloc[0].passes and recent.iloc[0].passes)
    write('decision.json',dict(selected_patch=name,promote=accepted,status='PATCH_PASSES_RESEARCH_GATE' if accepted else 'RETAIN_UNMODIFIED_CHAMPION',fresh_validation=False,website_changed=False))
    print(dev.to_string(index=False),recent.to_string(index=False),flush=True)

if __name__=='__main__':main()
