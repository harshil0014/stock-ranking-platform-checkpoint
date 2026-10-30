"""Expose where aggregate improvements conceal profile and sector regressions."""
import argparse,json
import pandas as pd
from sector_price_rebuild_20261010 import ROOT,METRICS

def run(family):
    folder=ROOT/'experiments'/({'rebuilt':'sector-price-rebuild','yeti':'sector-yetirank'}[family]+'-20261010')
    name=json.loads((folder/'selection.json').read_text())['model']
    d=pd.read_csv(folder/'directional_deltas.csv');d=d[d.model.eq(name)]
    long=d.melt(id_vars=[c for c in d if c not in METRICS],value_vars=METRICS,var_name='metric',value_name='directional_delta')
    long['regression']=long.directional_delta.lt(-1e-12)
    long.groupby(['reference','scope','period','profile','metric']).agg(comparisons=('regression','size'),regressions=('regression','sum'),mean_directional_delta=('directional_delta','mean')).reset_index().to_csv(folder/'profile_metric_tradeoffs.csv',index=False)
    q=pd.read_csv(folder/'selected_sector_query_metrics.csv.gz')
    q=q[q.top_n.eq(3)&q.return_treatment.eq('capped')]
    # Each profile gets equal weight after averaging its dates within each sector.
    a=q.groupby(['scope','period','sector','profile','model'])[METRICS].mean().groupby(['scope','period','sector','model'])[METRICS].mean()
    rows=[]
    for ref in ['guarded_previous','open_model','sector_incumbent']:
        z=(a.xs(name,level='model')-a.xs(ref,level='model')).dropna();z.shortfall=-z.shortfall;z['reference']=ref;rows.append(z.reset_index())
    paired=pd.concat(rows);paired.to_csv(folder/'sector_top3_tradeoffs.csv',index=False)
    recent=paired[paired.period.eq('exposed')&paired.reference.eq('guarded_previous')]
    print(recent.sort_values('xirr').head(8).to_string(index=False),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--family',choices=['rebuilt','yeti'],default='rebuilt');run(a.parse_args().family)
