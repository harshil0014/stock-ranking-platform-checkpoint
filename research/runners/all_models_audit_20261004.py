"""Inventory retained model evidence and recompute pairwise common-cohort metrics."""
from pathlib import Path
import csv,gzip,json,sys,hashlib,os
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from stock_research.personalized_validation import ranking_metrics
OUT=ROOT/'research/reports/all-models-audit-20261004'
KEYS=['isin','decision_date','profile_name']
METRICS=['median_xirr_top20','mean_asset_drawdown_top20','target_achievement_top20','target_shortfall_top20','ndcg20','rank_ic','pairwise_accuracy']

def inventory():
    OUT.mkdir(exist_ok=True)
    entries=[];labels=[]
    for directory in ['experiments','data/analysis','data/walk_forward','research/freezes']:
        paths=[]
        for parent,dirs,files in os.walk(ROOT/directory):
            dirs[:]=[d for d in dirs if not any(t in d.lower() for t in ['cache','provider','raw','history-receipts','source','financial','screener','adjudication'])]
            paths.extend(Path(parent)/name for name in files if any(t in name.lower() for t in
                ['score','rank','prediction','metric','leaderboard','trial','comparison','summary','blend','candidate','selection','panel','turnover','tournament','search','challenger']))
        for path in sorted(paths):
            if not path.is_file() or not (path.name.endswith('.csv') or path.name.endswith('.csv.gz')):continue
            try:
                opener=gzip.open if path.suffix=='.gz' else open
                with opener(path,'rt',encoding='utf-8-sig',newline='') as f: cols=next(csv.reader(f))
                score_cols=[c for c in cols if any(t in c.lower() for t in ['score','prediction']) and not any(t in c.lower() for t in ['delta','source','reason','count'])]
                label_cols=[c for c in cols if c in ['model','candidate','candidate_id','recipe','variant','challenger','strategy','name']]
                metric_cols=[c for c in cols if c in METRICS or c in ['rank_ic','spearman','ndcg','mean_return','mean_forward_return']]
                if not score_cols and not label_cols and not metric_cols:continue
                entries.append({'path':path.relative_to(ROOT).as_posix(),'bytes':path.stat().st_size,
                    'historical_keys':set(KEYS).issubset(cols),'score_columns':'|'.join(score_cols),
                    'label_columns':'|'.join(label_cols),'metric_columns':'|'.join(metric_cols),
                    'columns':cols})
                if label_cols and path.stat().st_size<5_000_000 and not path.name.endswith('.gz'):
                    f=pd.read_csv(path,usecols=label_cols,low_memory=False)
                    for col in label_cols:
                        for value in f[col].dropna().astype(str).unique():
                            labels.append({'path':path.relative_to(ROOT).as_posix(),'column':col,'label':value})
            except Exception as exc:
                entries.append({'path':path.relative_to(ROOT).as_posix(),'error':str(exc)})
    (OUT/'artifact_inventory.json').write_text(json.dumps(entries,indent=2))
    pd.DataFrame([{k:v for k,v in e.items() if k!='columns'} for e in entries]).to_csv(OUT/'artifact_inventory.csv',index=False)
    pd.DataFrame(labels).to_csv(OUT/'retained_model_labels.csv',index=False)
    print('INVENTORY',len(entries),'artifacts',len(labels),'label occurrences',flush=True)

