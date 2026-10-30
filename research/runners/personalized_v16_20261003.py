"""Read-only reuse of frozen V15 inputs; all new writes belong to V16."""
import sys,json,gc,hashlib,itertools,subprocess
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import personalized_v15_20261003 as v
O=v.ROOT/'experiments/personalized-v16-20261003'
R=v.ROOT/'research/reports/personalized_v16_20261003.md'
O.mkdir(exist_ok=True)
def write(n,x): (O/n).write_text(json.dumps(v.clean(x),indent=2,allow_nan=False)+'\n',encoding='utf-8')
def csv(n,x): x.to_csv(O/n,index=False,compression={'method':'gzip','mtime':0} if n.endswith('.gz') else None)
def now(): return datetime.now(timezone.utc).isoformat()
def cohorts(x):
    masks={'short_history':x.history_months.lt(60),'full_history':x.has_true_5y.eq(1),'high_volatility':x.realized_volatility_1y.ge(x.groupby(['decision_date','profile_name']).realized_volatility_1y.transform('quantile',.75)),'deep_drawdown':x.full_history_max_drawdown.le(-.5),'deep_ath':x.distance_from_recorded_high.le(-.4),'old_ath':x.days_since_recorded_high.ge(1095),'recent_ath':x.days_since_recorded_high.le(90)}
    rows=[]
    for name,mask in masks.items():
        for model in ['champion','v15','v16']:
            z=x.loc[mask]; metrics=v.evaluate(z,model+'_score')
            selected=x.dropna(subset=[model+'_score']+v.OUTCOME).sort_values(['decision_date','profile_name',model+'_score','isin'],ascending=[True,True,False,True]).groupby(['decision_date','profile_name']).head(20)
            selected=selected.loc[mask.reindex(selected.index)]
            rows.append({'cohort':name,'model':model,'share_overall_top20':len(selected)/(20*x.groupby(['decision_date','profile_name']).ngroups),'selected_xirr':selected.future_xirr.median(),'selected_drawdown':selected.future_drawdown.mean(),**metrics[v.METRICS].mean().to_dict()})
    return pd.DataFrame(rows)
def audit():
    before=json.loads((O/'protected_before.json').read_text()); changed=[]
    items=list(before.items())
    def check(item):
        p,h=item; file=v.ROOT/p
        return p if not file.is_file() or v.sha(file)!=h else None
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i,result in enumerate(pool.map(check,items)):
            if result: changed.append(result)
            if i%3000==0: print('VERIFY',i,flush=True)
    assert not changed,changed
    write('integrity_audit.json',{'verified_at':now(),'protected_count':len(before),'changed':changed,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=v.ROOT,text=True).strip(),'production_website_railway':'No source, configuration, deployment, or network writes; tracked production and website hashes verified','frozen_champion_v14_v15':'All protected hashes unchanged','historical_current_separation':True,'no_identity_features_or_NYKAA_rule':True,'universe_limit':'Frozen research cohorts have survivorship/selection exposure; historical publication timing and provider revisions not fully provable','historical_label_maturity':'Frozen V15 correction development fit endpoint <2020-03-31; evaluation <2024-03-31; current <2026-10-03. No new fit.'})
    paths=[p for p in O.iterdir() if p.is_file() and p.name!='manifest.json']+[Path(__file__),R]
    write('manifest.json',{'created_at':now(),'sha256':{str(p.relative_to(v.ROOT)):v.sha(p) for p in paths},'protected_snapshot_sha256':v.sha(O/'protected_before.json')})
    print('AUDIT VERIFIED',len(before),flush=True)
def ranks(x):
    for s in ['champion','v15','v16']:
        if s+'_score' in x: x[s+'_rank']=v.ranked(x,s+'_score')
    return x
def turns(x):
    tables=[]
    for a,b in [('v15','champion'),('v16','champion'),('v16','v15')]:
        if a+'_score' not in x: continue
        z=x.copy(); z['champion_score']=x[b+'_score']
        tables.append(v.turnover(z,a+'_score').assign(comparison=a+'_vs_'+b))
    return pd.concat(tables,ignore_index=True)
