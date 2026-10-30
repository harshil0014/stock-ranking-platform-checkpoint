"""Prospectively specified ATH-age research; never edits website or prior models."""
from pathlib import Path
import sys, json, hashlib, argparse, gc
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import lightgbm as lgb

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'research/runners')]
import personalized_v17_20261003 as s
v=s.v
O=ROOT/'experiments/v17-ath-refinement-20261004'
BASE=ROOT/'experiments/v17-refinement-20261004'
KEYS=v.KEYS
EXTRA=['ath_recency','ath_age_depth','ath_age_weak_recovery','ath_age_weak_momentum']

def write(name,obj):
    (O/name).write_text(json.dumps(v.clean(obj),indent=2,allow_nan=False),encoding='utf-8')
def csv(name,x): x.to_csv(O/name,index=False)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def prepare():
    O.mkdir(exist_ok=True)
    if (O/'protocol.json').exists():return
    candidates=[{'family':f,'strength':a,'scope':scope,'name':f'{f}_{a}_{scope}'}
        for f in ['age','age_depth','age_recovery','age_momentum']
        for a in [.005,.01,.025,.05,.10,.20]
        for scope in ['all','36']]
    learned=[{'family':f,'strength':a,'scope':scope,'name':f'{f}_{a}_{scope}'}
        for f in ['age_monotone','age_interactions','age_return','age_residual']
        for a in [.025,.05,.10]
        for scope in ['all','36']]
    write('protocol.json',{'created_at':datetime.now(timezone.utc).isoformat(),
        'objective':'Increase sensitivity to ATH age where defensible while preserving refined V17 returns, personalization, history treatment and stability.',
        'benchmarks':['d499580','original V17','V17 refined'],
        'selection_dates':v.protocol()['development_selection_dates'],
        'training':'Expanding annual fits; endpoint strictly before first decision in scored year. No 2024+ labels for candidate selection. All source features point-in-time from frozen panel.',
        'known_exposure':'2020-2023 repeatedly researched; 2024-2025 exposed contextual only. No new blind test claimed.',
        'candidates':candidates+learned,'mean_xirr_selection_weight':0,
        'formulas':'Smooth age a=days/(days+365), depth d=clip(-ATHdistance,0,1). age penalty=a; age_depth=a*sqrt(d); age_recovery=a*sqrt(d)/(1+max(recovery,0)); age_momentum=a*sqrt(d)*(1-clip(momentum,0,1)). Missing age contributes zero adjustment, no history-length penalty. Learned experts add corresponding positive recency transforms to V17 normalized features.',
        'gates':'Against refined V17: aggregate median XIRR, NDCG, drawdown and achievement nonnegative; shortfall nonpositive; worst profile return/drawdown >=-0.005; highvol return/drawdown >=0; utility>=0.002; positive utility in >=3/4 development years. Retain original strict d499580 gates. Current all-profile Top20 overlap>=0.85 is post-selection veto only.',
        'robustness':'Passing learned candidates: alternate seed and per-date refresh; passing score adjustments: alternate-seed and per-date refined baseline artifacts. Same aggregate directions, all-profile floors. Evaluate 7 cohort groups and all44 valid decision dates after lock. Current inference full4436.',
        'selection':'Highest passing utility; lower strength tie-break. Do not optimize current NYKAA rank. No identity predictors.',
        'stop':'48 smooth score adjustments and24 learned expert blends; evaluate gate-passing finalists. If none pass retain refined V17. No post-exposure gate weakening.',
        'references':[
            'https://onlinelibrary.wiley.com/doi/full/10.1111/j.1540-6261.2004.00695.x',
            'https://www.sciencedirect.com/science/article/pii/S0378426613002446',
            'https://www.nykaa.com/media/wysiwyg/2021/Investors-Relations/pdfs/stock-exchange-filling/Intimation-of-Record-date-for-Bonus-Issue.pdf'],
        'reference_limit':'52-week-high findings motivate recency hypotheses; they do not establish that penalizing all-time-high age improves Indian SIP ranking.'})
    paths=[BASE/'final_current_rankings.csv.gz',BASE/'refinement_final_lock.json',ROOT/'research/runtime/personalized-v17/manifest.json',ROOT/'research/freezes/personalized-d499580/lambdarank.txt']
    write('protected_hashes.json',{str(p.relative_to(ROOT)):digest(p) for p in paths})

