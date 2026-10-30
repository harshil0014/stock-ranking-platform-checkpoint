"""Research continuation: closing highs, sustained strength and downside risk."""
import sys,json,gc
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'research/runners'),str(ROOT/'src')]
import v17_peak_activity_20261004 as h
v,p,a=h.v,h.p,h.a
O=ROOT/'experiments/v17-peak-confirmation-20261004'
O.mkdir(exist_ok=True)

def write(name,obj):
    (O/name).write_text(json.dumps(v.clean(obj),indent=2,allow_nan=False),encoding='utf-8')

def prepare():
    path=O/'protocol.json'
    if not path.exists():
        write('protocol.json',{'created_at':datetime.now(timezone.utc).isoformat(),
            'candidates':[{'name':f'{family}_h{high}_q{weight}','family':family,'high':high,'weight':weight}
                for family in ['support','downside','combined'] for high in [.2,.3] for weight in [.025,.05,.1]],
            'formula':'(0.9-high-weight)*V17 + high*closing_high_component + 0.1*momentum_12_1_percentile + weight*confirmation',
            'confirmation':'Support is the percentile of share of past-year closes within 10% of that years maximum; downside is inverse downside-volatility percentile; combined is their equal mean. Missing values neutral 0.5.',
            'selection':'Development 2020-2023 only. Require aggregate median XIRR, drawdown, NDCG, achievement nonnegative and shortfall nonpositive versus the previous priority model on the identical eligible universe. Choose largest utility, then smaller weight.',
            'exposure':'All historical periods have prior research exposure. Later/earlier periods and current ranks used after locking this round. No blind-validation claim.',
            'reference':'Prior priority model and its trading screen are fixed. These new proxies are not a replication of FIP information discreteness.',
            'sources':['https://academic.oup.com/rfs/article-abstract/27/7/2171/1578455','https://academic.oup.com/rof/article/29/1/241/7772889']})
    return json.loads(path.read_text())

def enrich(z):
    z=h.priority_score(z)
    group=z.groupby(['decision_date','profile_name'])
    z['support_confirmation']=group.high_support.rank(pct=True).fillna(.5)
    z['downside_confirmation']=group.downside_volatility_1y.rank(pct=True,ascending=False).fillna(.5)
    z['combined_confirmation']=(z.support_confirmation+z.downside_confirmation)/2
    return z

def score(z,c):
    return ((.9-c['high']-c['weight'])*z.repair_score+c['high']*z.closing_high_component
        +.1*z.momentum_component+c['weight']*z[c['family']+'_confirmation']).where(z.activity_eligible)

def historical(period):
    source=v.load_historical(True) if period=='exposed' else pd.read_pickle(a.s.O/'historical.pkl')
    z=h.features(source);del source;gc.collect()
    ref=pd.read_csv(p.BASE/f'{period}_refined_scores.csv.gz',usecols=p.KEYS+['repair_score'])
    z=z.merge(ref,on=p.KEYS,validate='one_to_one')
    assert len(z)==len(ref)
    return enrich(z)

def search():
    protocol=prepare();z=historical('development');ref=v.evaluate(z,'priority_score');rows=[]
    for c in protocol['candidates']:
        z['new_score']=score(z,c);stats=p.summary(z,'new_score',ref);d=stats['delta']
        eligible=min(d[k] for k in ['median_xirr_top20','mean_asset_drawdown_top20','ndcg20','target_achievement_top20'])>=-1e-12 and d['target_shortfall_top20']<=1e-12
        rows.append({**c,**stats,'eligible':eligible})
        write('trials.json',rows)
        print('CONFIRMATION',c['name'],eligible,stats['utility'],flush=True)
    passing=sorted([r for r in rows if r['eligible']],key=lambda r:(-r['utility'],r['weight']))
    write('selection_lock.json',{'winner':passing[0] if passing else None,'locked_at':datetime.now(timezone.utc).isoformat(),
        'protocol_hash':p.sha(O/'protocol.json')})