def autopsy():
    assert not (O/'hypothesis_lock.json').exists()
    if not (O/'protected_before.json').exists():
        paths=v.protected_paths()+list(v.OUT.rglob('*'))+[v.REPORT,v.ROOT/'research/runners/personalized_v15_20261003.py']
        hashes={}
        for i,p in enumerate(sorted(set(p for p in paths if p.is_file()))):
            hashes[str(p.relative_to(v.ROOT))]=v.sha(p)
            if i%3000==0: print('PROTECT',i,flush=True)
        write('protected_before.json',hashes)
    if (O/'development.pkl.gz').exists(): x=pd.read_pickle(O/'development.pkl.gz',compression='gzip')
    else:
        x=v.load_historical(False); dates=v.protocol()['development_selection_dates']
        x=x.loc[x.decision_date.isin(dates)].merge(v.benchmark(dates),on=v.KEYS,validate='one_to_one')
    m=lgb.Booster(model_file=str(v.OUT/'development_balanced_return__confidence_only.txt'))
    x['correction_percentile']=v.correction(x,m); x['v15_score']=v.guided(x,x.correction_percentile,.2); ranks(x)
    base=v.evaluate(x,'champion_score'); pair=v.compare_metrics(v.evaluate(x,'v15_score'),base)
    old=pd.read_csv(v.OUT/'development_all_profile_date_results.csv'); old=old.loc[old.candidate.eq('balanced_return__confidence_only__0.2')]
    check=pair.merge(old,on=['decision_date','profile'],suffixes=('_new','_old'))
    error=max(float((check[c+'_delta_new']-check[c+'_delta_old']).abs().max()) for c in v.METRICS)
    assert error<1e-10
    write('reconstruction_audit.json',{'max_metric_error':error,'model_sha256':v.sha(v.OUT/'development_balanced_return__confidence_only.txt'),'sealed_post2023_labels':True})
    csv('v15_development_profile_date_results.csv',pair); csv('good_bad_profiles.csv',pair.groupby('profile',as_index=False)[[c+'_delta' for c in v.METRICS]].mean())
    x.to_pickle(O/'development.pkl.gz',compression='gzip')
    rows=[]; tops=[]; attrib=[]
    rng=np.random.default_rng(20261003)
    for day,g in x.loc[x.profile_name.eq('lookback12')].groupby('decision_date'):
        eligible=g.dropna(subset=['champion_score','v15_score']+v.OUTCOME)
        a=eligible.sort_values(['champion_score','isin'],ascending=[False,True]).head(20); b=eligible.sort_values(['v15_score','isin'],ascending=[False,True]).head(20)
        tops.append(pd.concat([a.assign(selection='champion'),b.assign(selection='v15')]))
        exits=a.loc[~a['isin'].isin(b['isin'])]; entries=b.loc[~b['isin'].isin(a['isin'])]
        common=a.loc[a['isin'].isin(b['isin'])].future_xirr.to_list()
        ev=exits.future_xirr.to_numpy(); nv=entries.future_xirr.to_numpy(); n=len(ev); contributions=np.zeros(n)
        for _ in range(512):
            vals=ev.copy(); before=np.median(common+vals.tolist())
            for j in rng.permutation(n):
                vals[j]=nv[j]; after=np.median(common+vals.tolist()); contributions[j]+=after-before; before=after
        for j,(ei,ni) in enumerate(zip(exits.index,entries.index)):
            e=x.loc[ei]; p=x.loc[ni]
            r={'decision_date':day,'exit_isin':e['isin'],'entry_isin':p['isin'],'median_xirr_attribution':contributions[j]/512,'drawdown_attribution':(p.future_drawdown-e.future_drawdown)/20,'entry_xirr':p.future_xirr,'exit_xirr':e.future_xirr,'entry_drawdown':p.future_drawdown,'exit_drawdown':e.future_drawdown}
            for c in ['champion_rank','v15_rank','evidence_confidence','history_months','days_since_recorded_high','distance_from_recorded_high','realized_volatility_1y','full_history_max_drawdown','strict_cagr_1y','cagr_3y','enhanced_carry_xirr_score','enhanced_goal_score','cash_utilization','unaffordable_rate','price_drawdown','target_attainment']:
                r['entry_'+c]=p[c]; r['exit_'+c]=e[c]
            attrib.append(r)
        rows.append({'decision_date':day,'substitutions':n,'champion_xirr':a.future_xirr.median(),'v15_xirr':b.future_xirr.median(),'xirr_delta':b.future_xirr.median()-a.future_xirr.median(),'drawdown_delta':b.future_drawdown.mean()-a.future_drawdown.mean(),'market_median_1y_growth':g.strict_cagr_1y.median(),'market_median_volatility':g.realized_volatility_1y.median()})
    dt=pd.DataFrame(rows); reference=pair.loc[pair.profile.eq('lookback12')].merge(dt,on='decision_date')
    assert (reference.median_xirr_top20_delta-reference.xirr_delta).abs().max()<1e-10
    assert (reference.mean_asset_drawdown_top20_delta-reference.drawdown_delta).abs().max()<1e-10
    csv('autopsy_12m_dates.csv',dt); csv('autopsy_12m_substitutions.csv',pd.DataFrame(attrib)); csv('autopsy_12m_top20.csv',pd.concat(tops))
    # Whole-family replacement diagnostics preserve all other inputs, and use no refit.
    tests=[]
    for family,cs in v.FAMILIES.items():
        cols=[c for c in cs if c in m.feature_name()]
        if not cols: continue
        z=x.copy()
        for c in cols: z[c]=z.groupby(['decision_date','profile_name'])[c].transform('median')
        z['v15_score']=v.guided(z,v.correction(z,m),.2)
        p=v.compare_metrics(v.evaluate(z,'v15_score'),base)
        tests.append(p.assign(ablated_family=family))
        print('ABLATE',family,flush=True)
    csv('autopsy_family_ranking_counterfactuals.csv',pd.concat(tests))
    csv('v15_development_turnover.csv',turns(x))
    print(pd.DataFrame(rows).to_string(index=False)); print(pd.DataFrame(attrib).sort_values('drawdown_attribution').head(12).to_string(index=False)); print('AUTOPSY COMPLETE',flush=True)
def inspect():
    d=pd.read_csv(O/'autopsy_12m_dates.csv'); a=pd.read_csv(O/'autopsy_12m_substitutions.csv')
    print('DATES',d.to_string(index=False))
    print('PROFILES',pd.read_csv(O/'good_bad_profiles.csv').to_string(index=False))
    z=pd.read_csv(O/'autopsy_family_ranking_counterfactuals.csv')
    print('FAMILY',z.groupby(['ablated_family','profile'])[['median_xirr_top20_delta','mean_asset_drawdown_top20_delta','target_shortfall_top20_delta']].mean().to_string())
    print('ENTRY_EXIT',a.filter(regex='entry_|exit_').select_dtypes('number').mean().to_string())
    x=pd.read_pickle(O/'development.pkl.gz',compression='gzip')
    m=lgb.Booster(model_file=str(v.OUT/'development_balanced_return__confidence_only.txt'))
    selected=x.loc[x.champion_rank.le(20)|x.v15_rank.le(20)].copy()
    sh=m.predict(selected[m.feature_name()],pred_contrib=True,num_threads=4)[:,:-1]
    for f,cs in v.FAMILIES.items():
        inds=[m.feature_name().index(c) for c in cs if c in m.feature_name()]
        selected[f+'_shap']=sh[:,inds].sum(axis=1) if inds else 0
    selected['selection']=np.select([selected.champion_rank.le(20)&selected.v15_rank.le(20),selected.v15_rank.le(20)],['retained','promoted'],default='demoted')
    csv('autopsy_all_profile_stock_behavior.csv.gz',selected)
    summaries=selected.groupby(['profile_name','selection']).mean(numeric_only=True).reset_index()
    csv('autopsy_profile_selection_composition.csv',summaries)
    print('SHAP',summaries[['profile_name','selection']+[f+'_shap' for f in v.FAMILIES]].to_string(index=False))
    state=[]
    for field,mask in [('short_history',a.entry_history_months.lt(60)),('full_history',a.entry_history_months.ge(60)),('old_ath',a.entry_days_since_recorded_high.ge(1095)),('recent_ath',a.entry_days_since_recorded_high.le(90)),('deep_ath',a.entry_distance_from_recorded_high.le(-.4)),('deep_drawdown',a.entry_full_history_max_drawdown.le(-.5)),('high_volatility',a.entry_realized_volatility_1y.ge(a.entry_realized_volatility_1y.quantile(.75)))]:
        state.append({'state':field,'substitutions':int(mask.sum()),'mean_date_xirr_attribution':a.loc[mask,'median_xirr_attribution'].sum()/16,'mean_date_drawdown_attribution':a.loc[mask,'drawdown_attribution'].sum()/16})
    csv('autopsy_state_attribution.csv',pd.DataFrame(state)); print('STATES',pd.DataFrame(state).to_string(index=False))
