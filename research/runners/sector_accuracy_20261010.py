"""Whole-sector accuracy diagnostic; does not replace the strict promotion gate."""
import json
import numpy as np
import pandas as pd
from scipy.stats import kendalltau
from sector_price_rebuild_20261010 import ROOT,KEYS,OLD
OUT=ROOT/'experiments/sector-accuracy-20261010'
SOURCES={'rebuilt':ROOT/'experiments/sector-price-rebuild-20261010','yeti':ROOT/'experiments/sector-yetirank-20261010'}

def pair_accuracy(scores,outcomes):
    n=len(scores);pairs=n*(n-1)/2
    if not pairs:return np.nan
    xt=pd.Series(scores).value_counts().to_numpy();yt=pd.Series(outcomes).value_counts().to_numpy()
    xties=float(np.sum(xt*(xt-1)/2));yties=float(np.sum(yt*(yt-1)/2))
    if pairs==xties or pairs==yties:return .5
    tau=float(kendalltau(scores,outcomes).statistic)
    # Tau-b -> concordant-minus-discordant pairs. Each tied pair gets half credit.
    net=tau*np.sqrt((pairs-xties)*(pairs-yties))
    return float(.5+.5*net/pairs)

def protocol():
    OUT.mkdir(exist_ok=True)
    doc={'role':'Additional whole-sector accuracy diagnostic requested by user; never substitutes for the unchanged broad promotion gate.',
      'selection':'Highest development mean rank IC across nine profiles, equal sectors and dates, both common and expanded scopes; raw outcomes only. No recent-period input into this choice. All dates previously exposed by earlier research.',
      'pair_accuracy':'Within date/profile/sector, one point per correctly ordered stock pair, zero for reversed pair, half for score/outcome ties. Equal date then sector/profile aggregation; not a probability of stock gains.',
      'coverage':'At least five finite outcome-covered peers; common universe matches production, expanded compares only full-coverage policies. Current full-universe export separate.',
      'fresh_validation':False,'source_families':list(SOURCES)}
    (OUT/'protocol.json').write_text(json.dumps(doc,indent=2))

def run():
    protocol();summaries=[]
    for family,folder in SOURCES.items():
        x=pd.read_csv(folder/'summary.csv');names=set(pd.read_csv(folder/'trials.csv').model)
        x=x[x.top_n.eq(3)&x.return_treatment.eq('raw')].copy();x['family']=family
        x['candidate']=x.model.isin(names);summaries.append(x)
    summary=pd.concat(summaries);means=summary.groupby(['family','model','period','candidate'])[['rank_ic','ndcg','xirr','drawdown','achievement','shortfall']].mean().reset_index()
    means.to_csv(OUT/'all_candidate_accuracy.csv',index=False)
    order=means[means.candidate&means.period.eq('development')].sort_values(['rank_ic','family','model'],ascending=[False,True,True])
    winner=order.iloc[0];folder=SOURCES[winner.family];name,weight=winner.model.split('_blend');weight=float(weight)
    x=pd.concat([pd.read_csv(folder/f'predictions_{year}.csv.gz') for year in range(2020,2026)],ignore_index=True)
    old=pd.concat([pd.read_csv(OLD/f'predictions_{year}.csv.gz',usecols=KEYS+['profile_defensive_15']) for year in range(2020,2026)],ignore_index=True)
    x=x.merge(old,on=KEYS,validate='one_to_one');x['guarded_previous']=.8*x.open_model+.2*x.profile_defensive_15
    x['accuracy_candidate']=(1-weight)*x.guarded_previous+weight*x[name]
    x[KEYS+['accuracy_candidate']].rename(columns={'accuracy_candidate':'replacement_score'}).to_csv(OUT/'selected_historical_scores.csv.gz',index=False)
    for family,source in SOURCES.items():
        chosen=pd.read_csv(source/'selected_historical_scores.csv.gz').rename(columns={'replacement_score':family+'_selected'})
        x=x.merge(chosen,on=KEYS,validate='one_to_one')
    rows=[]
    for scope in ['common','expanded']:
        z=x[x.sector_incumbent.notna()] if scope=='common' else x
        refs=['accuracy_candidate','rebuilt_selected','yeti_selected','open_model','frozen_challenger','guarded_previous']+(['sector_incumbent'] if scope=='common' else [])
        z=z.dropna(subset=refs+['future_xirr','future_drawdown','future_shortfall'])
        for (period,day,profile,sector),g in z.groupby(['period','decision_date','profile_name','sector']):
            if sector=='Unclassified' or len(g)<5:continue
            for model in refs:rows.append(dict(scope=scope,period=period,day=day,profile=profile,sector=sector,model=model,n=len(g),pair_accuracy=pair_accuracy(g[model].to_numpy(),g.future_xirr.to_numpy())))
        print('PAIR ACCURACY',scope,flush=True)
    query=pd.DataFrame(rows);query.to_csv(OUT/'pair_accuracy_queries.csv.gz',index=False)
    agg=query.groupby(['scope','period','profile','sector','model']).pair_accuracy.mean().groupby(['scope','period','profile','model']).mean().reset_index()
    agg.to_csv(OUT/'pair_accuracy_profiles.csv',index=False)
    overall=agg.groupby(['scope','period','model']).pair_accuracy.mean().reset_index();overall.to_csv(OUT/'pair_accuracy_summary.csv',index=False)
    # Paired sector resampling preserves all dates/profiles inside each sector.
    # It describes dispersion in the exposed research sample, not fresh validation.
    sector=query.groupby(['scope','period','sector','profile','model']).pair_accuracy.mean().groupby(['scope','period','sector','model']).mean().unstack('model')
    comparisons=[];rng=np.random.default_rng(20261010)
    for (scope,period),g in sector.groupby(level=['scope','period']):
        for candidate in ['accuracy_candidate','rebuilt_selected','yeti_selected']:
            for ref in ['open_model','frozen_challenger','guarded_previous','sector_incumbent']:
                if ref not in g:continue
                d=(g[candidate]-g[ref]).dropna().to_numpy()
                if not len(d):continue
                boot=rng.choice(d,size=(2000,len(d)),replace=True).mean(axis=1)
                comparisons.append(dict(scope=scope,period=period,model=candidate,reference=ref,sectors=len(d),mean_sector_delta=d.mean(),sector_win_fraction=(d>1e-12).mean(),lower_95=np.quantile(boot,.025),upper_95=np.quantile(boot,.975)))
    pd.DataFrame(comparisons).to_csv(OUT/'paired_sector_accuracy_differences.csv',index=False)
    chosen={'family':winner.family,'model':winner.model,'development_mean_rank_ic':float(winner.rank_ic),'status':'ACCURACY_RESEARCH_LEADER_NOT_UNIVERSAL_CHAMPION','fresh_validation':False,'production_replaced':False}
    (OUT/'selection.json').write_text(json.dumps(chosen,indent=2));print(json.dumps(chosen),flush=True);print(overall.to_string(index=False),flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--protocol-only',action='store_true');a=parser.parse_args()
    protocol() if a.protocol_only else run()
