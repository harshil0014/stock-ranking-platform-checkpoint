"""Describe evaluated standalone/blend results and saved learned weights."""
import json
import pandas as pd
import sector_specialist_combinations_20261011 as c


def main():
    out=c.OUT
    dev=pd.read_csv(out/'summary_development.csv')
    recent=pd.read_csv(out/'summary_recent.csv')
    frames=[]
    for stage,frame in [('development',dev),('exposed',recent)]:
        frame=frame[frame.top_n.eq(3)&frame.scope.eq('expanded')&frame.return_treatment.eq('capped')]
        table=frame.groupby('model')[c.p.METRICS].mean().reset_index()
        reference=table[table.model.eq(c.ANCHOR)].iloc[0]
        for metric in c.p.METRICS:
            table[metric+'_delta']=table[metric]-reference[metric]
        table['shortfall_delta']=-table.shortfall_delta
        table['stage']=stage
        table['evaluated_only']=True
        frames.append(table)
    pd.concat(frames).to_csv(out/'individual_and_combined_contributions.csv',index=False)
    rows=[]
    for year in c.YEARS:
        fitted=json.loads((out/f'stack_models_{year}.json').read_text())
        for target,model in fitted.items():
            if model.get('fallback'):
                rows.append(dict(year=year,target=target,region='all',component=c.ANCHOR,weight=1.,fallback=True))
                continue
            regimes=[('global',model['global_weights']),('breadth_below_median',model['regional_weights'][0]),('breadth_at_or_above_median',model['regional_weights'][1])]
            for region,weights in regimes:
                for component,weight in zip(model['features'],weights):
                    rows.append(dict(year=year,target=target,region=region,component=component,weight=weight,fallback=False,maximum_endpoint=model['max_endpoint'],cutoff=model['cutoff'],breadth_split=model['breadth_split']))
                rows.append(dict(year=year,target=target,region=region,component=c.ANCHOR,weight=max(0.,1-sum(weights)),fallback=False,maximum_endpoint=model['max_endpoint'],cutoff=model['cutoff'],breadth_split=model['breadth_split']))
    pd.DataFrame(rows).to_csv(out/'learned_component_weights.csv',index=False)
    c.s.write('contribution_table_scope.json',dict(interpretation='Standalone versus blended outcome comparisons from actual completed evaluations. Learned nonnegative coefficients describe the fitted stack; correlated component weights are not causal importance. Recent table contains only development-locked finalists. Unrun recent standalone cells are intentionally absent.',
        metrics='Top3, expanded, capped, equal sector/profile averages; positive oriented deltas favor candidate; no mean XIRR selection weight.',
        sources={name:c.s.digest(out/name) for name in ['summary_development.csv','summary_recent.csv','locked_finalists.json']},
        full_ablation=False,remaining='A component-removal experiment is required to claim marginal ensemble contribution; coefficient size alone does not prove it.'))
    print('CONTRIBUTION TABLES',len(rows),'weights',flush=True)


if __name__=='__main__':
    main()
