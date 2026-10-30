"""Fixed sector-only search; exposed retrospective evidence, no fresh holdout claim."""
from pathlib import Path
import sys,json,itertools,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from stock_ranker.closing_high_review import high_component
from stock_ranker.sector_scoring import components,score
OUT=ROOT/'experiments/sector-tuning-20261005'
KEYS=['isin','decision_date','profile_name']
METRICS=['xirr','drawdown','achievement','shortfall','ndcg']

def write(name,data):
    (OUT/name).write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8')

def prepare():
    OUT.mkdir(exist_ok=True)
    choices=[]
    for h,d,m,g,r in itertools.product([.3,.4,.5],[.1,.2],[.05,.1],[0,.1],[0,.5]):
        c=dict(high=h,downside=d,momentum=m,goal=g,relative_high=r)
        c['name']=f'h{h}_d{d}_m{m}_g{g}_r{r}'
        choices.append(c)
    write('protocol.json',{'objective':'Within-sector Top 3, equal sector and profile weights; global ranking excluded',
        'selection_period':'2020-2023 previously exposed development dates', 'candidates':choices,
        'sector_mapping':'Current runtime product_sector; retrospective, not historical PIT membership',
        'gate':'All five development averages nonworse; each profile XIRR/drawdown loss <=1pp, shortfall increase <=0.5pp; >=55% sectors nonnegative utility',
        'utility':'delta XIRR +0.5 delta drawdown +0.5 delta achievement -delta shortfall +0.2 delta NDCG',
        'fallback':'Unknown sectors or fewer than five eligible peers retain previous reviewed score',
        'evaluation':'Lock before early/exposed diagnostics; no new independent-validation claim'})
    cache=OUT/'prepared.pkl.gz'
    if cache.exists():return
    prep=pd.read_pickle(ROOT/'experiments/personalized-deep-championship-20261002/v3/prepared.pkl.gz',compression='gzip')
    features=prep[KEYS+['days_since_recorded_high','distance_from_recorded_high','downside_volatility_1y','enhanced_goal_score']].copy()
    del prep
    dated=pd.read_csv(ROOT/'experiments/v17-peak-activity-20261004/dated_features.csv.gz',usecols=['isin','decision_date','high52_freshness','momentum_12_1'])
    facts=pd.read_csv(ROOT/'research/runtime/personalized-v17/facts.csv.gz',usecols=['isin','product_sector']).rename(columns={'product_sector':'sector'})
    facts.sector=facts.sector.fillna('Unclassified').replace(r'^\s*$','Unclassified',regex=True)
    pieces=[]
    for period in ['development','early','exposed']:
        current=pd.read_csv(ROOT/f'experiments/closing-high-recovery-20261004/{period}_scores.csv.gz',usecols=KEYS+['recovery_score']).rename(columns={'recovery_score':'current_score'})
        previous=pd.read_csv(ROOT/f'experiments/v17-refinement-20261004/{period}_refined_scores.csv.gz')
        x=current.merge(previous,on=KEYS,validate='one_to_one').merge(features,on=KEYS,validate='one_to_one')
        x=x.merge(dated,on=['isin','decision_date'],validate='many_to_one').merge(facts,on='isin',validate='many_to_one')
        x['closing_high_component']=high_component(x.days_since_recorded_high,x.distance_from_recorded_high,x.high52_freshness)
        x['period']=period
        pieces.append(components(x))
    frame=pd.concat(pieces,ignore_index=True)
    assert frame.decision_date.nunique()==44 and frame.profile_name.nunique()==9
    assert not frame.duplicated(KEYS).any()
    frame.to_pickle(cache,compression='gzip')
    print('PREPARED',len(frame),flush=True)

def evaluate(x,choices,top_n=3):
    """Vectorized candidates per sector; tie break by ISIN. No cross-sector selection."""
    x=x.dropna(subset=['current_score','future_xirr','future_drawdown','future_shortfall']).sort_values('isin').copy()
    for c in choices:x[c['name']]=score(x,c)
    names=['current_score']+[c['name'] for c in choices]
    result=[]
    for (day,profile,sector),g in x.groupby(['decision_date','profile_name','sector'],sort=False):
        if len(g)<5 or sector=='Unclassified':continue
        predictions=g[names].to_numpy()
        assert np.isfinite(predictions).all()
        top=np.argsort(-predictions,axis=0,kind='stable')[:top_n]
        y=g.future_xirr.to_numpy();risk=g.future_drawdown.to_numpy();short=g.future_shortfall.to_numpy()
        relevance=g.future_xirr.rank(pct=True).to_numpy();discount=np.log2(np.arange(2,top_n+2))[:,None]
        ndcg=(relevance[top]/discount).sum(axis=0)/(np.sort(relevance)[-top_n:][::-1]/discount[:,0]).sum()
        metrics=np.column_stack([np.median(y[top],axis=0),risk[top].mean(axis=0),(short[top]==0).mean(axis=0),short[top].mean(axis=0),ndcg])
        for i,name in enumerate(names):
            result.append({'date':day,'profile':profile,'sector':sector,'model':name,'n':len(g),**dict(zip(METRICS,metrics[i]))})
    return pd.DataFrame(result)