def hypothesis():
    assert not (O/'hypothesis_lock.json').exists()
    write('hypothesis_lock.json',{'locked_at':now(),'hypothesis':'For short investor lookbacks, the frozen correction over-rewards a growth pattern associated with long-lived deeply underwater stocks, despite weaker recent plan returns than displaced champion picks. Missing-field confidence does not detect this interaction. Calibrate the growth inputs in the correction toward contemporaneous query medians, retaining champion growth and realized historical plan return inputs, ATH, risk, goal/user, and missing-evidence shrinkage. This is a reliability experiment, not a proven causal identification.', 'evidence':{'12m_xirr_delta':-.06663069087150725,'12m_drawdown_delta':-.06502649160076093,'growth_median_counterfactual_xirr_delta':.114803,'growth_median_counterfactual_drawdown_delta':-.003798,'entry_evidence_confidence':.998918,'entry_mean_days_since_high':4611.05,'entry_mean_ath_distance':-.911276,'short_history_substitutions':1,'substitutions':231},'candidate_grid':[0,.25,.5],'candidate_parameter':'Retained deviation from the within-decision/profile growth median. Missing inputs stay missing. Only lookback <=12 months is calibrated; all longer lookbacks are byte-equivalent V15 scores. No new model fit or identity rule. Alpha remains .2 times original evidence confidence.', 'rules':json.loads((v.OUT/'protocol_lock.json').read_text())['rules'],'selection':'Highest eligible utility under unchanged V15 development gates; if none eligible, highest utility diagnostic. Ties choose greatest retained growth weight. Exactly three candidates; no expansion after results.', 'development_dates':v.protocol()['development_selection_dates'],'inputs_sha256':{n:v.sha(O/n) for n in ['autopsy_12m_dates.csv','autopsy_12m_substitutions.csv','autopsy_family_ranking_counterfactuals.csv','good_bad_profiles.csv','autopsy_state_attribution.csv']},'current_and_exposed_evaluation_accessed_for_v16_selection':False,'fundamentals_industry':'No valid historical industry/fundamental mapping: unavailable, never backfill current classifications.','limitation':'All profiles have forward horizon12 months; this calibrates investor lookback, not future holding horizon.'})
    write('candidate_definitions.json',{'locked_at':now(),'candidates':[{'name':'growth_retained_'+str(g),'growth_retained':g,'alpha':.2,'base_correction':'frozen V15 balanced_return confidence_only','training':'unchanged maturity-purged V15 models'} for g in [0,.25,.5]]})
def score(x,m,weight):
    z=x.copy(); mask=z.lookback_months.le(12)
    for c in v.FAMILIES['growth']:
        if c not in m.feature_name(): continue
        med=z.groupby(['decision_date','profile_name'])[c].transform('median')
        z.loc[mask,c]=weight*z.loc[mask,c]+(1-weight)*med.loc[mask]
    corr=v.correction(z,m)
    result=v.guided(x,corr,.2)
    if 'v15_score' in x: result.loc[~mask]=x.loc[~mask,'v15_score']
    return result
def development():
    lock=json.loads((O/'hypothesis_lock.json').read_text()); assert not (O/'selection_lock.json').exists()
    x=pd.read_pickle(O/'development.pkl.gz',compression='gzip'); base=v.evaluate(x,'champion_score')
    m=lgb.Booster(model_file=str(v.OUT/'development_balanced_return__confidence_only.txt'))
    rows=[]; tables=[]; details={}
    for g in lock['candidate_grid']:
        name='growth_retained_'+str(g); x['v16_score']=score(x,m,g)
        pair=v.compare_metrics(v.evaluate(x,'v16_score'),base); t=v.turnover(x,'v16_score'); stats=v.eligibility(pair,t)
        rows.append({'candidate':name,'growth_retained':g,'eligible':stats['eligible'],'utility':stats['utility'],**stats['delta']}); details[name]=stats
        tables.append(pair.assign(candidate=name)); print('CANDIDATE',name,json.dumps(v.clean(stats)),flush=True)
    table=pd.DataFrame(rows).sort_values(['eligible','utility','growth_retained'],ascending=[False,False,False]); selected=table.iloc[0].to_dict()
    csv('development_candidates.csv',table); csv('development_all_candidate_profile_date_results.csv',pd.concat(tables)); write('development_gate_details.json',details)
    write('selection_lock.json',{'locked_at':now(),'selected':selected,'details':details[selected['candidate']],'hypothesis_sha256':v.sha(O/'hypothesis_lock.json'),'candidate_definitions_sha256':v.sha(O/'candidate_definitions.json'),'development_results_sha256':v.sha(O/'development_candidates.csv'),'selected_before_current_and_exposed_evaluation':True,'no_2024_2025_or_current_used_for_selection':True})
    x['v16_score']=score(x,m,selected['growth_retained']); ranks(x)
    pair=v.compare_metrics(v.evaluate(x,'v16_score'),base); csv('development_selected_profile_date_results.csv',pair)
    csv('development_profile_summary.csv',pair.groupby('profile',as_index=False)[[c+'_delta' for c in v.METRICS]].mean())
    csv('development_turnover.csv',turns(x)); csv('development_cohorts.csv',cohorts(x))
    csv('development_scores.csv.gz',x[v.KEYS+v.OUTCOME+['champion_score','v15_score','v16_score','champion_rank','v15_rank','v16_rank']])
    csv('development_largest_movers.csv',x.assign(v16_vs_v15=x.v15_rank-x.v16_rank).sort_values('v16_vs_v15',key=lambda c:c.abs(),ascending=False).head(200))
    csv('development_year_summary.csv',pair.assign(year=pair.decision_date.str[:4]).groupby('year',as_index=False)[[c+'_delta' for c in v.METRICS]].mean())
    z=pair.loc[pair.profile.eq('lookback12')]; rng=np.random.default_rng(20261003); boot=[]
    # Year blocks preserve clustered decision dates, but four blocks give wide uncertainty.
    y=z.assign(year=z.decision_date.str[:4]).groupby('year')[[c+'_delta' for c in v.METRICS]].mean()
    for _ in range(2000): boot.append(y.iloc[rng.integers(0,len(y),len(y))].mean().to_dict())
    b=pd.DataFrame(boot); csv('development_12m_year_block_intervals.csv',pd.DataFrame({'metric':b.columns,'p025':b.quantile(.025).values,'p975':b.quantile(.975).values}))
    print('SELECTED',selected,flush=True)
def selected_weight():
    lock=json.loads((O/'selection_lock.json').read_text())
    assert lock['hypothesis_sha256']==v.sha(O/'hypothesis_lock.json')
    assert lock['candidate_definitions_sha256']==v.sha(O/'candidate_definitions.json')
    assert lock['development_results_sha256']==v.sha(O/'development_candidates.csv')
    return lock['selected']['growth_retained']