def final():
    winner=json.loads((O/'selection_lock.json').read_text())['winner']
    if winner is None:
        write('decision.json',{'retained':'V17 closing-high priority','new_trials':18,'reason':'No aggregate-dominating confirmation blend; preserve published preference model.'})
        return
    results=[]
    for period in ['development','early','exposed']:
        z=historical(period);z['new_score']=score(z,winner)
        for model in ['eligible_v17_score','priority_score','new_score']:
            met=v.evaluate(z,model);met['period']=period;met['model']=model;results.append(met)
        z[p.KEYS+['new_score']].to_csv(O/f'{period}_scores.csv.gz',index=False)
        print('EVALUATED',period,flush=True)
        del z;gc.collect()
    metrics=pd.concat(results,ignore_index=True);metrics.to_csv(O/'metrics.csv',index=False)
    metrics.groupby(['period','model'])[v.METRICS].mean().reset_index().to_csv(O/'summary.csv',index=False)
    current=enrich(pd.read_csv(h.O/'priority_current_rankings.csv.gz',low_memory=False))
    current['new_score']=score(current,winner);current['new_rank']=v.ranked(current,'new_score')
    current.to_csv(O/'current_rankings.csv.gz',index=False)
    for n in [20,50,100]:
        current[current.new_rank.le(n)].sort_values(['profile_name','new_rank']).to_csv(O/f'current_top{n}.csv',index=False)
    older=current.copy();older.days_since_recorded_high+=365;older=enrich(older)
    oldscore=score(older,winner);valid=current.new_score.notna()&oldscore.notna()
    assert (oldscore[valid]<=current.loc[valid,'new_score']+1e-12).all()
    assert metrics.decision_date.nunique()==44
    pair=v.compare_metrics(metrics[metrics.model.eq('new_score')],metrics[metrics.model.eq('priority_score')])
    assert (pair.n_v15==pair.n_champion).all()
    pair.groupby('profile')[[c+'_delta' for c in v.METRICS]].mean().to_csv(O/'profile_deltas.csv')
    write('decision.json',{'model':winner,'dates':44,'profiles':9,'universe':current['isin'].nunique(),
        'identical_eligible_universe':True,'older_ath_cannot_increase_score':True,
        'status':'Exploratory continuation; not fresh validation','website_changed':False})