def compare(extended=False):
    current=pd.concat([pd.read_csv(ROOT/f'experiments/closing-high-recovery-20261004/{p}_scores.csv.gz').assign(period=p)
                       for p in ['early','development','exposed']],ignore_index=True)
    outcomes=pd.concat([pd.read_csv(ROOT/f'experiments/v17-refinement-20261004/{p}_refined_scores.csv.gz',
        usecols=KEYS+['future_xirr','future_shortfall','future_drawdown']) for p in ['early','development','exposed']],ignore_index=True)
    current=current.merge(outcomes,on=KEYS,validate='one_to_one')
    specs=[]
    def register(label,folder,patterns,column):
        specs.append((label,[ROOT/'experiments'/folder/p for p in patterns],column))
    periods=['early','development','exposed']
    for label,col in [('Original Personalized policy','champion_score'),('V17','v17_score'),('V17 refined','repair_score')]:
        register(label,'v17-refinement-20261004',[p+'_refined_scores.csv.gz' for p in periods],col)
    register('V18 rejected candidate','personalized-v18-20261003',['early_all_scores.csv.gz','development_scores.csv.gz','exposed_scores.csv.gz'],'new_score')
    for name in ['v15','v16']:
        register(name.upper(),'personalized-v16-20261003',['development_scores.csv.gz','exposed_2024_2025_scores.csv.gz'],name+'_score')
    register('V14','personalized-v14-ml-20261003',['known_evaluation_scores.csv.gz'],'v14_score')
    for label,folder,suffix,col in [
        ('V17 ATH diagnostic','v17-ath-refinement-20261004','_diagnostic_scores.csv.gz','candidate_score'),
        ('V17 peak context','v17-peak-context-20261004','_scores.csv.gz','candidate_score'),
        ('Closing High confirmation','v17-peak-confirmation-20261004','_scores.csv.gz','new_score')]:
        register(label,folder,[p+suffix for p in periods],col)
    register('Closing High priority','v17-peak-activity-20261004',['priority_'+p+'_scores.csv.gz' for p in periods],'priority_score')
    if extended:
        specs=[]
        register('Deep championship V1','personalized-deep-championship-20261002/v1',
                 ['development_winner_scores.csv.gz','clean_2024_holdout_scores.csv.gz','exposed_2025_diagnostic_scores.csv.gz'],'candidate_score')
        register('V12','personalized-deep-championship-20261002/v3',
                 ['development_winner_scores.csv.gz','postlock_2024_diagnostics_scores.csv.gz','untouched_final_2025_scores.csv.gz','postfinal_2025_diagnostics_scores.csv.gz'],'candidate_score')
        for name,cols in [('rankers',['catboost_yetirank_pairwise_blend_score','xgboost_rank_ndcg_blend_score']),
                          ('regimes',['jump_blend_score','volatility_blend_score','hmm_blend_score','jump_adwin_blend_score'])]:
            for col in cols:specs.append(('Archived '+col,[OUT/'archived'/f'{name}.csv.gz'],col))
        panel=ROOT/'experiments/personalized-deep-history-20261002/real-panel-v12/deep_panel.csv.gz'
        columns=pd.read_csv(panel,nrows=0).columns
        for col in columns:
            if col.endswith('_score') and col not in ['fractional_professor_score']:
                specs.append(('Executable '+col,[panel],col))
        # Earliest fractional and global prototypes have different execution economics;
        # inventory those rather than relabel their outcomes as comparable SIP results.
    if extended=='v13':
        prep=pd.read_pickle(ROOT/'experiments/personalized-deep-championship-20261002/v3/prepared.pkl.gz',compression='gzip')
        cols=KEYS+['history_months','cagr_5y_observed','downside_volatility_1y']
        prep=prep[cols].copy()
        champion=pd.concat([pd.read_csv(ROOT/f'experiments/v17-refinement-20261004/{p}_refined_scores.csv.gz',usecols=KEYS+['champion_score']) for p in periods],ignore_index=True)
        frame=prep.merge(champion,on=KEYS,validate='one_to_one')
        risk=frame.downside_volatility_1y
        risk=risk.fillna(risk.groupby(frame.decision_date).transform('median')).fillna(risk.median()).clip(0,2)/2
        gap=(1-frame.history_months.fillna(0).div(60).clip(0,1))*frame.cagr_5y_observed.ne(1)
        frame['v13_replayed_score']=frame.champion_score-.06*np.sqrt(gap)-.2*risk-.15*frame.profile_name.eq('weekly')*risk
        path=OUT/'v13_policy_replayed.csv.gz'
        frame[KEYS+['v13_replayed_score']].to_csv(path,index=False)
        specs=[('V13 policy replay',[path],'v13_replayed_score')]
    summary=[];detail=[];availability=[]
    cached_path=None;cached_frame=None
    for label,paths,column in specs:
        if len(paths)==1 and paths[0].name=='deep_panel.csv.gz':
            if cached_path!=paths[0]:
                allcols=pd.read_csv(paths[0],nrows=0).columns
                cached_frame=pd.read_csv(paths[0],usecols=KEYS+[c for c in allcols if c.endswith('_score')],low_memory=False)
                cached_path=paths[0]
            candidate=cached_frame[KEYS+[column]].copy()
        else:candidate=pd.concat([pd.read_csv(path,usecols=KEYS+[column]) for path in paths],ignore_index=True)
        assert not candidate.duplicated(KEYS).any(),label
        paired=current.merge(candidate.rename(columns={column:'opponent_score'}),on=KEYS,validate='one_to_one')
        for (period,day,profile),g in paired.groupby(['period','decision_date','profile_name'],sort=True):
            common=g.dropna(subset=['recovery_score','opponent_score','future_xirr','future_shortfall','future_drawdown'])
            if len(common)<20:continue
            a=ranking_metrics(common,'recovery_score');b=ranking_metrics(common,'opponent_score')
            row={'opponent':label,'period':period,'decision_date':day,'profile':profile,'common_n':len(common),
                 'current_available':int(g.recovery_score.notna().sum()),'opponent_available':int(g.opponent_score.notna().sum())}
            for m in METRICS:row.update({m+'_current':a[m],m+'_opponent':b[m],m+'_delta':a[m]-b[m]})
            detail.append(row)
        availability.append({'opponent':label,'artifacts':[p.relative_to(ROOT).as_posix() for p in paths],
                             'score_column':column,'rows_joined':len(paired),'decision_dates':paired.decision_date.nunique()})
        print('COMPARED',label,flush=True)
    full=pd.DataFrame(detail)
    if extended:
        full=pd.concat([pd.read_csv(OUT/'paired_date_profile_metrics.csv'),full],ignore_index=True)
        availability=json.loads((OUT/'comparison_sources.json').read_text())+availability
    full.to_csv(OUT/'paired_date_profile_metrics.csv',index=False)
    for (opponent,period),g in full.groupby(['opponent','period']):
        means=g[[c for c in g if c.endswith(('_current','_opponent','_delta'))]].mean().to_dict()
        directions={m:(-1 if m=='target_shortfall_top20' else 1) for m in METRICS}
        losses={m:int((g[m+'_delta']*sign < -1e-12).sum()) for m,sign in directions.items()}
        summary.append({'opponent':opponent,'period':period,'date_profile_pairs':len(g),'common_n_min':int(g.common_n.min()),
            'common_n_max':int(g.common_n.max()),'aggregate_all_seven_nonworse':all(means[m+'_delta']*s>=-1e-12 for m,s in directions.items()),
            'every_date_profile_all_seven_nonworse':not any(losses.values()),**means,**{m+'_losing_queries':n for m,n in losses.items()}})
    pd.DataFrame(summary).to_csv(OUT/'common_population_summary.csv',index=False)
    full.groupby(['opponent','period','profile'])[[m+'_delta' for m in METRICS]].mean().to_csv(OUT/'profile_deltas.csv')
    (OUT/'comparison_sources.json').write_text(json.dumps(availability,indent=2))
    print('PAIRED',len(full),'queries',flush=True)

