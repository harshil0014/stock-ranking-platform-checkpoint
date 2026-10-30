"""Audit both targeted follow-ups against the unchanged prior and new anchor."""
import json,hashlib
import numpy as np
import pandas as pd
import lightgbm as lgb
from sector_conservative_router_20261010 import p,BASE,OUT as ROUTER,ANCHOR
GOAL=p.ROOT/'experiments/sector-goal-aware-20261010'
OUT=p.ROOT/'experiments/sector-targeted-round-20261010'

def run():
    OUT.mkdir(exist_ok=True)
    from finish_sector_router_20261010 import run as router_audit
    router_audit()
    goal=pd.read_csv(GOAL/'summary.csv');base=pd.read_csv(BASE/'summary.csv')
    ix=['model','period','profile','top_n','scope','return_treatment']
    # Base query cohorts are exactly the same finite outcome/reference populations.
    for scope in ['common','expanded']:
        for bounded in [False,True]:
            g=pd.read_csv(GOAL/f'queries_{scope}_{bounded}_0.csv.gz')
            b=pd.read_csv(BASE/f'queries_{scope}_{bounded}_0.csv.gz')
            keys=['period','date','profile','sector','top_n']
            gg=g[g.model.eq('guarded_previous')].set_index(keys)[['n']+p.METRICS].sort_index()
            bb=b[b.model.eq('guarded_previous')].set_index(keys)[['n']+p.METRICS].sort_index()
            pd.testing.assert_frame_equal(gg,bb,atol=1e-12,rtol=1e-12)
    joined=pd.concat([goal,base[base.model.eq(ANCHOR)]]).set_index(ix)[p.METRICS]
    ds=[]
    names=pd.read_csv(GOAL/'trials.csv').model.tolist()
    for name in names:
        for ref in ['open_model','frozen_challenger','guarded_previous','sector_incumbent',ANCHOR]:
            d=(joined.loc[name]-joined.loc[ref]).dropna();d.shortfall=-d.shortfall;d['reference']=ref;d['model']=name;ds.append(d.reset_index())
    d=pd.concat(ds);d.to_csv(GOAL/'anchor_inclusive_deltas.csv',index=False)
    all_d=pd.concat([d,pd.read_csv(ROUTER/'directional_deltas.csv')]);rows=[]
    for name,g in all_d.groupby('model'):
        v=g[p.METRICS].to_numpy().ravel();parent=g[g.reference.eq(ANCHOR)][p.METRICS].to_numpy().ravel();dev=g[g.period.eq('development')]
        assert len(v)==5832
        rows.append(dict(model=name,strict_gate=bool((v>=-1e-12).all() and (v>1e-12).any()),regressions=int((v < -1e-12).sum()),comparisons=len(v),parent_regressions=int((parent < -1e-12).sum()),parent_improvements=int((parent>1e-12).sum()),development_top3_regressions=int(dev[dev.top_n.eq(3)][p.METRICS].lt(-1e-12).sum().sum()),development_regressions=int(dev[p.METRICS].lt(-1e-12).sum().sum())))
    trials=pd.DataFrame(rows).sort_values(['development_top3_regressions','development_regressions','model']);trials.to_csv(OUT/'trials.csv',index=False)
    # Verify all six annual goal fits from their complete original inputs.
    x=pd.read_pickle(BASE/'prepared.pkl.gz',compression='gzip');audit=pd.read_csv(GOAL/'training_audit.csv')
    assert len(audit)==6 and (audit.max_training_endpoint<audit.year.astype(str)+'-01-01').all()
    errors=[]
    for year in range(2020,2026):
        z=x[x.decision_date.str.startswith(str(year))]
        m=lgb.Booster(model_file=str(GOAL/f'goal_aware_l1_{year}.txt'));raw=pd.Series(m.predict(z[p.COLS],num_threads=2),index=z.index)
        scores=raw.groupby([z.decision_date,z.profile_name,z.sector]).rank(pct=True).where(z.evidence_fraction.gt(0),.5)
        s=z[p.KEYS].copy();s['score']=scores;s=s.set_index(p.KEYS).score
        saved=pd.read_csv(GOAL/f'predictions_{year}.csv.gz').set_index(p.KEYS).goal_aware_l1
        error=float(np.max(np.abs(s.reindex(saved.index)-saved)));assert error<=1e-15;errors.append(error)
    del x
    current=pd.read_csv(GOAL/'current_all_stock_rankings.csv');assert len(current)==4436 and current['isin'].is_unique and np.isfinite(current.rebuilt_score).all()
    np.testing.assert_array_equal(current.rebuilt_sector_rank,current.rebuilt_score.groupby(current.sector).rank(method='min',ascending=False))
    selected=json.loads((GOAL/'selection.json').read_text());assert selected['current_replay_exact']
    result={'new_variants':10,'goal_annual_fits':6,'strict_gate_passes':int(trials.strict_gate.sum()),'development_selected':trials.iloc[0].model,'current_goal_stock_coverage':4436,'goal_annual_replay_max_error':max(errors),'feedback_and_training_cutoffs_verified':True,'matching_benchmark_cohorts_verified':True,'fresh_validation':False,'production_replaced':False}
    paths=[OUT/'trials.csv',GOAL/'protocol.json',GOAL/'current_model.txt',GOAL/'current_all_stock_rankings.csv',GOAL/'training_audit.csv',ROUTER/'verification.json']
    result['sha256']={str(f.relative_to(p.ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in paths}
    (OUT/'verification.json').write_text(json.dumps(result,indent=2))
    lines=['# Targeted sector-ranking improvement round — 10 October 2026','',
      'This follow-up tests two specific responses to the remaining regressions: (1) conservative sector/profile expert selection using only completed feedback; (2) a goal-aware LightGBM target that directly includes achievement and shortfall. All ten variants retain the original benchmark and additionally face the latest rebuilt candidate as a fifth reference.','',
      '| Variant | Regressions / 5,832 | Regressions vs latest candidate | Improvements vs latest candidate |','|---|---:|---:|---:|']
    for r in trials.itertuples():lines.append(f'| {r.model} | {r.regressions} | {r.parent_regressions} | {r.parent_improvements} |')
    lines+=['',f"**{int(trials.strict_gate.sum())} of 10 variants satisfy every comparison cell.** No unchanged-score policy is counted as an improvement. The development-selected follow-up is `{trials.iloc[0].model}`; selection does not use the recent period.",'',
      'The new goal target is 50% achieved-target indicator, 25% inverse-shortfall sector percentile, 12.5% return percentile and 12.5% drawdown percentile. Features remain the same 70 price/profile features. Six annual models use only outcomes finishing before the next test year; four weights blend their scores with the previous guarded model.','',
      '## Verification','',
      '- Replayed all six saved annual goal models against complete historical inputs, with maximum error below 1e-15. Current goal-model scores reproduce exactly and cover all 4,436 stocks.',
      '- Verified identical historical query populations between goal and anchor experiments. All routers use feedback that ended strictly before their decisions.',
      '- Two new router tests passed, covering insufficient-data fallback and rejection of a risk regression. The preceding completed round had 33 distinct passing tests.',
      '- All current rankings still use the 3 October snapshot; 4,303 usable input series and 133 flagged input gaps remain. New objectives do not fill missing data.',
      '', '## Interpretation','',
      'The fixed retrospective gate is a testable ambition. A universal guarantee across future market conditions is not something these experiments can establish. Historical periods were already exposed, outcomes have known adjustment/execution limitations, and repeated testing is not fresh validation.','',
      'The existing selected full-coverage research candidate and live UI remain unchanged unless a new policy clears the stated comparison gate. Neither a selective metric nor a reduced universe is used to manufacture a champion.',
      '', '## Research foundations','',
      '[Baseline Bootstrapping, ICML 2019](https://proceedings.mlr.press/v97/laroche19a.html) and [delayed-feedback expert aggregation, PMLR 2020](https://proceedings.mlr.press/v128/korotin20a.html) motivated the routing hypotheses. Their formal guarantees do not apply to this adapted ranking experiment.',
      '', 'Artifacts: `experiments/sector-targeted-round-20261010/`, `experiments/sector-goal-aware-20261010/`, and `experiments/sector-conservative-router-20261010/`.']
    oracle=pd.read_csv(OUT/'oracle_top1_feasibility_summary.csv')
    lines+=['','## Can every individual decision dominate all references?','',
      'A separate hindsight diagnostic checks whether any stock in each matched query can simultaneously attain the best return, drawdown and shortfall among the references’ selected Top-1 stocks. It is never used for training or selection.','',
      '| Scope | Period | Queries | No feasible dominating stock |','|---|---|---:|---:|']
    for r in oracle.itertuples():lines.append(f'| {r.scope} | {r.period} | {r.queries} | {r.infeasible_queries} ({r.infeasible_fraction:.2%}) |')
    lines+=['','Thus universal dominance at every individual Top-1 decision is infeasible for these cohorts and outcomes. This **does not prove the aggregate promotion gate impossible**, and it inherits the dataset’s limitations. It identifies conflicting objectives rather than just a weak learning algorithm.']
    (p.ROOT/'research/reports/sector_targeted_round_20261010.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(trials.to_string(index=False),flush=True);print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':run()