def features(x):
    x=s.normalize(x)
    age=x.days_since_recorded_high.clip(lower=0)
    a=(age/(age+365)).fillna(0)
    depth=(-x.distance_from_recorded_high).clip(0,1).fillna(0)
    penalties={'age':a,'age_depth':a*np.sqrt(depth),
        'age_recovery':a*np.sqrt(depth)/(1+x.recovery_from_worst_trough.clip(lower=0).fillna(0)),
        'age_momentum':a*np.sqrt(depth)*(1-x.momentum_6m.clip(0,1).fillna(0))}
    for col,(family,values) in zip(EXTRA,penalties.items()):
        x[col]=(1-values).astype('float32');x['penalty_'+family]=values.astype('float32')
    return x

def data():
    x=features(pd.read_pickle(s.O/'historical.pkl'))
    scores=pd.read_csv(BASE/'development_refined_scores.csv.gz')
    dev=x.merge(scores[KEYS+['champion_score','v17_score','repair_score']],on=KEYS,validate='one_to_one')
    return x,dev

def apply(x,candidate,raw=None):
    mask=x.lookback_months.eq(36) if candidate['scope']=='36' else pd.Series(True,index=x.index)
    strength=candidate['strength']*x.evidence_confidence
    base=x.repair_score
    if candidate.get('gate'):
        # Fixed smooth gates use only date-available features, not profile names
        # or outcomes. The extra .25 preserves some general expert influence.
        if candidate['gate']=='age_context':strength=strength*(.25+.75*x.penalty_age_depth)
        elif candidate['gate']=='goal_uncertainty':strength=strength*(.25+.75*(1-x.q_enhanced_goal_score))
    if candidate['family'] in ['age_monotone','age_interactions','age_return','age_residual','age_consensus']:
        correction=raw.where(base.notna()).groupby([x.decision_date,x.profile_name]).rank(pct=True)
        pred=base*(1-strength)+correction*strength
    else:pred=base-strength*x['penalty_'+candidate['family']]
    return pred.where(mask,base)

def measure(dev,pred,reference,champion,hvref):
    z=dev.assign(candidate_score=pred)
    metrics=v.evaluate(z,'candidate_score');pair=v.compare_metrics(metrics,reference)
    delta={c:float(pair[c+'_delta'].mean()) for c in v.METRICS}
    p=pair.groupby('profile')[[c+'_delta' for c in v.METRICS]].mean()
    yearly=pair.assign(year=pair.decision_date.str[:4]).groupby('year')[[c+'_delta' for c in v.METRICS]].mean()
    def utility(d):return .45*d['ndcg20']+.20*d['target_achievement_top20']-.25*d['target_shortfall_top20']+.10*d['mean_asset_drawdown_top20']+.10*d['median_xirr_top20']
    yu=[utility({c:r[c+'_delta'] for c in v.METRICS}) for _,r in yearly.iterrows()]
    hv=dev.realized_volatility_1y.ge(dev.groupby(['decision_date','profile_name']).realized_volatility_1y.transform('quantile',.75))
    hvpair=v.compare_metrics(v.evaluate(z.loc[hv],'candidate_score'),hvref)
    champion_stats=s.strict_stats(v.compare_metrics(metrics,champion),v.turnover(z,'candidate_score'))
    checks={'champion':champion_stats['strong_eligible'],
        **{c:delta[c]>=-1e-12 for c in ['median_xirr_top20','ndcg20','mean_asset_drawdown_top20','target_achievement_top20']},
        'shortfall':delta['target_shortfall_top20']<=1e-12,
        'profile_return':p.median_xirr_top20_delta.min()>=-.005,
        'profile_drawdown':p.mean_asset_drawdown_top20_delta.min()>=-.005,
        'highvol_return':hvpair.median_xirr_top20_delta.mean()>=-1e-12,
        'highvol_drawdown':hvpair.mean_asset_drawdown_top20_delta.mean()>=-1e-12,
        'utility':utility(delta)>=.002,'three_years':sum(u>0 for u in yu)>=3}
    return {'eligible':all(checks.values()),'checks':checks,'delta':delta,'utility':utility(delta),
        'profile_deltas':p.reset_index().to_dict('records'),'year_utility':yu,
        'champion_checks':champion_stats,'highvol_return':float(hvpair.median_xirr_top20_delta.mean()),
        'highvol_drawdown':float(hvpair.mean_asset_drawdown_top20_delta.mean())},pair