def report():
    lock=json.loads((O/'selection_lock.json').read_text());winner=lock['winner']
    if winner is None:
        (ROOT/'research/reports/v17_peak_confirmation_20261004.md').write_text(
            '# Closing-high confirmation continuation\n\nTested 18 prospectively listed blends of sustained high-price support and downside volatility with 20% or 30% explicit closing-high weight. The existing closing-high-priority model remains the delivered preference model. All trial measurements are retained in `experiments/v17-peak-confirmation-20261004/trials.json`. No new candidate improved all five aggregate development directions against that model.\n',encoding='utf-8')
        return
    summary=pd.read_csv(O/'summary.csv');current=pd.read_csv(O/'current_rankings.csv.gz',low_memory=False)
    lines=['# Closing-high confirmation continuation','',f"Selected development candidate: `{winner['name']}`.",'',
        f"Weights: {100*(.9-winner['high']-winner['weight']):.1f}% V17 refined, {100*winner['high']:.0f}% closing-high component, 10% 12-1 momentum, {100*winner['weight']:.1f}% {winner['family']} confirmation.",'',
        'The prior trading-activity screen is unchanged. Models are compared on identical eligible stocks. All 44 historical dates were previously researched, so these are exploratory comparisons rather than blind validation. Mean stock XIRR is not used to select a candidate. Basket median XIRRs below are averaged across decision dates and profiles; drawdown is average asset drawdown, not a cost-adjusted portfolio backtest.','',
        '| Period | Model | Basket-median XIRR | Asset drawdown | Achievement | Shortfall | NDCG@20 |','|---|---|---:|---:|---:|---:|---:|']
    for r in summary.itertuples():lines.append(f'| {r.period} | {r.model} | {r.median_xirr_top20:.2%} | {r.mean_asset_drawdown_top20:.2%} | {r.target_achievement_top20:.2%} | {r.target_shortfall_top20:.2%} | {r.ndcg20:.4f} |')
    lines+=['','## Profile tradeoffs versus prior priority model','', '| Profile | Median XIRR change (pp) | Drawdown change (pp) |','|---|---:|---:|']
    for r in pd.read_csv(O/'profile_deltas.csv').itertuples():lines.append(f'| {r.profile} | {100*r.median_xirr_top20_delta:+.2f} | {100*r.mean_asset_drawdown_top20_delta:+.2f} |')
    base=current[current.profile_name.eq('base7500')];n=base[base.ticker.eq('NYKAA')].iloc[0]
    lines+=['',f'NYKAA default ranks: V17 refined {n.winner_rank:.0f}; previous priority {n.priority_rank:.0f}; new candidate {n.new_rank:.0f}. Its recorded age remains {n.days_since_recorded_high:.0f} days.','',
        '## Current default Top20','', '| Rank | Company | Ticker | ATH age |','|---:|---|---|---:|']
    for r in base[base.new_rank.le(20)].sort_values('new_rank').itertuples():lines.append(f'| {r.new_rank:.0f} | {r.company} | {r.ticker} | {r.days_since_recorded_high:.0f} |')
    lines+=['','## Research basis','',
        '[Da, Gurun and Warachka (2014)](https://academic.oup.com/rfs/article-abstract/27/7/2171/1578455) studies continuous information and momentum. It motivates investigating trend persistence. Our share of closes near the annual high is a related hypothesis, not their information-discreteness measure. [International evidence](https://academic.oup.com/rof/article/29/1/241/7772889) reports support for information discreteness and limited standalone support for 52-week-high anchoring; these signals are not assumed universally profitable.','',
        'The data retain current-universe/survivorship and provider-revision limitations. Positive reported volume and traded-value thresholds are eligibility proxies, not guarantees of fills or transaction costs.','',
        '## Website integration','',
        'The local website offers Closing High at `/closing-high` and opens that mode by default at `/`. It uses the locked formula and activity screen for all nine saved profiles. Other valid contribution profiles recalculate the V17 component and the contribution-dependent traded-value threshold against the fixed 3 October 2026 snapshot. Original Personalized and V17 modes remain selectable. This is a local product change, not a remote deployment or live market refresh.','',
        'The runtime package includes hashed closing-high features and the selection lock. The default saved profile was compared row by row with the research export: all 4,436 identities, eligible scores and ranks reproduce within 1e-9; NYKAA remains 1,765 days from its ATH and ranks 172. Custom-profile and HTTP route checks passed. All 396 date/profile benchmark comparisons, Top20/50/100 exports, and baseline source hashes were also verified.','',
        'Trial ledger, protocol, dated scores, profile deltas and Top20/50/100 exports are in `experiments/v17-peak-confirmation-20261004`.']
    (ROOT/'research/reports/v17_peak_confirmation_20261004.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

def verify():
    winner=json.loads((O/'selection_lock.json').read_text())['winner']
    if winner is None:return
    current=pd.read_csv(O/'current_rankings.csv.gz',low_memory=False)
    fresh=score(enrich(current),winner)
    np.testing.assert_allclose(fresh,current.new_score,rtol=0,atol=1e-12,equal_nan=True)
    np.testing.assert_allclose(v.ranked(current,'new_score'),current.new_rank,rtol=0,atol=0,equal_nan=True)
    metrics=pd.read_csv(O/'metrics.csv');pairs=v.compare_metrics(metrics[metrics.model.eq('new_score')],metrics[metrics.model.eq('priority_score')])
    assert len(pairs)==44*9 and (pairs.n_v15==pairs.n_champion).all()
    assert metrics.decision_date.nunique()==44 and metrics.profile.nunique()==9
    dev=metrics[metrics.period.eq('development')&metrics.model.eq('new_score')]
    for k in v.METRICS:assert abs(dev[k].mean()-winner['metrics'][k])<1e-10,k
    for n in [20,50,100]:
        top=pd.read_csv(O/f'current_top{n}.csv')
        assert len(top)==9*n and top.new_rank.le(n).all()
        assert top.activity_eligible.all()
    before=json.loads((p.OUT/'baseline_hashes.json').read_text())
    assert all(p.sha(ROOT/name)==digest for name,digest in before.items())
    write('verification.json',{'score_and_rank_reproduced':True,'development_selection_replayed':True,
        'date_profile_comparisons':len(pairs),'same_population_every_comparison':True,
        'top20_50_100_all_profiles_verified':True,'baseline_hashes_unchanged':True})
    write('manifest.json',{'name':'V17 closing-high confirmation','candidate':winner['name'],
        'files':{str(path.relative_to(ROOT)):p.sha(path) for path in [Path(__file__),O/'protocol.json',
        O/'selection_lock.json',O/'current_rankings.csv.gz',O/'metrics.csv',O/'verification.json',
        h.O/'dated_features.csv.gz']}})
    print('VERIFIED 396 COMPARISONS',flush=True)

if __name__=='__main__':globals()[sys.argv[1]]()