def current():
    weight=selected_weight()
    source=v.OUT/'current_rankings.csv.gz'; x=pd.read_csv(source,low_memory=False)
    x[v.FEATURES+['evidence_confidence']]=x[v.FEATURES+['evidence_confidence']].astype('float32')
    # Reuse the immutable, audited whole-share feature replay built from V7, not stale September plans.
    facts=pd.read_csv(v.V7,low_memory=False); assert set(x['isin'])==set(facts['isin'])
    inv=json.loads((v.OUT/'input_inventory.json').read_text())
    key=str(v.V7.relative_to(v.ROOT)); assert inv[key]==v.sha(v.V7)
    m=lgb.Booster(model_file=str(v.OUT/'current_model.txt'))
    recomputed=v.guided(x,v.correction(x,m),.2)
    error=float((recomputed-x.v15_score).abs().max()); assert error<1e-8
    x['v16_score']=score(x,m,weight); ranks(x); x['v16_vs_v15']=x.v15_rank-x.v16_rank; x['v16_vs_champion']=x.champion_rank-x.v16_rank
    unchanged=float((x.loc[x.lookback_months.gt(12),'v16_score']-x.loc[x.lookback_months.gt(12),'v15_score']).abs().max()); assert unchanged==0
    csv('current_rankings.csv.gz',x)
    for n in [20,50,100]: csv('current_top'+str(n)+'.csv',x.loc[x.v16_rank.le(n)].sort_values(['profile_name','v16_rank']))
    csv('current_turnover.csv',turns(x)); csv('current_largest_movers.csv',x.sort_values('v16_vs_v15',key=lambda c:c.abs(),ascending=False).head(200))
    compositions=[]; personal=[]
    for model in ['champion','v15','v16']:
        for profile,g in x.groupby('profile_name'):
            top=g.loc[g[model+'_rank'].le(20)]
            compositions.append({'profile':profile,'model':model,'scored':int(g[model+'_rank'].notna().sum()),'missing_true_5y_top20':float(top.has_true_5y.eq(0).mean()),'median_history_months':top.history_months.median(),'median_days_since_high':top.days_since_recorded_high.median(),'mean_distance_high':top.distance_from_recorded_high.mean(),'mean_historical_max_drawdown':top.full_history_max_drawdown.mean(),'median_1y_growth':top.strict_cagr_1y.median(),'median_3y_growth':top.cagr_3y.median(),'mean_volatility':top.realized_volatility_1y.mean(),'mean_confidence':top.evidence_confidence.mean()})
        base=x.loc[x.profile_name.eq('base7500')].set_index('isin')[model+'_rank']
        for profile,g in x.groupby('profile_name'):
            ranks2=g.set_index('isin')[model+'_rank']; common=pd.concat([base.rename('base'),ranks2.rename('other')],axis=1).dropna()
            personal.append({'model':model,'profile':profile,'top20_overlap_with_base':len(set(common.loc[common.base.le(20)].index)&set(common.loc[common.other.le(20)].index)),'mean_absolute_rank_displacement':(common.base-common.other).abs().mean(),'mean_absolute_percentile_change':(common.base.rank(pct=True)-common.other.rank(pct=True)).abs().mean()})
    csv('current_history_ath_growth_risk_composition.csv',pd.DataFrame(compositions)); csv('current_personalization.csv',pd.DataFrame(personal))
    peers=pd.read_csv(v.OUT/'current_peer_fundamental_diagnostics.csv'); industry=x.merge(peers[['isin','industry']],on='isin',validate='many_to_one'); concentration=[]
    for model in ['champion','v15','v16']:
        for (day,profile),g in industry.groupby(['decision_date','profile_name']):
            for n in [20,50,100]:
                top=g.loc[g[model+'_rank'].le(n)]; counts=top.industry.value_counts(normalize=True)
                concentration.append({'profile':profile,'model':model,'top_n':n,'industry_hhi':(counts**2).sum(),'largest_industry':counts.index[0],'largest_share':counts.iloc[0]})
    csv('current_industry_concentration.csv',pd.DataFrame(concentration))
    sh=m.predict(x.loc[x.v16_score.notna(),m.feature_name()],pred_contrib=True,num_threads=4)[:,:-1]
    direction=x.loc[x.v16_score.notna(),v.KEYS+['v16_rank','v15_rank','champion_rank']].copy()
    for family,cs in v.FAMILIES.items():
        inds=[m.feature_name().index(c) for c in cs if c in m.feature_name()]
        direction[family+'_original_correction_shap']=sh[:,inds].sum(axis=1) if inds else 0
    csv('current_original_family_contributions.csv.gz',direction)
    effects=[]
    for f,cs in v.FAMILIES.items():
        if f=='history': continue
        z=x.copy()
        for c in cs:
            if c in m.feature_name(): z[c]=z.groupby(['decision_date','profile_name'])[c].transform('median').where(x[c].notna())
        alt=score(z,m,weight); changed_rank=v.ranked(z.assign(alternative=alt),'alternative')
        # score() copies longer-profile frozen V15 scores; explicitly recompute those for diagnostic perturbations.
        longer=x.lookback_months.gt(12); alt.loc[longer]=v.guided(z,v.correction(z,m),.2).loc[longer]
        changed_rank=v.ranked(z.assign(alternative=alt),'alternative')
        for profile,g in x.groupby('profile_name'):
            idx=g.index; a=set(g.loc[g.v16_rank.le(20),'isin']); b=set(g.loc[changed_rank.loc[idx].le(20),'isin'])
            effects.append({'family':f,'profile':profile,'top20_changed':20-len(a&b),'mean_absolute_rank_displacement':(changed_rank.loc[idx]-g.v16_rank).abs().mean(),'mean_absolute_score_change':(alt.loc[idx]-g.v16_score).abs().mean(),'method':'Within-query median replacement preserving missing inputs; fixed champion score; diagnostic, not causal'})
    csv('current_family_ranking_sensitivity.csv',pd.DataFrame(effects))
    ny=x.loc[x['isin'].eq('INE388Y01029')]; csv('nykaa_diagnostic.csv',ny.merge(peers,on=['isin','ticker','company'],validate='many_to_one'))
    explanation=json.loads((v.OUT/'nykaa_explanation.json').read_text())
    write('nykaa_explanation.json',{'diagnostic_only':True,'v16_base_rank':float(ny.loc[ny.profile_name.eq('base7500'),'v16_rank'].iloc[0]),'v15_reference_explanation':explanation,'rule':'No identity-specific rule; base profile is unchanged V15; lookback12 alone receives selected growth calibration.'})
    # These are current-only diagnostics, never fitted or backfilled historically.
    for n in ['current_peer_fundamental_diagnostics.csv','current_industry_concentration.csv','current_plan_history_audit.csv']:
        (O/('v15_reference_'+n)).write_bytes((v.OUT/n).read_bytes())
    write('current_inference_audit.json',{'completed_at':now(),'selection_lock_sha256':v.sha(O/'selection_lock.json'),'v7_sha256':v.sha(v.V7),'v15_feature_replay_sha256':v.sha(source),'current_model_sha256':v.sha(v.OUT/'current_model.txt'),'v15_reconstruction_max_error':error,'non12m_score_difference':unchanged,'rows':len(x),'scored':int(x.v16_score.notna().sum()),'replay':'Immutable V15 V7 whole-share replay reused and score reproduction verified; no new source acquisition. Current diagnostics only after lock.','action_limitation':'Official ledger ends September18; post-ledger corporate-action completeness not proved. Conditional research only; V15 quarantine preserved.'})
    print('CURRENT COMPLETE',len(x),flush=True)