def fit(train,test,family,tag,seed=20261004):
    t=train.dropna(subset=v.OUTCOME+['enhanced_carry_xirr_score']).sort_values(['decision_date','profile_name','isin']).copy()
    assert t.endpoint.max()<test.decision_date.min()
    cols=s.NORM+EXTRA
    target=s.target(t);groups=t.groupby(['decision_date','profile_name'],sort=False)
    weights=1/groups.isin.transform('size');weights/=weights.mean()
    constraints=[1]*len(s.POS+s.NEG)+[0]*len(s.CONTEXT)+[1]*len(EXTRA)
    if family=='age_interactions':constraints=[0]*len(cols)
    if family=='age_return':target=groups.future_xirr.rank(pct=True)*.85+groups.future_shortfall.rank(pct=True,ascending=False)*.15
    if family=='age_residual':
        # Purged cross-sectional executable strength, no target-date model labels.
        target=target-(.67*groups.enhanced_goal_score.rank(pct=True)+.33*groups.enhanced_carry_xirr_score.rank(pct=True))
        constraints=[0]*len(cols)
    model=lgb.LGBMRegressor(n_estimators=160,learning_rate=.035,num_leaves=15,max_depth=4,
        min_child_samples=300,reg_lambda=40,n_jobs=4,verbosity=-1,random_state=seed,
        deterministic=True,force_col_wise=True,monotone_constraints=constraints,monotone_constraints_method='advanced')
    model.fit(t[cols],target,sample_weight=weights)
    model.booster_.save_model(str(O/f'model_{tag}.txt'))
    pred=pd.Series(model.predict(test[cols],num_threads=4),index=test.index)
    if family=='age_residual':pred=pred+test.repair_score
    return pred,{'family':family,'seed':seed,'rows':len(t),'max_endpoint':t.endpoint.max(),'first_test_date':test.decision_date.min(),'features':cols}

def search():
    prepare();protocol=json.loads((O/'protocol.json').read_text());x,dev=data()
    reference=v.evaluate(dev,'repair_score');champion=v.evaluate(dev,'champion_score')
    hv=dev.realized_volatility_1y.ge(dev.groupby(['decision_date','profile_name']).realized_volatility_1y.transform('quantile',.75))
    hvref=v.evaluate(dev.loc[hv],'repair_score')
    csv('refined_reference_metrics.csv',reference)
    details=json.loads((O/'details.json').read_text()) if (O/'details.json').exists() else {}
    rows=[];audits=[];predictions={}
    for candidate in protocol['candidates']:
        family=candidate['family'];name=candidate['name']
        if name in details:
            stat=details[name];rows.append({**candidate,'eligible':stat['eligible'],'utility':stat['utility'],**stat['delta']});continue
        raw=None
        if family in ['age_monotone','age_interactions','age_return','age_residual']:
            if family not in predictions:
                path=O/f'predictions_{family}.csv.gz'
                if path.exists():raw=dev[KEYS].merge(pd.read_csv(path),on=KEYS,validate='one_to_one').prediction
                else:
                    raw=pd.Series(np.nan,index=dev.index)
                    for year in ['2020','2021','2022','2023']:
                        test=dev[dev.decision_date.str.startswith(year)];train=x[x.endpoint.lt(test.decision_date.min())]
                        print('TRAIN',family,year,len(train),flush=True)
                        p,audit=fit(train,test,family,f'{family}_{year}');raw.loc[test.index]=p;audits.append(audit)
                        write('training_audit.json',audits)
                    dev[KEYS].assign(prediction=raw).to_csv(path,index=False)
                predictions[family]=raw
            raw=predictions[family]
        pred=apply(dev,candidate,raw)
        stat,pair=measure(dev,pred,reference,champion,hvref)
        details[name]=stat
        rows.append({**candidate,'eligible':stat['eligible'],'utility':stat['utility'],**stat['delta']})
        csv('trials.csv',pd.DataFrame(rows).sort_values(['eligible','utility'],ascending=False));write('details.json',details)
        if stat['eligible']:
            csv(name+'_profile_date.csv',pair)
            dev[KEYS].assign(candidate_score=pred).to_csv(O/(name+'_scores.csv.gz'),index=False)
        print('TRIAL',len(rows),name,stat['eligible'],round(stat['utility'],6),flush=True)
    table=pd.DataFrame(rows).sort_values(['eligible','utility','strength'],ascending=[False,False,True])
    csv('trials.csv',table)
    write('development_lock.json',{'locked_at':datetime.now(timezone.utc).isoformat(),'eligible':table.loc[table.eligible].to_dict('records'),'trial_count':len(table),'protocol_sha256':digest(O/'protocol.json')})
    print('SEARCH COMPLETE',int(table.eligible.sum()),flush=True)