def extended():compare(True)
def v13():compare('v13')

def catalog():
    """Preserve native studies without pretending their scores share an estimand."""
    labels=pd.read_csv(OUT/'retained_model_labels.csv').to_dict('records')
    summaries=[]
    for folder in ['data/analysis','data/walk_forward','experiments']:
        for parent,dirs,files in os.walk(ROOT/folder):
            dirs[:]=[d for d in dirs if not any(t in d.lower() for t in ['cache','provider','raw','history-receipts','source','financial','screener','adjudication'])]
            for filename in files:
                if not filename.endswith('.json') or not any(t in filename for t in ['summary','trial','selection','protocol','decision','leaderboard','definition']):continue
                path=Path(parent)/filename
                if path.stat().st_size>8_000_000:continue
                try:obj=json.loads(path.read_text(encoding='utf-8-sig'))
                except (ValueError,UnicodeError):continue
                def walk(value,location=''):
                    if isinstance(value,dict):
                        for key,item in value.items():
                            if key in ['models','locked_test_models','validation_scores'] and isinstance(item,dict):
                                for name,metrics in item.items():
                                    labels.append({'path':path.relative_to(ROOT).as_posix(),'column':location+'/'+key,'label':name})
                                    if isinstance(metrics,dict):summaries.append({'path':path.relative_to(ROOT).as_posix(),'model':name,'native_metrics':metrics})
                            if key in ['name','candidate','model','model_id','family','recipe'] and isinstance(item,str):
                                labels.append({'path':path.relative_to(ROOT).as_posix(),'column':location+'/'+key,'label':item})
                            if isinstance(item,(dict,list)):walk(item,location+'/'+key)
                    elif isinstance(value,list):
                        for item in value:
                            if isinstance(item,(dict,list)):walk(item,location+'[]')
                walk(obj)
    pd.DataFrame(labels).drop_duplicates().to_csv(OUT/'all_retained_labels.csv',index=False)
    (OUT/'native_study_metrics.json').write_text(json.dumps(summaries,indent=2))
    registry=[]
    for label,g in pd.DataFrame(labels).groupby('label'):
        registry.append({'label':label,'source_count':g.path.nunique(),'sources':'|'.join(sorted(set(g.path))),
                         'interpretation':'Retained artifact identifier; not necessarily a distinct fitted model'})
    pd.DataFrame(registry).to_csv(OUT/'model_label_registry.csv',index=False)
    print('CATALOG',len(registry),'retained labels',len(summaries),'native model results')