def exposed():
    weight=selected_weight(); x=v.load_historical(True); dates=sorted(d for d in x.decision_date.unique() if d>='2024-01-01')
    x=x.loc[x.decision_date.isin(dates)].merge(v.benchmark(dates),on=v.KEYS,validate='one_to_one')
    m=lgb.Booster(model_file=str(v.OUT/'evaluation_model.txt')); x['v15_score']=v.guided(x,v.correction(x,m),.2)
    frozen=pd.read_csv(v.OUT/'known_evaluation_scores.csv.gz'); check=x[v.KEYS+['v15_score']].merge(frozen[v.KEYS+['v15_score']],on=v.KEYS,suffixes=('_new','_old'))
    error=float((check.v15_score_new-check.v15_score_old).abs().max()); assert error<1e-8
    x['v16_score']=score(x,m,weight); ranks(x)
    pair=v.compare_metrics(v.evaluate(x,'v16_score'),v.evaluate(x,'champion_score'))
    csv('exposed_2024_2025_profile_date_results.csv',pair); csv('exposed_2024_2025_profile_summary.csv',pair.groupby('profile',as_index=False)[[c+'_delta' for c in v.METRICS]].mean())
    csv('exposed_2024_2025_scores.csv.gz',x[v.KEYS+v.OUTCOME+['champion_score','v15_score','v16_score','champion_rank','v15_rank','v16_rank']]); csv('exposed_2024_2025_turnover.csv',turns(x)); csv('exposed_2024_2025_cohorts.csv',cohorts(x))
    stats=v.eligibility(pair,v.turnover(x,'v16_score'))
    write('exposed_evaluation_audit.json',{'completed_at':now(),'known_exposed_not_blind':True,'not_used_for_selection':True,'selection_lock_sha256':v.sha(O/'selection_lock.json'),'v15_score_reconstruction_max_error':error,'model_sha256':v.sha(v.OUT/'evaluation_model.txt'),'results':stats})
    print('EXPOSED COMPLETE',stats,flush=True)
def supplemental():
    weight=selected_weight(); x=pd.read_pickle(O/'development.pkl.gz',compression='gzip'); m=lgb.Booster(model_file=str(v.OUT/'development_balanced_return__confidence_only.txt')); x['v16_score']=score(x,m,weight)
    csv('development_cohorts_by_profile.csv',pd.concat([cohorts(g).assign(profile=p) for p,g in x.groupby('profile_name')],ignore_index=True))
    csv('development_12m_cohorts.csv',cohorts(x.loc[x.profile_name.eq('lookback12')]))
    ranks(x); selected=x.loc[x.profile_name.eq('lookback12')&(x.champion_rank.le(20)|x.v15_rank.le(20))].copy()
    sh=m.predict(selected[m.feature_name()],pred_contrib=True,num_threads=4)[:,:-1]
    for c in v.FAMILIES['growth']: selected[c+'_original_shap']=sh[:,m.feature_name().index(c)]
    selected['selection']=np.select([selected.champion_rank.le(20)&selected.v15_rank.le(20),selected.v15_rank.le(20)],['retained','promoted'],default='demoted')
    csv('autopsy_growth_feature_contributions.csv',selected.groupby('selection')[[c+'_original_shap' for c in v.FAMILIES['growth']]].mean().reset_index())
    # Post-lock mechanism audit; never used to select or amend the candidate.
    cur=pd.read_csv(O/'current_rankings.csv.gz',low_memory=False); cm=lgb.Booster(model_file=str(v.OUT/'current_model.txt')); cur=cur.loc[cur.v16_score.notna()].copy()
    for c in v.FAMILIES['growth']:
        med=cur.groupby(['decision_date','profile_name'])[c].transform('median'); mask=cur.lookback_months.le(12); cur.loc[mask,c]=med.loc[mask].where(cur.loc[mask,c].notna())
    rows=[]
    for scenario,days,depth in [('recent_near',30,-.05),('old_near',1825,-.05),('recent_deep',30,-.7),('old_deep',1825,-.7)]:
        z=cur.copy(); z['days_since_recorded_high']=days; z['distance_from_recorded_high']=depth; z['current_drawdown_duration_days']=days
        z['old_high_depth']=np.log1p(days/365)*(-depth); z['underwater_depth']=z.old_high_depth; z['recovery_vs_old_high']=z.recovery_from_worst_trough.clip(-1,10)*(-depth)
        pred=cm.predict(z[cm.feature_name()],num_threads=4)
        cur[scenario]=pred
    for profile,g in cur.groupby('profile_name'):
        for scenario in ['old_near','recent_deep','old_deep']:
            diff=g[scenario]-g.recent_near
            rows.append({'profile':profile,'scenario_vs_recent_near':scenario,'raw_correction_mean_change':diff.mean(),'raw_correction_median_change':diff.median(),'negative_fraction':diff.lt(-1e-8).mean(),'method':'Coherent ATH age/depth/duration bundle, fixed other features and champion; synthetic sensitivity, not a realizable portfolio or causal result. Post-lock only.'})
    csv('current_ath_directional_sensitivity.csv',pd.DataFrame(rows))
    write('validation_checks.json',{'completed_at':now(),'selection_unchanged':True,'hypothesis_hash_valid':True,'only_three_candidates':True,'non12m_dev_score_error':float((x.loc[x.lookback_months.gt(12),'v16_score']-x.loc[x.lookback_months.gt(12),'v15_score']).abs().max()),'missing_inputs_preserved_in_growth_calibration':True,'original_evidence_confidence_preserved':True,'short_lookback_growth_signal':'Correction growth levels calibrated; champion carry-XIRR, goal, CAGR3/5 foundation untouched; missingness remains available to correction. This intentionally weakens direct strict1Y/momentum influence only in short-lookback correction.'})
def table(df,cols=None):
    if cols is not None: df=df[cols]
    def val(x):
        if isinstance(x,(float,np.floating)): return f'{x:.4f}' if np.isfinite(x) else 'NA'
        return str(x).replace('|','/')
    return '| '+' | '.join(df.columns)+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(val(x) for x in row)+' |' for row in df.itertuples(index=False,name=None))