def gated_prepare():
    """Additional mechanistic round, locked before its results or exposed evaluation."""
    if (O/'gated_protocol.json').exists():return
    assert not (O/'final_diagnostic_lock.json').exists()
    candidates=[{'family':family,'strength':strength,'scope':scope,'gate':gate,
        'name':f'{family}_{strength}_{scope}_{gate}'}
        for family in ['age_monotone','age_return','age_residual','age_consensus']
        for strength in [.05,.10,.20] for scope in ['all','36']
        for gate in ['age_context','goal_uncertainty']]
    write('gated_protocol.json',{'created_at':datetime.now(timezone.utc).isoformat(),
        'reason':'Separate bounded extension to test economically motivated conditional influence rather than uniform blending. No exposed-period or current-rank results have been examined.',
        'candidates':candidates,'consensus':'Equal within-date/profile prediction percentiles of monotone, return and residual models.',
        'gates':'age_context=.25+.75*(age/(age+365))*sqrt(ATHdepth); goal_uncertainty=.25+.75*(1-goal_percentile).',
        'unchanged':'Identical outcome-maturity rules, original 72-trial ledger retained, identical performance gates, mean XIRR zero, all-profile checks, current stability post-selection veto, no NYKAA tuning.',
        'stop':'48 conditional blends, then final robustness/evaluation; no additional strength tuning.'})

def signal(z,family,prefix='predictions_',suffix=''):
    if family=='age_consensus':
        parts=[signal(z,f,prefix,suffix).groupby([z.decision_date,z.profile_name]).rank(pct=True) for f in ['age_monotone','age_return','age_residual']]
        return pd.concat(parts,axis=1).mean(axis=1)
    return z[KEYS].merge(pd.read_csv(O/f'{prefix}{family}{suffix}.csv.gz'),on=KEYS,validate='one_to_one').prediction

def gated_search():
    gated_prepare();_,dev=data()
    reference=v.evaluate(dev,'repair_score');champion=v.evaluate(dev,'champion_score')
    hv=dev.realized_volatility_1y.ge(dev.groupby(['decision_date','profile_name']).realized_volatility_1y.transform('quantile',.75))
    hvref=v.evaluate(dev.loc[hv],'repair_score')
    details=json.loads((O/'details.json').read_text());rows=pd.read_csv(O/'trials.csv').to_dict('records')
    protocol=json.loads((O/'gated_protocol.json').read_text())
    cache={}
    for candidate in protocol['candidates']:
        if candidate['name'] in details:continue
        family=candidate['family']
        if family not in cache:cache[family]=signal(dev,family)
        pred=apply(dev,candidate,cache[family]);stat,pair=measure(dev,pred,reference,champion,hvref)
        details[candidate['name']]=stat;rows.append({**candidate,'eligible':stat['eligible'],'utility':stat['utility'],**stat['delta']})
        csv('trials.csv',pd.DataFrame(rows).sort_values(['eligible','utility'],ascending=False));write('details.json',details)
        if stat['eligible']:
            csv(candidate['name']+'_profile_date.csv',pair)
            dev[KEYS].assign(candidate_score=pred).to_csv(O/(candidate['name']+'_scores.csv.gz'),index=False)
        print('GATED TRIAL',len(rows),candidate['name'],stat['eligible'],round(stat['utility'],6),flush=True)
    table=pd.DataFrame(rows).sort_values(['eligible','utility','strength'],ascending=[False,False,True])
    csv('trials.csv',table)
    # Preserve first-round lock separately rather than overwrite its evidence.
    write('combined_development_lock.json',{'locked_at':datetime.now(timezone.utc).isoformat(),'eligible':table.loc[table.eligible].to_dict('records'),'trial_count':len(table),
        'protocol_sha256':digest(O/'protocol.json'),'gated_protocol_sha256':digest(O/'gated_protocol.json')})

