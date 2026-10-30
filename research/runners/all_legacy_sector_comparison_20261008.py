"""Match retained earlier score policies to the frozen new sector challenger."""
import json,gc,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from sector_championship_20261005 import metrics,METRICS,KEYS,ROOT
OUT=ROOT/'experiments/all-model-sector-audit-20261008'
NEW=ROOT/'experiments/full-coverage-open-models-20261008'

def run(outcome_guard=False,candidate_scores=None,output_directory=None):
    global OUT
    if outcome_guard:OUT=ROOT/'experiments/action-guarded-legacy-sector-20261008'
    if output_directory:OUT=Path(output_directory)
    if candidate_scores and not output_directory:raise ValueError('Alternative candidate needs a separate output directory')
    OUT.mkdir(exist_ok=True)
    paths=sorted(NEW.glob('locked_scores_*.csv.gz'));assert len(paths)==9,'Finish nine-profile materialization first'
    x=pd.concat([pd.read_csv(p) for p in paths],ignore_index=True)
    assert not x.duplicated(KEYS).any()
    if candidate_scores:
        replacement=pd.read_csv(candidate_scores,usecols=KEYS+['replacement_score'])
        x=x.merge(replacement,on=KEYS,validate='one_to_one')
        assert x.replacement_score.notna().all()
        x['open_model']=x.replacement_score
    masked_rows=0
    if outcome_guard:
        flagged=pd.read_csv(ROOT/'experiments/sector-action-integrity-20261008/unreconciled_outcome_windows.csv.gz',usecols=KEYS).drop_duplicates()
        flagged['unreconciled_outcome']=True
        x=x.merge(flagged,on=KEYS,how='left',validate='one_to_one')
        mask=x.unreconciled_outcome.eq(True);masked_rows=int(mask.sum())
        x.loc[mask,['future_xirr','future_drawdown','future_shortfall']]=np.nan
    specs=json.loads((ROOT/'research/reports/all-models-audit-20261004/comparison_sources.json').read_text())
    specs += [dict(opponent=label,score_column=col,artifacts=[],local_column=True) for label,col in [
        ('Baseline four-factor formula replay','baseline_formula_replay'),('Production sector champion','sector_incumbent'),
        ('Prior reviewed closing-high policy','current_score'),('Professor whole-share project policy','professor_whole_share_score')]]
    protocol={'objective':'Within-sector comparison against every recoverable earlier score policy, plus full retained artifact inventory.',
      'scope':'Nine profiles; matching stocks, dates and outcome labels per opponent. At least five sector peers; Top1/3/5. Current sector classifications applied retrospectively.',
      'metrics':METRICS,'returns':['raw','capped[-1,1]'],'fresh_holdout':False,
      'limits':'Score-policy replay on common labels is not reproduction of each original study or execution pipeline. Baseline formula replay is distinct from the original strict point-in-time cohort. Missing policies are not declared beaten.',
      'sources':specs,'outcome_guard':outcome_guard,'masked_rows':masked_rows,'alternative_candidate_scores':str(candidate_scores) if candidate_scores else None,
      'guard_limits':'Unreconciled provider/official action windows excluded identically; historical scores/features are not rebuilt. This does not establish remaining outcomes are error-free.' if outcome_guard else None}
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    summaries=[];availability=json.loads((OUT/'availability.json').read_text()) if (OUT/'availability.json').exists() else []
    artifact_columns={};last_use={};artifact_cache={}
    for i,s in enumerate(specs):
        for artifact in s['artifacts']:
            artifact_columns.setdefault(artifact,set()).add(s['score_column']);last_use[artifact]=i
    for idx,spec in enumerate(specs):
        path=OUT/f'comparison_{idx:02}.csv'
        if path.exists():
            summaries.append(pd.read_csv(path));continue
        col=spec['score_column']
        if spec.get('local_column'):paired=x.assign(opponent_score=x[col])
        else:
            parts=[]
            for artifact in spec['artifacts']:
                if artifact not in artifact_cache:
                    table=pd.read_csv(ROOT/artifact,usecols=KEYS+sorted(artifact_columns[artifact]))
                    artifact_cache[artifact]=table[table.decision_date.ge('2020-01-01')]
                parts.append(artifact_cache[artifact][KEYS+[col]])
            other=pd.concat(parts,ignore_index=True);other=other[other.decision_date.ge('2020-01-01')]
            assert not other.duplicated(KEYS).any(),spec['opponent']
            paired=x.merge(other.rename(columns={col:'opponent_score'}),on=KEYS,validate='one_to_one');del parts,other;gc.collect()
        available=paired.dropna(subset=['open_model','frozen_challenger','opponent_score','future_xirr','future_drawdown','future_shortfall'])
        availability.append({'opponent':spec['opponent'],'joined_rows':len(paired),'finite_matched_rows':len(available),'matched_dates':available.decision_date.nunique(),'profiles':available.profile_name.nunique(),'source_artifacts':spec['artifacts']})
        pieces=[]
        for bounded in [False,True]:
            z=available.copy()
            if bounded:z.future_xirr=z.future_xirr.clip(-1,1)
            q=metrics(z,['open_model','frozen_challenger','opponent_score'],top_ns=(1,3,5))
            if q.empty:continue
            q['return_treatment']='capped' if bounded else 'raw'
            # Keep profile and sector results, then equal sector weights within profile.
            sector=q.groupby(['model','period','profile','top_n','return_treatment','sector'])[METRICS].mean().reset_index()
            sector['opponent']=spec['opponent'];sector.to_csv(OUT/f'sectors_{idx:02}_{"capped" if bounded else "raw"}.csv.gz',index=False)
            a=sector.groupby(['model','period','profile','top_n','return_treatment'])[METRICS].mean().reset_index();a['opponent']=spec['opponent'];pieces.append(a)
        if pieces:
            a=pd.concat(pieces);a.to_csv(path,index=False);summaries.append(a)
            pd.concat(summaries).to_csv(OUT/'all_profile_summary.csv',index=False)
        (OUT/'availability.json').write_text(json.dumps(availability,indent=2))
        print('LEGACY',idx+1,len(specs),spec['opponent'],'matched',len(available),flush=True)
        del paired,available;gc.collect()
        for artifact in spec['artifacts']:
            if last_use[artifact]==idx:artifact_cache.pop(artifact,None)
    full=pd.concat(summaries);ix=['opponent','period','profile','top_n','return_treatment'];a=full.set_index(['model']+ix)[METRICS]
    rows=[]
    for current in ['open_model','frozen_challenger']:
        d=a.loc[current]-a.loc['opponent_score'];d.shortfall=-d.shortfall;d['model']=current;rows.append(d.reset_index())
    delta=pd.concat(rows);delta.to_csv(OUT/'all_profile_directional_deltas.csv',index=False)
    for (model,opponent),g in delta.groupby(['model','opponent']):
        assert np.isfinite(g[METRICS]).all().all()
    report=delta.groupby(['model','opponent','period','top_n','return_treatment'])[METRICS].mean().reset_index();report['all_six_nonworse']=report[METRICS].ge(-1e-12).all(axis=1)
    report.to_csv(OUT/'equal_profile_summary.csv',index=False)
    print('DONE',len(specs),'policies',len(delta),'comparison rows',flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--outcome-guard',action='store_true');parser.add_argument('--candidate-scores');parser.add_argument('--output-directory');args=parser.parse_args()
    run(outcome_guard=args.outcome_guard,candidate_scores=args.candidate_scores,output_directory=args.output_directory)