def report():
    lock=json.loads((O/'selection_lock.json').read_text()); exp=json.loads((O/'exposed_evaluation_audit.json').read_text()); current_audit=json.loads((O/'current_inference_audit.json').read_text())
    old=pd.read_csv(O/'good_bad_profiles.csv'); new=pd.read_csv(O/'development_profile_summary.csv'); d=pd.read_csv(O/'autopsy_12m_dates.csv'); a=pd.read_csv(O/'autopsy_12m_substitutions.csv'); states=pd.read_csv(O/'autopsy_state_attribution.csv')
    selected_dates=pd.read_csv(O/'development_selected_profile_date_results.csv'); dates=d.merge(selected_dates.loc[selected_dates.profile.eq('lookback12'),['decision_date']+[c+'_delta' for c in v.METRICS]],on='decision_date')
    assert abs(a.median_xirr_attribution.sum()/16-d.xirr_delta.mean())<1e-10
    assert abs(a.drawdown_attribution.sum()/16-d.drawdown_delta.mean())<1e-10
    metrics=[]
    for c in v.METRICS:
        metrics.append({'metric':c,'V15_12m_delta':float(old.loc[old.profile.eq('lookback12'),c+'_delta'].iloc[0]),'V16_12m_delta':float(new.loc[new.profile.eq('lookback12'),c+'_delta'].iloc[0]),'V16_all_profile_delta':lock['details']['delta'][c],'exposed_V16_delta':exp['results']['delta'][c]})
    csv('aggregate_comparison.csv',pd.DataFrame(metrics))
    decision={'verdict':'PROMISING CHALLENGER','replace_d499580':False,'production_champion':'d499580','selected_candidate':lock['selected']['candidate'],'development_gates_pass':lock['details']['eligible'],'12m_return_loss_repaired':True,'12m_drawdown_recovery_fraction':1-float(new.loc[new.profile.eq('lookback12'),'mean_asset_drawdown_top20_delta'].iloc[0])/float(old.loc[old.profile.eq('lookback12'),'mean_asset_drawdown_top20_delta'].iloc[0]),'development_all_other_profiles_unchanged':True,'exposed_supporting_only':True,'no_deployment':True,'limitations':['Wide four-year block intervals include regression','12M June2021 return deficit worsens and March2023 deficit remains','Only 40.14% aggregate development Top20 overlap with champion; gate uses pre-existing high-turnover exception','Current official-action completeness after September18 unproved','No new unexposed validation; frozen research universe and provider-history revision exposure remain'],'completed_at':now()}
    write('decision.json',decision)
    facts=pd.read_csv(v.V7,usecols=['isin','ticker','company']); names=facts.set_index('isin').ticker.to_dict()
    sample=a.nsmallest(12,'drawdown_attribution').copy(); sample['exit_ticker']=sample.exit_isin.map(names); sample['entry_ticker']=sample.entry_isin.map(names)
    csv('autopsy_named_worst_drawdown_substitutions.csv',sample)
    counts={'negative_return_dates':int(d.xirr_delta.lt(0).sum()),'negative_drawdown_dates':int(d.drawdown_delta.lt(0).sum()),'substitutions':int(d.substitutions.sum()),'unique_promoted_isins':int(a.entry_isin.nunique()),'worst3_share_gross_return_losses':-d.nsmallest(3,'xirr_delta').xirr_delta.sum()/-d.loc[d.xirr_delta.lt(0),'xirr_delta'].sum(),'worst3_share_gross_drawdown_losses':-d.nsmallest(3,'drawdown_delta').drawdown_delta.sum()/-d.loc[d.drawdown_delta.lt(0),'drawdown_delta'].sum()}
    write('autopsy_summary.json',{'classification':'B: systematic growth/history interaction, with regime dependence; not proof of a single causal feature','concentration':counts,'median_attribution_method':'512 fixed-seed random permutations of deterministic rank-paired exit/entry substitutions. Paired Shapley approximation; median is nonadditive. Pairing affects attribution; within-date sums reproduce exact observed median delta.','drawdown_attribution_method':'(entrant realized asset drawdown minus exit realized asset drawdown)/20, exact additive contribution. Mean across16 dates.','industry':'No valid historically dated classification mapping was supplied; sector attribution unavailable. Current classifications not backfilled.'})
    family=pd.read_csv(O/'autopsy_family_ranking_counterfactuals.csv'); family=family.loc[family.profile.eq('lookback12')].groupby('ablated_family',as_index=False)[['median_xirr_top20_delta','mean_asset_drawdown_top20_delta','target_shortfall_top20_delta']].mean()
    turnover=pd.read_csv(O/'development_turnover.csv').groupby(['comparison','top_n'],as_index=False)[['overlap_fraction','mean_absolute_rank_movement']].mean()
    ct=pd.read_csv(O/'current_turnover.csv'); composition=pd.read_csv(O/'current_history_ath_growth_risk_composition.csv'); personal=pd.read_csv(O/'current_personalization.csv'); ath=pd.read_csv(O/'current_ath_directional_sensitivity.csv'); intervals=pd.read_csv(O/'development_12m_year_block_intervals.csv')
    text=['# Personalized V16 — 2026-10-03','','## Verdict','','**PROMISING CHALLENGER. Do not replace d499580. No deployment.** V16 repairs the average development 12M failure and passes all unchanged V15 gates, but calendar instability, high turnover, exposed research, and conditional current execution evidence prevent promotion.','',
    '## What failed in V15','','The main diagnosis is **B: a systematic growth/history interaction at short lookbacks**, with regime dependence. It is not just one or two bad accidents, and the evidence does not establish that every part of the 12M correction is unreliable. Of16 development dates,7 lose median XIRR and13 worsen drawdown. There are231 substitutions (14.44 per date), spanning '+str(counts['unique_promoted_isins'])+' promoted ISINs. The worst three dates account for '+f"{counts['worst3_share_gross_return_losses']:.1%}"+' of gross return losses and '+f"{counts['worst3_share_gross_drawdown_losses']:.1%}"+' of gross drawdown losses; gains on other dates offset much of the loss. Thus concentrated return setbacks coexist with broadly worse drawdown.','',
    'Entrants average212 months of history versus146 for exits;4611 days since the high versus2386;91.1% below the high versus48.9%;42.3% annual volatility versus34.5%; and historical maximum drawdown−96.4% versus−67.0%. Entrants have weaker recent whole-share plan XIRR scores (4.86 versus12.19) and1Y growth (83.6% versus427.8%, highly skewed means). Almost all are fully observed: mean confidence99.89%, and only1 of231 entrants has less than60 months of history. Missing-field confidence therefore fails to flag this profile/model interaction. Affordability is not the driver: both groups have essentially100% utilization and zero unaffordable rate.','',
    'The post-lock feature-level mechanism audit confirms that promoted stocks receive most growth-family support from observed5Y (+0.271 average raw TreeSHAP),10Y (+0.109), and7Y (+0.039), while1Y is slightly negative. Demoted picks have observed5Y−0.008 and10Y−0.011. Long-history growth proxies swamp recent plan-return evidence in this profile. TreeSHAP explains model predictions; it is not causal outcome attribution. No identity features are used.','',
    '### Date-by-date autopsy and locked V16 repair','','All deltas are fractions (multiply by100 for percentage points); higher drawdown delta is better. The market growth/volatility columns in the detailed CSV are contemporaneous cross-sectional proxies, not an externally reconstructed benchmark regime.','',table(dates,['decision_date','substitutions','xirr_delta','drawdown_delta','median_xirr_top20_delta','mean_asset_drawdown_top20_delta']),'',
    'V15 return gains during the first three2020 dates do not excuse their drawdown losses. The2021Q4–2022Q2 losses are consecutive, and2023Q1 also loses75.36pp of median XIRR. This is consistent with regime-dependent generalization failure; regime causation is not proved.','',
    '### Stock substitutions and attribution','','Full champion and V15 Top20 lists are in `autopsy_12m_top20.csv`; every entry/exit pair, realized return/drawdown, ranks, and pre-decision feature state is in `autopsy_12m_substitutions.csv`. Drawdown contribution is exactly additive. Median-XIRR attribution uses512 fixed-seed permutation orders over deterministic rank-paired substitutions; paired attribution is approximate and depends on pairing, but its sum reproduces each exact date delta. It is not a claim that one stock independently caused that amount. The table shows the twelve worst drawdown pairs; ticker labels were attached after selection for readability and do not establish historical industry membership.','',table(sample,['decision_date','exit_ticker','entry_ticker','exit_xirr','entry_xirr','drawdown_attribution','median_xirr_attribution']),'',
    '### Feature-state concentration','','Attributions below are mean-date contributions. States overlap and must not be summed. High volatility uses the entrant distribution upper quartile in this descriptive table; robustness cohorts use within-query universe upper quartiles.','',table(states),'',
    'Historical sector/industry attribution is unavailable: no valid dated industry-membership source was supplied. Current industry concentration is separately available and was never backfilled into development.','',
    '### Actual ranking counterfactuals','','The frozen V15 model was reranked after replacing each correlated family with query medians. This is a diagnostic, not a refit or causal experiment. Diagnostic replacement fills missing values; the selected V16 implementation explicitly preserves missing values, hence its result differs from the diagnostic.','',table(family),'',
    'Removing risk makes12M return and drawdown worse. Removing ATH improves return but leaves drawdown worse (−7.23pp); removing goal/user changes little of the drawdown loss. Growth-family neutralization is the only tested family diagnostic that improves both clearly. Therefore neither a broad defensive shift nor removing ATH is justified.','',
    '## Good versus bad profiles','','All nine profiles have the same12-month forward horizon. Lookback12/36/60 are investor observation windows, not different investment horizons. V15 improves median return in every profile except lookback12. Promoted-stock mean raw growth SHAP is+0.395 at12M versus+0.167 for base7500 and+0.104 at60M; ATH support is+0.201 versus+0.141 and+0.158. Actual promoted and demoted stock rows and goal/affordability states are retained in `autopsy_all_profile_stock_behavior.csv.gz` and `autopsy_profile_selection_composition.csv`. Different recent plan-return inputs and their interaction with long-history growth are more consistent with the evidence than missing-data sparsity.','',table(old,['profile','median_xirr_top20_delta','mean_asset_drawdown_top20_delta','target_shortfall_top20_delta','ndcg20_delta']),'',
    '## Hypothesis, minimum change, and selection','','`hypothesis_lock.json` and `candidate_definitions.json` were written before any V16 candidate evaluation. Exactly three retained-growth weights were tested:0,0.25,0.5. No new model training, feature search, stock rule, NYKAA target, or exposed-period tuning occurred. The same maturity-purged V15 model files are reused. All original gates and the utility were retained. Weight0 was the only eligible candidate; weights0.25 and0.5 still failed the12M drawdown gate. No grid expansion followed.','',
    'For each growth input c at lookback<=12, replace its observed value by `g*c + (1-g)*within_query_median(c)`; preserve NaN. Use the original eight-field evidence confidence and the original20% maximum champion-guided correction. Selected g=0. All longer-lookback scores are exactly V15. Champion carry-XIRR, goal, CAGR3/5, affordability, and price-drawdown foundation are unchanged. ATH, risk, and goal/user correction inputs are unchanged. This deliberately removes cross-sectional growth-level differentiation from the short-lookback correction, while keeping growth in the champion foundation; it is not a claim that growth is irrelevant. Missingness can still affect tree paths, but there is no prescribed missing-history score subtraction.','',
    '## Locked development results','','Mean across16 dates per profile, then nine equally weighted profiles; not a pooled-stock median or a20-stock shared-budget portfolio. Independent SIP plans retain the existing execution/label definitions.','',table(pd.DataFrame(metrics)),'',table(new,['profile','median_xirr_top20_delta','mean_asset_drawdown_top20_delta','target_shortfall_top20_delta','ndcg20_delta']),'',
    '12M median-XIRR delta rises−6.66→+5.44pp; drawdown delta improves−6.50→−0.84pp, recovering87.0% of the disadvantage. Achievement rises−1.25→+0.94pp and shortfall switches+0.64→−0.65pp. Aggregate return improves18.53pp, achievement4.97pp, shortfall2.15pp, and drawdown1.11pp versus champion. Weekly and the other seven longer-lookback profiles are exactly V15, so this fix introduces no new profile regression there.','',
    '**The repair is uneven.** June2021’s12M return deficit worsens from−53.76 to−96.74pp; March2023 remains−75.36pp. The12M drawdown average passes the−1pp tolerance by only0.16pp. Four-year block bootstrap intervals include regression; these are descriptive intervals from only four dependent calendar blocks, not proof of statistical superiority.','',table(intervals),'',
    'Robustness outputs cover every profile and short/full history, high volatility, deep drawdown, deep ATH, old ATH, and recent ATH. See `development_cohorts_by_profile.csv` and `development_12m_cohorts.csv`. Within-cohort Top20 metrics differ from shares and outcomes of cohorts inside the overall Top20; both are reported. Aggregate high-volatility within-cohort drawdown is slightly worse than champion; recent-ATH within-cohort median return is slightly worse. These shared V15 weaknesses were not erased by an average repair.','',
    '## Turnover','','V16 is targeted relative to V15: aggregate development Top20 overlap93.89%;94.47% for50 and95.51% for100. Within12M alone, Top20 overlap with V15 is45.0%, so the local repair is substantial. Relative to champion, aggregate Top20 overlap remains only40.14%, using the unchanged high-turnover exception (NDCG gain>=0.03 and shortfall improvement>=0.02). It is not low-turnover in absolute terms.','',table(turnover),'',
    '## Current V7 research inference — after selection lock','','The immutable V15 whole-share V7 replay was reused and its model scores reproduced to floating-point precision before applying V16. The V7 file hash and the feature-replay/model hashes are recorded. This uses the fresh V7/Yahoo feature and plan replay, not the stale September plan rows.29,295 rows are scored across39,924 company/profile rows; original quarantine is preserved. Official action authority ends September18, and absence of later non-split actions is not proved. Current outputs remain conditional research.','',table(ct.loc[ct.profile.isin(['base7500','lookback12'])],['profile','comparison','top_n','overlap','mean_absolute_rank_movement']),'',
    'Base7500 remains V15: champion overlap12/20,28/50,61/100; V15/V16 overlap100%. Current12M V16/V15 overlap15/20,31/50,73/100. Full rankings include all three scores/ranks; Top20/50/100 and largest movers are saved for all profiles.','',table(composition.loc[composition.profile.isin(['base7500','lookback12'])]),'',
    'Base Top20 missing true Yahoo5Y remains65% (champion85%). Current12M missing5Y is85% in V16 versus80% V15 and65% champion: the fix does not hard-filter young stocks, but history quality still needs attention. Current12M median1Y growth rises58.95→68.20%, median days since high falls344.5→29.5, and mean historical maximum drawdown improves−68.29→−64.78%. These are input composition diagnostics, not future outcome evidence. Current industry concentration and peer fundamentals are diagnostic only.','',
    '### ATH and user behavior survive','','Current median-family sensitivity reranks stocks and changes the ATH-family Top20; growth calibration leaves the other feature families active. A post-lock synthetic ATH age/depth/duration audit compares30 days/5% below high with1825 days/70% below high, recomputing derived ATH depth fields while fixing all other inputs. The current12M raw correction declines for100% of scored rows, median−0.0882; base declines for99.88%, median−0.0836. This supports meaningful negative old/deep evidence without an identity or automatic rejection rule. It is a synthetic sensitivity, not a causal experiment; specific stocks can have positive ATH SHAP conditional on their other features.','',table(ath.loc[ath.profile.isin(['base7500','lookback12'])],['profile','scenario_vs_recent_near','raw_correction_median_change','negative_fraction']),'',
    'User personalization remains: current lookback12/base overlap8/20 and60M/base1/20. Amount, frequency, and target changes retain the existing distinct rankings. Direct goal/user family replacement changes current Top20, and growth calibration does not wash out the user input features.','',table(personal.loc[personal.model.eq('v16')]),'',
    '### NYKAA diagnostic only','','Base ranks: frozen September champion1; refreshed champion5; V15=V16=6; prior V14 reference213. No targeted rank was sought. Trusted current growth is35.06%1Y and30.60%3Y; true5Y is unavailable. It is21.80% below its recorded high, with1765 days since high and underwater. Annual volatility27.75%, downside17.05%; plan attainment1.21, historical goal-window achievement75%, utilization99.96%, confidence87.5%. Strong recent return and goal fit maintain the champion foundation. Original correction raw family SHAP is ATH+0.07995, growth−0.01453, risk−0.04070, and goal/user−0.04283: the model does not impose blanket rejection for an old high. Current ROCE17.23%, ROE15.29%, both about87th percentile among15 E-Retail/E-Commerce peers;3Y growth about85th percentile among69 Retailing names. Fundamentals/peers do not cause its trained score. Detailed features and ranks for every user profile are in the NYKAA artifacts.','',
    '## Exposed2024–2025 supporting evidence','','This period was already known in earlier research. It was accessed for V16 only after the selection lock; it is not blind validation and was not used for tuning. Aggregate median-XIRR delta+18.99pp, achievement+11.06pp, shortfall−2.85pp, drawdown+3.23pp, NDCG+0.07975.12M return+30.37pp and drawdown+5.91pp. Every unchanged development gate passes here, but these results do not authorize promotion. Full profile/date, cohort, score, and turnover outputs are saved separately under `exposed_2024_2025_*`.','',
    '## Integrity and evidence limits','','No V14, V15, frozen champion, tracked production/website, or Railway configuration was edited; no deployment or service write occurred. Protected artifacts are hashed before and verified after the experiment in `integrity_audit.json`. No current V7 values or current fundamentals/classifications enter historical rows. Historical score inputs use dated price windows; reused correction fits are maturity-purged before2020-03-31 for development and2024-03-31 for exposed evaluation; current fit labels mature before2026-10-03. Champion historical comparisons use maturity-purged refits of its frozen recipe rather than applying future2026 weights backward.','',
    'This is not proof of a fully unbiased point-in-time investment study: the frozen research universe retains survivorship/selection exposure, provider revisions and historical publication availability are not fully proved, overlapping12-month labels correlate dates, and current post-ledger action completeness is conditional. No identity feature or NYKAA rule exists. All three candidates and selection rules were locked before current/exposed evaluation. The post-lock feature/ATH audits did not alter selection.','',
    '## Reproduction and artifacts','','See `REPRODUCE.md`. The runner writes only V16 artifacts and this report. `manifest.json` covers the runner, report, locks, results, and audit files. Protected inputs are recorded separately. The completed experiment is frozen: reproduce in a separate checkout/output directory; do not overwrite locks.','',
    '## Answers','','**Why did V15 fail?** At12M, its correction strongly promoted long-history, deeply underwater names through5Y/7Y/10Y growth signals, displacing stronger recent plan-return picks. High observed-field confidence did not detect the mismatch; losses were regime-dependent and drawdown deterioration broad.','',
    '**What changed?** Only short-lookback correction growth levels are calibrated to query medians; NaNs, original confidence, champion foundation, ATH, risk, and user-goal inputs are preserved.','',
    '**Did it fix the problem?** It repairs the average return loss and87% of the drawdown disadvantage, passes the locked gates, and leaves the other eight profiles unchanged. It does not fix every date or eliminate all cohort/turnover risks.','',
    '**Does it deserve to replace d499580?** No. It is a promising research challenger requiring unexposed validation and stronger execution evidence before replacement.']
    R.write_text('\n'.join(text)+'\n',encoding='utf-8')
    instructions='''# Reproduce V16\n\nFrozen research experiment: do not rerun into the completed output root. Use a separate checkout/output root. Python3.13 with pandas, numpy, lightgbm, scipy and sklearn from the recorded environment. No remote service calls are required.\n\nStages (in order, from repository root):\n\n```powershell\npython research/runners/personalized_v16_20261003.py autopsy\npython research/runners/personalized_v16_20261003.py inspect\npython research/runners/personalized_v16_20261003.py hypothesis\npython research/runners/personalized_v16_20261003.py development\npython research/runners/personalized_v16_20261003.py current\npython research/runners/personalized_v16_20261003.py exposed\npython research/runners/personalized_v16_20261003.py supplemental\npython research/runners/personalized_v16_20261003.py report\npython research/runners/personalized_v16_20261003.py audit\n```\n\nAutopsy reconstructs frozen V15 development scores and checks all metric deltas (<1e-10). Attribution uses exactly the same labeled eligibility as ranking_metrics. Inspect adds development-only selection behavior and feature-state attribution. Hypothesis writes the immutable three-candidate grid and unchanged V15 gates before candidates. Development locks selection before current/exposed access. Current reuses the immutable audited V15 replay from the exact V7 file; restores original float32 feature/confidence types and verifies V15 score reproduction. Exposed reuses frozen maturity-purged V15 evaluation model; never refits or tunes. Supplemental is post-lock mechanism/robustness diagnostics only. Audit checks protected hashes and creates manifest.\n\nInputs: frozen V15 runner/models/protocol and current V7 replay; V12 prepared panel, raw historical panel, V14 dated historical growth and maturity-purged champion benchmark scores. No edits to these inputs. Model dependencies and exact hashes are recorded in input_inventory.json and protected_before.json; V15 remains a required read-only dependency. Median attribution is paired and uses512 seeded permutation orders, seed20261003. Year bootstrap uses2000 four-year block resamples with the same seed.\n\nHistorical fundamentals/industries unavailable; no current backfill. All horizons12 months; lookback12/36/60 differ. Known2024–2025 is exposed supporting evidence only. Production remains d499580, no deployment.\n'''
    (O/'REPRODUCE.md').write_text(instructions,encoding='utf-8')
    inputs=[v.PREP,v.PANEL,v.V7,v.V14/'historical_growth.csv.gz',v.OUT/'current_rankings.csv.gz',v.OUT/'protocol_lock.json',v.OUT/'development_balanced_return__confidence_only.txt',v.OUT/'evaluation_model.txt',v.OUT/'current_model.txt',v.ROOT/'research/runners/personalized_v15_20261003.py']+[v.V12/n for n in ['development_winner_scores.csv.gz','postlock_2024_diagnostics_scores.csv.gz','untouched_final_2025_scores.csv.gz','postfinal_2025_diagnostics_scores.csv.gz']]
    write('input_inventory.json',{str(p.relative_to(v.ROOT)):v.sha(p) for p in inputs})
    write('software_versions.json',{'python':sys.version,'numpy':np.__version__,'pandas':pd.__version__,'lightgbm':lgb.__version__})
    print('REPORT COMPLETE',decision,flush=True)
if __name__=='__main__': globals()[sys.argv[1]]()