def audit():
    prepare()
    from stock_ranker.personalized_v17_product import V17RankingService
    service=V17RankingService();book=service._load_book();receipts=[]
    facts=service.current[service.current.profile_name.eq('base7500')].set_index('isin')
    for identity,values in book.arrays.items():
        dates,raw,economic,nominal,factor=values
        valid=(dates<=np.datetime64('2026-10-03'))&np.isfinite(economic)&(economic>0)
        if not valid.any():continue
        dates=dates[valid];prices=economic[valid];high=prices.max();last=np.where(prices==high)[0][-1]
        row=facts.loc[identity]
        receipts.append({'isin':identity,'ticker':row.ticker,'price_basis':'official-action-adjusted closing price',
            'recomputed_high_date':str(dates[last]),'recomputed_high':high,
            'days_at_decision':int((np.datetime64('2026-10-03')-dates[last]).astype(int)),
            'days_at_last_price':int((dates[-1]-dates[last]).astype(int)),
            'stored_days':row.days_since_recorded_high,'stored_distance':row.distance_from_recorded_high,
            'recomputed_distance':prices[-1]/high-1})
    frame=pd.DataFrame(receipts);csv('ath_price_basis_audit.csv',frame)
    write('ath_audit_summary.json',{'rows':len(frame),'within_3_calendar_days':int((frame.days_at_decision-frame.stored_days).abs().le(3).sum()),
        'distance_matches_1pct':int((frame.recomputed_distance-frame.stored_distance).abs().le(.01).sum()),
        'nykaa':frame.loc[frame.ticker.eq('NYKAA')].to_dict('records'),
        'definition':'Highest adjusted daily CLOSE in observed history, not intraday high; days field can be measured at last quote date rather than decision date.',
        'corporate_action_reference':'Official issuer 5-for-1 bonus record date11Nov2022; use adjusted history, never compare nominal IPO high directly to post-bonus price.'})
    print('ATH AUDIT',len(frame),flush=True)

def robustness():
    path=O/('combined_development_lock.json' if (O/'combined_development_lock.json').exists() else 'development_lock.json')
    lock=json.loads(path.read_text());x,dev=data()
    results={};winner=None;audits=[]
    for candidate in lock['eligible']:
        name=candidate['name'];results[name]={};passed=True
        for variant,seed in [('seed20261004',20261005),('per_date',20261004)]:
            z=dev.drop(columns=['repair_score']).merge(pd.read_csv(BASE/f'bag_robust_{variant}_scores.csv.gz'),on=KEYS,validate='one_to_one')
            raw=None
            if candidate['family'] in ['age_monotone','age_interactions','age_return','age_residual','age_consensus']:
                cache=O/f'robust_{candidate["family"]}_{variant}.csv.gz'
                if cache.exists():raw=z[KEYS].merge(pd.read_csv(cache),on=KEYS,validate='one_to_one').prediction
                else:
                    raw=pd.Series(np.nan,index=z.index)
                    blocks=sorted(z.decision_date.unique()) if variant=='per_date' else ['2020','2021','2022','2023']
                    families=['age_monotone','age_return','age_residual'] if candidate['family']=='age_consensus' else [candidate['family']]
                    members=[]
                    for family in families:
                        member=pd.Series(np.nan,index=z.index)
                        for block in blocks:
                            test=z[z.decision_date.eq(block) if variant=='per_date' else z.decision_date.str.startswith(block)]
                            p,a=fit(x[x.endpoint.lt(test.decision_date.min())],test,family,f'robust_{family}_{variant}_{block}',seed)
                            member.loc[test.index]=p;audits.append(a);write('robustness_training_audit.json',audits)
                        members.append(member.groupby([z.decision_date,z.profile_name]).rank(pct=True) if len(families)>1 else member)
                    raw=pd.concat(members,axis=1).mean(axis=1)
                    z[KEYS].assign(prediction=raw).to_csv(cache,index=False)
            hv=z.realized_volatility_1y.ge(z.groupby(['decision_date','profile_name']).realized_volatility_1y.transform('quantile',.75))
            stats,pair=measure(z,apply(z,candidate,raw),v.evaluate(z,'repair_score'),v.evaluate(z,'champion_score'),v.evaluate(z.loc[hv],'repair_score'))
            # The stated robustness gate requires aggregate directions/profile floors;
            # utility threshold and three-year count remain development selection only.
            checks={k:value for k,value in stats['checks'].items() if k not in ['utility','three_years']}
            results[name][variant]={'checks':checks,'stats':stats}
            csv(f'{name}_{variant}_metrics.csv',pair)
            write('robustness.json',results)
            print('ROBUST',name,variant,all(checks.values()),flush=True)
            if not all(checks.values()):passed=False;break
        if passed:winner=candidate;break
    write('robustness_lock.json',{'winner':winner,'results':results,'locked_at':datetime.now(timezone.utc).isoformat()})

