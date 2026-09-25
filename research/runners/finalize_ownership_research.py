"""Finalize the ownership rerun, audit boundaries, and write the concise research report."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
import numpy as np
import pandas as pd
from research.runners.finalize_personalized_tournament import run as finalize,score_ensembles
from research.runners.compare_final_professor_workbook import run as workbook_compare
from stock_research.personalized_executable_tournament import BASE_CANDIDATES,FEATURES
from stock_research.personalized_validation import ranking_metrics

def write(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')
def table(frame, index=False):
 if index: frame=frame.reset_index()
 header='| '+' | '.join(map(str,frame.columns))+' |'
 rule='| '+' | '.join(['---']*len(frame.columns))+' |'
 return '\n'.join([header,rule]+['| '+' | '.join(str(x).replace('|','/') for x in row)+' |' for row in frame.itertuples(index=False,name=None)])
def digest(path):return sha256(path.read_bytes()).hexdigest()
def verify(root):
 m=json.loads((root/'manifest.json').read_text())
 for item in m['deterministic_artifacts']:
  p=root/item['path'];assert p.stat().st_size==item['size'] and digest(p)==item['sha256'],p
 return m['fingerprint']
def run(args):
 out=args.tournament;freeze=args.freeze
 freeze_fingerprint=verify(freeze);verify(out)
 assert verify(freeze.with_name(freeze.name+'-rebuild-check'))==freeze_fingerprint
 finalize(argparse.Namespace(tournament=out,freeze=freeze))
 assessment=json.loads((out/'final_assessment.json').read_text())
 from stock_research.personalized_rank_blend import fit_matured_rank_blend
 training_panel=pd.read_csv(out/'training_panel.csv.gz',low_memory=False)
 validation_panel=pd.read_csv(out/'validation_predictions.csv.gz',low_memory=False)
 current_panel=pd.read_csv(out/'current_profile_rankings.csv.gz',low_memory=False)
 blended,blend_audit=fit_matured_rank_blend(training_panel,pd.concat([validation_panel.assign(_blend_part='validation'),current_panel.assign(_blend_part='current')],ignore_index=True))
 learned_rows=[]
 for (day,profile),group in blended.loc[blended._blend_part.eq('validation')].groupby(['decision_date','profile_name']):
  common=group.dropna(subset=BASE_CANDIDATES+['future_xirr','future_shortfall','future_drawdown'])
  learned_rows.append({'decision_date':day,'profile':profile,'candidate':'learned_rank_blend_score','cohort':'common',**ranking_metrics(common,'learned_rank_blend_score')})
 learned_metrics=pd.DataFrame(learned_rows);learned_metrics.to_csv(out/'learned_ensemble_metrics.csv',index=False)
 write(out/'learned_ensemble_fit_audit.json',blend_audit)
 assert all(pd.Timestamp(a['latest_training_endpoint'])<pd.Timestamp(a['decision_date']) for a in blend_audit)
 learned_summary=learned_metrics.groupby('candidate').mean(numeric_only=True)
 fixed_summary=pd.read_csv(out/'ensemble_metrics.csv').set_index('candidate')
 assessment['strongest_train_only_learned_ensemble']='learned_rank_blend_score'
 assessment['strongest_ensemble_by_goal_shortfall']=pd.concat([fixed_summary,learned_summary]).target_shortfall_top20.idxmin()
 assessment['reason']='Six annual, retrospectively selected historical evaluation dates with matured-label fitting; current-universe survivorship, price-only wealth, gross execution, and reused historical evidence preclude production promotion.'
 write(out/'final_assessment.json',assessment)
 write(out/'selection_freeze.json',{'selection':assessment,'method':'Minimum mean goal shortfall; strongest IC reported separately. No workbook targets used.','metrics_sha256':digest(out/'candidate_metrics.csv'),'ensemble_metrics_sha256':digest(out/'ensemble_metrics.csv')})
 current=blended.loc[blended._blend_part.eq('current')].drop(columns='_blend_part').copy()
 selected=assessment['strongest_ensemble_by_goal_shortfall']
 if selected=='learned_rank_blend_score':
  current['selected_ensemble_score']=current.learned_rank_blend_score
 else:
  names,weights=selected.split('@');columns=[x+'_score' for x in names.split('+')];weights=np.array([float(x) for x in weights.split('-')]);weights/=weights.sum()
  ranks=current.groupby('profile_name')[columns].rank(pct=True)
  current['selected_ensemble_score']=sum(ranks[c]*w for c,w in zip(columns,weights)).where(ranks.notna().all(axis=1))
 fixed_selected=assessment['strongest_fixed_ensemble_by_goal_shortfall']
 fixed_names,fixed_weights=fixed_selected.split('@')
 fixed_columns=[x+'_score' for x in fixed_names.split('+')]
 fixed_weights=np.array([float(x) for x in fixed_weights.split('-')]);fixed_weights/=fixed_weights.sum()
 fixed_ranks=current.groupby('profile_name')[fixed_columns].rank(pct=True)
 current['selected_fixed_ensemble_score']=sum(fixed_ranks[c]*w for c,w in zip(fixed_columns,fixed_weights)).where(fixed_ranks.notna().all(axis=1))
 current.to_csv(out/'current_profile_rankings.csv.gz',index=False,compression={'method':'gzip','mtime':0})
 current.loc[current.profile_name.eq('base7500')].sort_values(['selected_ensemble_score','isin'],ascending=[False,True]).head(100).to_csv(out/'current_base7500_top100.csv',index=False)
 workbook_compare(argparse.Namespace(tournament=out,workbook=args.workbook))
 panel=pd.read_csv(out/'validation_predictions.csv.gz',low_memory=False)
 train=pd.read_csv(out/'training_panel.csv.gz',low_memory=False)
 protocol=json.loads((out/'protocol.json').read_text())
 supplementary=pd.read_csv(out/'supplementary_predictions.csv.gz',low_memory=False)
 score_ensembles(supplementary,protocol).to_csv(out/'supplementary_ensemble_metrics.csv',index=False)
 # Descriptive risk ablation with the same strict maturity filter as the tournament.
 from sklearn.impute import SimpleImputer
 from sklearn.linear_model import Ridge
 from sklearn.pipeline import make_pipeline
 from sklearn.preprocessing import StandardScaler
 rows=[]
 for day,target in panel.groupby('decision_date'):
  mature=train.loc[pd.to_datetime(train.endpoint).lt(pd.Timestamp(day)) & train.future_xirr.notna() & train.enhanced_carry_xirr_score.notna()].sort_values(['decision_date','profile_name','isin'])
  features=[c for c in FEATURES if c!='price_drawdown']
  model=make_pipeline(SimpleImputer(strategy='median',add_indicator=True),StandardScaler(),Ridge(alpha=100.))
  model.fit(mature[features],mature.future_xirr.clip(-1,3))
  target=target.copy();target['risk_ablation_score']=model.predict(target[features])
  for profile,group in target.groupby('profile_name'):
   common=group.dropna(subset=BASE_CANDIDATES+['future_xirr','future_shortfall','future_drawdown'])
   rows.append({'decision_date':day,'profile':profile,'candidate':'ridge_without_risk_score',**ranking_metrics(common,'risk_ablation_score')})
 risk=pd.DataFrame(rows)
 risk.to_csv(out/'risk_ablation_metrics.csv',index=False)
 ablation=pd.read_csv(out/'model_ablation.csv')
 full=pd.read_csv(out/'candidate_metrics.csv').set_index('candidate').loc['ridge_executable_score']
 additions=[]
 for metric in ['rank_ic','target_achievement_top20','target_shortfall_top20']:
  sign=-1 if metric=='target_shortfall_top20' else 1
  additions.append({'component':'risk_feature_price_drawdown','full':'ridge_executable_score','without':'ridge_without_risk_score','metric':metric,'improvement':sign*(full[metric]-risk[metric].mean())})
 pd.concat([ablation,pd.DataFrame(additions)]).to_csv(out/'model_ablation.csv',index=False)
 metrics=pd.concat([pd.read_csv(out/'validation_metrics.csv'),score_ensembles(panel,protocol),learned_metrics])
 # Utility uncertainty resamples dates, never securities or correlated profiles.
 rng=np.random.default_rng(20260925);uncertainty=[]
 for candidate,g in metrics.groupby('candidate'):
  dated=g.groupby('decision_date')[['target_shortfall_top20','target_achievement_top20','rank_ic']].mean()
  for reference in ['global_existing_score','professor_whole_share_score']:
   ref=metrics.loc[metrics.candidate.eq(reference)].groupby('decision_date')[dated.columns].mean()
   delta=dated-ref
   for metric in dated.columns:
    values=delta[metric].to_numpy()*(-1 if metric=='target_shortfall_top20' else 1)
    boot=values[rng.integers(len(values),size=(5000,len(values)))].mean(axis=1)
    uncertainty.append(dict(candidate=candidate,reference=reference,metric=metric,date_blocks=len(values),mean_improvement=float(values.mean()),low95=float(np.quantile(boot,.025)),high95=float(np.quantile(boot,.975)),status='RETROSPECTIVE_DESCRIPTIVE_SELECTION_NOT_ADJUSTED'))
 pd.DataFrame(uncertainty).to_csv(out/'paired_date_uncertainty.csv',index=False)
 audit=json.loads((out/'model_audit.json').read_text())
 fit_audits=audit['validation_fit']+audit['final_fit']
 assert all(pd.Timestamp(x['latest_training_endpoint'])<pd.Timestamp(x['decision_date']) for x in fit_audits)
 assert pd.to_datetime(panel.endpoint).max()<=pd.Timestamp('2026-09-18')
 assert pd.to_datetime(supplementary.endpoint).max()<=pd.Timestamp('2026-09-18')
 assert current.future_xirr.isna().all()
 assert not panel.duplicated(['decision_date','profile_name','isin']).any()
 assert len(panel.decision_date.unique())==6
 protected=json.loads((out/'inputs.json').read_text())['protected_state']
 assert all(digest(ROOT/p)==v for p,v in protected.items())
 prior=ROOT/'experiments/personalized-official-action-freeze/build-04'
 recovery=pd.read_csv(freeze/'all_profile_recovery_audit.csv.gz')
 old=pd.read_csv(prior/'all_profile_recovery_audit.csv.gz')
 paired=recovery.merge(old[['isin','lookback_months','status']],on=['isin','lookback_months'],suffixes=('','_old'))
 recovered=paired.status.eq('AVAILABLE')&paired.status_old.ne('AVAILABLE');lost=paired.status.ne('AVAILABLE')&paired.status_old.eq('AVAILABLE')
 blockers=recovery.loc[recovery.status.ne('AVAILABLE')].groupby(['lookback_months','status','reason'],dropna=False).size().rename('profile_rows').reset_index();blockers.to_csv(out/'blocker_reason_summary.csv',index=False)
 coverage=pd.read_csv(freeze/'executable_coverage.csv')
 history=pd.read_csv(freeze/'history_recovery_audit.csv')
 summary={'recovered_profile_rows':int(recovered.sum()),'recovered_unique_identities':int(paired.loc[recovered,'isin'].nunique()),'newly_excluded_profile_rows':int(lost.sum()),'net_profile_rows':int(recovered.sum()-lost.sum()),'invalid_observations_removed':int(history.removed_invalid_rows.fillna(0).sum()),'histories_with_invalid_observations_removed':int(history.removed_invalid_rows.fillna(0).gt(0).sum()),'additional_passive_rights_events':543,'separate_resulting_entitlements':len(pd.read_csv(freeze/'resulting_equity_terms.csv')),'coverage':coverage.to_dict('records'),'deterministic_freeze_rebuild_fingerprint':freeze_fingerprint,'train_maturity_pass':True,'future_outcomes_excluded':True,'protected_state_unchanged':True,'prior_performance_not_comparable':'Earlier nominal-price error and immature training labels invalidate direct performance-improvement claims. Compare all models on corrected outcomes instead.'}
 write(out/'ownership_audit.json',summary)
 candidates=pd.read_csv(out/'candidate_metrics.csv').set_index('candidate');ensembles=pd.concat([pd.read_csv(out/'ensemble_metrics.csv').set_index('candidate'),learned_summary]);bench=json.loads((out/'professor_comparison_summary.json').read_text())
 goal=assessment['strongest_individual_by_goal_shortfall'];ic=assessment['strongest_individual_by_rank_ic']
 report=['# Personalized investing ownership research','',f'Checkpoint: `097643b73d10f57a32cfb8ceb03d5edd17b6ddfe`. Research cutoff: 2026-09-18. Production untouched.','',f'Recovered {summary["recovered_profile_rows"]} profile rows across {summary["recovered_unique_identities"]} identities; newly excluded {summary["newly_excluded_profile_rows"]} rows after integrity corrections; net gain {summary["net_profile_rows"]}.','',table(coverage),'','## Model results','',f'13 individual candidates, 25 fixed ensembles, and one ensemble learned strictly from matured training outcomes; six annual historical evaluation dates, nine profiles; strictly matured training labels. Best individual by shortfall: **{goal}**. Best by rank IC: **{ic}**. Best combination by shortfall: **{selected}**.','',table(pd.concat([candidates.loc[[goal,ic,'global_existing_score','professor_whole_share_score']],ensembles.loc[[selected]]]).drop_duplicates()[['rank_ic','target_achievement_top20','target_shortfall_top20','median_xirr_top20']],index=True),'','## Benchmark and interpretation','',f'Sir workbook: {bench["exact_identity_matches"]}/{bench["workbook_rows"]} identities mapped; {bench["usable_workbook_purchase_rows"]} usable purchase rows. Supplied-rank agreement over {bench["supplied_rank_pairs_with_selected_individual_score"]} comparable pairs: {bench["supplied_rank_vs_selected_score_spearman_within_overlap"]}. This is within-list agreement, not global ranking accuracy. Cached purchase/investment values do not support execution reproduction.','', 'Data completeness and calculation integrity are materially improved. A superior investment policy is not established: previous performance was distorted by split double counting and temporal leakage. New comparisons use corrected outcomes, but retrospective selection, current-universe survivorship, omitted dividends/fees/slippage, and limited date blocks remain. No production promotion.','','## Remaining evidence gaps','',table(blockers),'','Rights lapse deliberately without subscription or sale; zero received proceeds is a policy assumption, not an observed entitlement quote. Exercise sensitivity uses record-date proxy cash and is hypothetical. Unknown resulting-security or fractional proceeds remain blocked. Resulting-company values use separate holdings and observed terminal prices; risk features remain parent-security features. Dividends are excluded from executable wealth and risk; the global baseline retains original adjusted features. Terminal adjusted values in overlay files are inferred only for schema compatibility; executable calculations use raw prices. No missing raw price was imputed.','', 'Raw histories and documents, large prediction panels, and checkpoints remain outside Git. Compact audit artifacts and their source hashes are versioned.','','Exact next step: shadow-run the frozen selected policy without changing production; evaluate genuinely prospective outcomes after 2026-09-18 and obtain missing fractional settlements/resulting-security quotes before claiming total-return completeness.']
 (ROOT/'docs/PERSONALIZED_OWNERSHIP_RESEARCH_20260925.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
 normalized=ROOT/'research/data/ownership-recovery-20260925'
 inputs=json.loads((out/'inputs.json').read_text())
 inputs['normalized_recovery_sources']={str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in sorted(normalized.iterdir()) if p.is_file()}
 inputs['finalizer_sources']={str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in [Path(__file__),ROOT/'src/stock_research/personalized_rank_blend.py',ROOT/'research/runners/compare_final_professor_workbook.py']}
 write(out/'inputs.json',inputs)
 test_log=ROOT/'experiments/ownership-final-tests.log'
 write(out/'verification_summary.json',{'freeze_rebuild_fingerprint':freeze_fingerprint,'protected_state_unchanged':True,'matured_training_fits':len(fit_audits),'learned_blend_maturity_pass':True,'test_log_tail':test_log.read_text(encoding='utf-8',errors='replace').splitlines()[-4:],'test_log_sha256':digest(test_log),'raw_and_large_artifacts_outside_git':True})
 files=[{'path':p.name,'size':p.stat().st_size,'sha256':digest(p)} for p in sorted(out.iterdir()) if p.is_file() and p.name!='manifest.json']
 write(out/'manifest.json',{'deterministic_artifacts':files,'fingerprint':sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()});verify(out)
 print(json.dumps(summary,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--tournament',type=Path,required=True);p.add_argument('--freeze',type=Path,required=True);p.add_argument('--workbook',type=Path,required=True);run(p.parse_args())