def aggregate(q):
    return q.groupby(['model','sector','profile'])[METRICS].mean().groupby('model').mean()

def utility(delta):
    return delta.xirr+.5*delta.drawdown+.5*delta.achievement-delta.shortfall+.2*delta.ndcg

def search():
    protocol=json.loads((OUT/'protocol.json').read_text())
    x=pd.read_pickle(OUT/'prepared.pkl.gz',compression='gzip');x=x[x.period.eq('development')]
    trials=[]
    # Batches keep memory bounded and preserve the prespecified grid.
    choices=protocol['candidates']
    for start in range(0,len(choices),12):
        batch=choices[start:start+12];q=evaluate(x,batch);a=aggregate(q);ref=a.loc['current_score']
        profile=q.groupby(['model','sector','profile'])[METRICS].mean().groupby(['model','profile']).mean()
        sector=q.groupby(['model','sector','profile'])[METRICS].mean().groupby(['model','sector']).mean()
        for c in batch:
            delta=a.loc[c['name']]-ref
            pdiff=profile.loc[c['name']]-profile.loc['current_score']
            sdiff=sector.loc[c['name']]-sector.loc['current_score']
            sector_win=float((utility(sdiff)>=-1e-12).mean())
            gate=bool((delta[['xirr','drawdown','achievement','ndcg']]>=-1e-12).all() and delta.shortfall<=1e-12
                and pdiff.xirr.min()>=-.01 and pdiff.drawdown.min()>=-.01 and pdiff.shortfall.max()<=.005 and sector_win>=.55)
            trials.append({**c,'utility':float(utility(delta)),'gate':gate,'sector_utility_win_fraction':sector_win,
                           **{k+'_delta':float(delta[k]) for k in METRICS}})
        pd.DataFrame(trials).to_csv(OUT/'trials.csv',index=False)
        print('SEARCH',len(trials),'/',len(choices),'passing',sum(t['gate'] for t in trials),flush=True)
    passing=sorted([c for c in trials if c['gate']],key=lambda c:(-c['utility'],c['high'],c['name']))
    write('selection_lock.json',{'winner':passing[0] if passing else None,'trial_count':len(trials),
         'protocol_sha256':hashlib.sha256((OUT/'protocol.json').read_bytes()).hexdigest(),
         'exposure':'Development-only selection in this round; historical data previously exposed'})
    print('LOCKED',passing[:1],flush=True)

def final():
    selected=json.loads((OUT/'selection_lock.json').read_text())['winner']
    if selected is None:print('No candidate meets prespecified guardrails');return
    x=pd.read_pickle(OUT/'prepared.pkl.gz',compression='gzip')
    summaries=[]
    for period,g in x.groupby('period'):
        q=evaluate(g,[selected]);q.to_csv(OUT/f'{period}_sector_metrics.csv.gz',index=False)
        a=aggregate(q).reset_index();a['period']=period;summaries.append(a)
        q.groupby(['model','sector','profile'])[METRICS].mean().to_csv(OUT/f'{period}_sector_profile_metrics.csv')
        print('FINAL',period,a.to_dict('records'),flush=True)
    pd.concat(summaries).to_csv(OUT/'summary.csv',index=False)

def sensitivity():
    selected=json.loads((OUT/'selection_lock.json').read_text())['winner']
    x=pd.read_pickle(OUT/'prepared.pkl.gz',compression='gzip');rows=[];profiles=[]
    for period,g in x.groupby('period'):
        for n in [1,5]:
            q=evaluate(g,[selected],top_n=n)
            a=aggregate(q).reset_index();a['period']=period;a['top_n']=n;rows.append(a)
        q=pd.read_csv(OUT/f'{period}_sector_metrics.csv.gz')
        a=q.groupby(['model','sector','profile'])[METRICS].mean().groupby(['model','profile']).mean().reset_index()
        a['period']=period;profiles.append(a)
        print('SENSITIVITY',period,flush=True)
    pd.concat(rows).to_csv(OUT/'top1_top5_sensitivity.csv',index=False)
    pd.concat(profiles).to_csv(OUT/'profile_summary.csv',index=False)

if __name__=='__main__':globals()[sys.argv[1]]()