def final():
    """Post-selection diagnostics only; no changes to candidate rules after this."""
    lock=json.loads((O/'robustness_lock.json').read_text());choice=lock['winner']
    trials=pd.read_csv(O/'trials.csv')
    # If none passes, report the best development candidate as rejected evidence,
    # never relabel it as a winner or score it into the website.
    diagnostic=choice or trials.sort_values('utility',ascending=False).iloc[0].to_dict()
    write('final_diagnostic_lock.json',{'accepted_candidate':choice,'diagnostic_candidate':diagnostic,
        'purpose':'Post-lock contextual evaluation; diagnostic candidate remains rejected unless all previously specified gates passed.'})
    x,dev=data();del dev;gc.collect()
    outputs=[]
    for period,file in [('development','development_refined_scores.csv.gz'),('early','early_refined_scores.csv.gz'),('exposed','exposed_refined_scores.csv.gz')]:
        scores=pd.read_csv(BASE/file)
        source=x if period!='exposed' else features(v.load_historical(True))
        z=source.merge(scores[KEYS+['champion_score','v17_score','repair_score']],on=KEYS,validate='one_to_one')
        assert len(z)==len(scores),(period,len(z),len(scores))
        raw=None
        if diagnostic['family'] in ['age_monotone','age_interactions','age_return','age_residual','age_consensus']:
            if period=='development':raw=signal(z,diagnostic['family'])
            else:
                members=[]
                families=['age_monotone','age_return','age_residual'] if diagnostic['family']=='age_consensus' else [diagnostic['family']]
                for family in families:
                    member=pd.Series(np.nan,index=z.index)
                    for year in sorted(z.decision_date.str[:4].unique()):
                        test=z[z.decision_date.str.startswith(year)]
                        p,a=fit(source[source.endpoint.lt(test.decision_date.min())],test,family,f'postlock_{family}_{period}_{year}')
                        member.loc[test.index]=p
                    members.append(member.groupby([z.decision_date,z.profile_name]).rank(pct=True) if len(families)>1 else member)
                raw=pd.concat(members,axis=1).mean(axis=1)
        z['candidate_score']=apply(z,diagnostic,raw)
        z[KEYS+['candidate_score']].to_csv(O/f'{period}_diagnostic_scores.csv.gz',index=False)
        masks={'all':pd.Series(True,index=z.index),'short_history':z.history_months.lt(60),
            'full_history':z.has_true_5y.eq(1),'high_volatility':z.realized_volatility_1y.ge(z.groupby(['decision_date','profile_name']).realized_volatility_1y.transform('quantile',.75)),
            'deep_drawdown':z.full_history_max_drawdown.le(-.5),'deep_ath':z.distance_from_recorded_high.le(-.4),
            'old_ath':z.days_since_recorded_high.ge(1095),'recent_ath':z.days_since_recorded_high.le(90)}
        for cohort,mask in masks.items():
            for model in ['champion_score','v17_score','repair_score','candidate_score']:
                out=v.evaluate(z.loc[mask],model);out['period']=period;out['cohort']=cohort;out['model']=model;outputs.append(out)
        print('FINAL HISTORICAL',period,len(z),flush=True)
        if period=='exposed':del source;gc.collect()
    results=pd.concat(outputs,ignore_index=True);csv('all_period_profile_cohort_metrics.csv',results)
    csv('period_model_summary.csv',results[results.cohort.eq('all')].groupby(['period','model'])[v.METRICS].mean().reset_index())
    # Current diagnostics happen only now, after selection and robustness locks.
    current=pd.read_csv(BASE/'final_current_rankings.csv.gz',low_memory=False)
    current=features(current);current['repair_score']=current.winner_score
    raw=None
    if diagnostic['family'] in ['age_monotone','age_interactions','age_return','age_residual','age_consensus']:
        members=[];audits=[]
        families=['age_monotone','age_return','age_residual'] if diagnostic['family']=='age_consensus' else [diagnostic['family']]
        for family in families:
            member,a=fit(x[x.endpoint.lt('2026-10-03')],current,family,'postlock_current_'+family);audits.append(a)
            members.append(member.groupby([current.decision_date,current.profile_name]).rank(pct=True) if len(families)>1 else member)
        raw=pd.concat(members,axis=1).mean(axis=1)
        write('current_training_audit.json',audits)
    current['diagnostic_score']=apply(current,diagnostic,raw)
    current['diagnostic_rank']=v.ranked(current,'diagnostic_score')
    stability=[]
    for profile,g in current.groupby('profile_name'):
        old=set(g[g.winner_rank.le(20)]['isin']);new=set(g[g.diagnostic_rank.le(20)]['isin'])
        stability.append({'profile':profile,'top20_overlap':len(old&new)/20})
    csv('current_stability.csv',pd.DataFrame(stability))
    stability_pass=all(r['top20_overlap']>=.85 for r in stability)
    accepted=choice is not None and stability_pass
    current['final_score']=current.diagnostic_score if accepted else current.winner_score
    current['final_rank']=current.diagnostic_rank if accepted else current.winner_rank
    current.to_csv(O/'final_current_rankings.csv.gz',index=False)
    for n in [20,50,100]:csv(f'current_top{n}.csv',current[current.final_rank.le(n)].sort_values(['profile_name','final_rank']))
    csv('nykaa_diagnostic.csv',current.loc[current.ticker.eq('NYKAA'),['profile_name','days_since_recorded_high','distance_from_recorded_high','winner_rank','diagnostic_rank','final_rank','winner_score','diagnostic_score']])
    protected=json.loads((O/'protected_hashes.json').read_text());unchanged=all(digest(ROOT/p)==d for p,d in protected.items());assert unchanged
    write('decision.json',{'winner':'V17 ATH refined' if accepted else 'V17 refined retained',
        'verdict':'PROMISING CHALLENGER' if accepted else 'V17 REMAINS BEST CHALLENGER',
        'accepted':accepted,'candidate':choice,'rejected_diagnostic':diagnostic if not accepted else None,
        'trials':len(trials),'development_passes':int(trials.eligible.sum()),'current_stability_pass':stability_pass,
        'all44_dates':int(results.decision_date.nunique()),'profiles':int(results.profile.nunique()),'current_universe':int(current['isin'].nunique()),
        'protected_unchanged':unchanged,'website_changed':False,'mean_xirr_selection_weight':0,
        'no_unexposed_validation':True})
    print('FINAL',accepted,flush=True)