def finalize():
    """Check comparison arithmetic and preserve provenance; no strategy selection."""
    q=pd.read_csv(OUT/'paired_date_profile_metrics.csv')
    s=pd.read_csv(OUT/'common_population_summary.csv')
    assert not q.duplicated(['opponent','period','decision_date','profile']).any()
    assert q.common_n.ge(20).all()
    checks=[]
    for m in METRICS:
        assert np.allclose(q[m+'_current']-q[m+'_opponent'],q[m+'_delta'],equal_nan=True)
        assert np.isfinite(q[[m+'_current',m+'_opponent',m+'_delta']]).all().all()
        actual=q.groupby(['opponent','period'])[m+'_delta'].mean()
        saved=s.set_index(['opponent','period'])[m+'_delta'].reindex(actual.index)
        assert np.allclose(actual,saved)
        checks.append(m)
    assert s.date_profile_pairs.sum()==len(q)
    sources=json.loads((OUT/'comparison_sources.json').read_text())
    paths={p for entry in sources for p in entry['artifacts']}
    for period in ['early','development','exposed']:
        paths.add(f'experiments/closing-high-recovery-20261004/{period}_scores.csv.gz')
        paths.add(f'experiments/v17-refinement-20261004/{period}_refined_scores.csv.gz')
    paths.update(['research/runners/all_models_audit_20261004.py',
                  'src/stock_research/personalized_validation.py',
                  'research/runners/personalized_v13_smooth_history_probe.py',
                  'experiments/personalized-deep-championship-20261002/v3/prepared.pkl.gz'])
    hashes=[]
    for name in sorted(paths):
        path=ROOT/name; digest=hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
        hashes.append({'path':name,'bytes':path.stat().st_size,'sha256':digest.hexdigest()})
    verdict={'opponents':q.opponent.nunique(),'paired_queries':len(q),'dates':q.decision_date.nunique(),
             'profiles':q.profile.nunique(),'opponent_period_comparisons':len(s),
             'aggregate_all_seven_nonworse':int(s.aggregate_all_seven_nonworse.sum()),
             'every_query_all_seven_nonworse':int(s.every_date_profile_all_seven_nonworse.sum()),
             'unique_keys':True,'finite_metrics':True,'delta_and_aggregation_checks':checks,
             'source_hashes':hashes}
    (OUT/'verification.json').write_text(json.dumps(verdict,indent=2))
    lines=['# All paired score policies','',
           'Each row uses its own common dates and stocks. Current means vary when coverage differs. These are score-policy diagnostics, not a complete historical replay of the deployed UI pipeline.','',
           '| Opponent | Period | Queries | Current XIRR | Opponent XIRR | All seven aggregate metrics nonworse? |',
           '|---|---|---:|---:|---:|---|']
    for _,r in s.iterrows():
        lines.append(f'| {r.opponent} | {r.period} | {r.date_profile_pairs} | {r.median_xirr_top20_current:.2%} | {r.median_xirr_top20_opponent:.2%} | {"Yes" if r.aggregate_all_seven_nonworse else "No"} |')
    (OUT/'paired_comparison_tables.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in verdict.items() if k!='source_hashes'},indent=2))

if __name__=='__main__':
    globals()[sys.argv[1] if len(sys.argv)>1 else 'inventory']()