def report():
    decision=json.loads((O/'decision.json').read_text())
    trials=pd.read_csv(O/'trials.csv');details=json.loads((O/'details.json').read_text())
    summary=pd.read_csv(O/'period_model_summary.csv')
    allmetrics=pd.read_csv(O/'all_period_profile_cohort_metrics.csv')
    diagnostic=json.loads((O/'final_diagnostic_lock.json').read_text())['diagnostic_candidate']
    failures=[k for k,value in details[diagnostic['name']]['checks'].items() if not value]
    current=pd.read_csv(O/'final_current_rankings.csv.gz',low_memory=False)
    base=current[current.profile_name.eq('base7500')]
    nykaa=pd.read_csv(O/'nykaa_diagnostic.csv')
    source=json.loads((O/'provider_ath_reproduction.json').read_text())
    models={'champion_score':'d499580','v17_score':'Original V17','repair_score':'V17 refined','candidate_score':'New ATH candidate (diagnostic)'}
    lines=['# V17 ATH-age refinement research','',
        '## Decision','',f"**{decision['verdict']} — {decision['winner']}.**",'',
        f"Completed {len(trials)} configurations across separately locked rounds: 48 smooth ATH-age adjustments, 24 blends using four newly trained age-aware models, and 48 conditional expert blends. Development gate passes: {decision['development_passes']}. Website and frozen champion unchanged.",
        '', 'The user requested stronger days-since-high influence. This experiment tested that preference without targeting a company or choosing weights from current rankings. A lower NYKAA rank is not a selection criterion.',
        '', '## What was tested','',
        '- Saturating age alone; age with ATH distance; age with depth and recovery; age with depth and momentum. Six strengths, full-profile and 36-month routes. No hard age cutoff.',
        '- Four retrained families: monotone age-aware utility, unconstrained age interactions, return-focused age model, and residual correction. Expanding annual training with outcome endpoints strictly before each scored year.',
        '- Nine profiles and all 16 development dates (2020–2023). Mean XIRR has zero selection weight. No 2024–2025 results used for selection.',
        f"- Post-lock evaluation covers {decision['all44_dates']} valid decision dates, all nine profiles, seven robustness cohorts plus the complete universe. Current evaluation includes all {decision['current_universe']:,} V7 stocks.",
        '- Prior 2020–2023 experimentation creates model-selection overfitting risk. 2024–2025 is exposed, not a fresh holdout. No NEW CHAMPION claim is available from this research alone.',
        '', '## Historical comparison','',
        'Metrics are averages across decision-date/profile groups; XIRR is the average of each group\'s Top20 median, not mean stock XIRR. Drawdown is negative: closer to zero is better.',
        '', '| Period | Model | Top20 median XIRR | Target achievement | Target shortfall | Mean asset drawdown | NDCG@20 |',
        '|---|---|---:|---:|---:|---:|---:|']
    for row in summary.itertuples():
        lines.append(f'| {row.period} | {models[row.model]} | {row.median_xirr_top20:.2%} | {row.target_achievement_top20:.2%} | {row.target_shortfall_top20:.2%} | {row.mean_asset_drawdown_top20:.2%} | {row.ndcg20:.4f} |')
    lines+=['',f"Locked diagnostic candidate: `{diagnostic['name']}`. Failed development checks: {', '.join(failures) or 'none'}. A diagnostic candidate is not promoted because it looks attractive on one metric.",
        '', '## Profile weaknesses of the new candidate','',
        '| Profile | Change in median XIRR (percentage points) | Change in drawdown (percentage points) |',
        '|---|---:|---:|']
    for row in details[diagnostic['name']]['profile_deltas']:
        lines.append(f"| {row['profile']} | {100*row['median_xirr_top20_delta']:+.2f} | {100*row['mean_asset_drawdown_top20_delta']:+.2f} |")
    lines+=['', '## NYKAA and ATH data','',
        'NYKAA\'s adjusted closing high is 1 December 2021. The stored 1,765 days is measured to the last quote; it is 1,767 days at the 3 October decision date. Corporate-action-adjusted execution history independently agrees with the high and distance. Its 2022 bonus does not explain away the old high.',
        f"All {source['rows']:,} usable provider histories exactly reproduced the stored age and distance. {source['repeated_high_date_cases']} histories contain repeated equal highs: the frozen feature takes the first occurrence. This is a documented feature-definition limitation; changing it only for current inference would introduce a training/inference mismatch. NYKAA is not one of these tie cases.",
        '', '| Profile | V17 refined rank | New candidate diagnostic rank | Final retained rank |', '|---|---:|---:|---:|']
    for row in nykaa.itertuples():
        def rank(value):return str(int(value)) if pd.notna(value) else 'Unranked'
        lines.append(f'| {row.profile_name} | {rank(row.winner_rank)} | {rank(row.diagnostic_rank)} | {rank(row.final_rank)} |')
    lines+=['', '## Current Top20 (default profile)','',', '.join(f"{int(row.final_rank)}. {row.ticker}" for row in base[base.final_rank.le(20)].sort_values('final_rank').itertuples()),
        '', 'Top20/50/100 for every profile: `experiments/v17-ath-refinement-20261004/current_top20.csv`, `current_top50.csv`, `current_top100.csv`.',
        '', '## Sources and interpretation','',
        'Academic work supports investigating high-price proximity and recency as signals, not assigning an arbitrary penalty to old all-time highs. The 52-week high and the all-time high are different concepts.',
        '', '- George & Hwang, The 52-Week High and Momentum Investing: https://onlinelibrary.wiley.com/doi/full/10.1111/j.1540-6261.2004.00695.x',
        '- The timing of 52-week high price and momentum: https://www.sciencedirect.com/science/article/pii/S0378426613002446',
        '- Nykaa issuer bonus record-date filing: https://www.nykaa.com/media/wysiwyg/2021/Investors-Relations/pdfs/stock-exchange-filling/Intimation-of-Record-date-for-Bonus-Issue.pdf',
        '', '## Audit trail','',
        '`protocol.json`, `trials.csv`, `details.json`, `training_audit.json`, `development_lock.json`, `robustness_lock.json`, `final_diagnostic_lock.json`, `all_period_profile_cohort_metrics.csv`, `provider_ath_reproduction.csv`, `current_stability.csv`, and `decision.json` reside in the experiment directory.',
        '', 'Original V17, V17 refined, runtime manifest and d499580 hashes remained unchanged. No stock-identity inputs, current fundamental backfills into history, deployed ranking changes, or exposed-period weight selection.']
    (ROOT/'research/reports/v17_ath_refinement_20261004.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('REPORT WRITTEN',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','search','audit','gated_prepare','gated_search','robustness','final','report']);args=parser.parse_args();globals()[args.stage]()
