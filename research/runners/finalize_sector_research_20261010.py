"""Consolidate completed experiments; never promote an unpassed broad gate."""
import json,hashlib
import numpy as np
import pandas as pd
from sector_price_rebuild_20261010 import ROOT,METRICS
from sector_accuracy_20261010 import SOURCES
OUT=ROOT/'experiments/sector-research-final-20261010'

def run():
    OUT.mkdir(exist_ok=True);trials=[]
    for family,folder in SOURCES.items():
        t=pd.read_csv(folder/'trials.csv');t['family']=family;trials.append(t)
        assert (folder/'verification.json').exists() and (folder/'historical_model_replay.json').exists()
    trials=pd.concat(trials).sort_values(['development_top3_regressions','development_regressions','model'])
    trials.to_csv(OUT/'all_32_candidate_trials.csv',index=False)
    winner=trials.iloc[0];folder=SOURCES[winner.family]
    assert (folder/'legacy-comparison/verified_opponent_gates.csv').exists(),'Complete earlier-policy audit for the selected family first'
    selected=json.loads((folder/'selection.json').read_text());assert selected['model']==winner.model
    component,blend_weight=winner.model.split('_blend');blend_weight=float(blend_weight)
    current=pd.read_csv(folder/'current_all_stock_rankings.csv')
    col='rebuilt' if winner.family=='rebuilt' else 'yeti'
    flags=pd.read_csv(folder/'all_stock_structural_review.csv',usecols=['isin','review_flags','sector_size'])
    current=current.merge(flags,on='isin',validate='one_to_one')
    compact=current[['isin','ticker','company','sector','sector_size',col+'_sector_rank',col+'_score','guarded_sector_rank','open_model_sector_rank','input_status','rebuilt_input_confidence','observations','last_price_date','review_flags']].copy()
    compact=compact.rename(columns={col+'_sector_rank':'sector_rank',col+'_score':'research_score','guarded_sector_rank':'previous_guarded_sector_rank','open_model_sector_rank':'previous_open_sector_rank'})
    compact['model']=winner.model;compact['snapshot']='2026-10-03';compact['validation_status']='EXPOSED_RESEARCH_NOT_UNIVERSAL_CHAMPION'
    compact['review_required']=compact.review_flags.fillna('').str.contains('NO_USABLE|SHORT_PRICE|NOT_BENCHMARKED|ZERO_PRICE|DOMINATES|DRAWDOWN_BELOW')
    compact=compact.sort_values(['sector','sector_rank','isin']);compact.to_csv(OUT/'all_4436_sector_rankings.csv',index=False)
    compact[compact.sector_rank.le(3)].to_csv(OUT/'sector_top3_rankings.csv',index=False)
    assert len(compact)==4436 and compact['isin'].is_unique and np.isfinite(compact.research_score).all()
    np.testing.assert_array_equal(compact.sector_rank,compact.research_score.groupby(compact.sector).rank(method='min',ascending=False))
    summary=pd.read_csv(folder/'summary.csv');means=summary[summary.top_n.eq(3)].groupby(['scope','period','return_treatment','model'])[METRICS].mean().reset_index()
    means.to_csv(OUT/'paired_top3_summary.csv',index=False)
    accuracy=ROOT/'experiments/sector-accuracy-20261010';pairs=pd.read_csv(accuracy/'pair_accuracy_summary.csv')
    pairs.to_csv(OUT/'whole_sector_pair_accuracy.csv',index=False)
    previous=pd.read_csv(folder/'legacy-comparison/verified_opponent_gates.csv')
    current_status=current.input_status.value_counts().to_dict();struct=json.loads((folder/'structural_review.json').read_text())
    if not (folder/'sector_top3_tradeoffs.csv').exists():
        from sector_tradeoffs_20261010 import run as tradeoffs
        tradeoffs(winner.family)
    sector_deltas=pd.read_csv(folder/'sector_top3_tradeoffs.csv')
    worst=sector_deltas[sector_deltas.scope.eq('expanded')&sector_deltas.period.eq('exposed')&sector_deltas.reference.eq('guarded_previous')].sort_values('xirr').head(3)
    worst_text='; '.join(f'{r.sector}: {r.xirr*100:+.2f} percentage points Top-3 XIRR' for r in worst.itertuples())
    tests=json.loads((SOURCES['rebuilt']/'test_results.json').read_text())
    verification={'selected_research_candidate':winner.model,'family':winner.family,'selection':'Fewest development Top-3 regressions, then fewest development total regressions, across 32 completed candidates. Exposed period not used to choose.',
      'candidate_count':32,'additional_fixed_activity_rule':1,'annual_fits':48,'profiles':9,'current_stocks':len(compact),'current_input_status':current_status,
      'strict_gate_passes':int(trials.strict_gate.sum()),'selected_strict_gate':bool(winner.strict_gate),'top3_regressions':int(winner.top3_regressing_cells),'top3_comparisons':int(winner.top3_cells),
      'all_metric_regressions':int(winner.regressing_cells),'all_metric_comparisons':int(winner.total_cells),
      'legacy_policies':37,'legacy_policy_gates_passed':int(previous.all_cells_nonworse.sum()),'tests_passed':tests['distinct_tests_passed'],
      'fresh_validation':False,'production_replaced':False,'snapshot':'2026-10-03','status':'COMPLETED_RESEARCH_WITH_DISCLOSED_TRADEOFFS'}
    files=[OUT/'all_4436_sector_rankings.csv',OUT/'all_32_candidate_trials.csv',OUT/'paired_top3_summary.csv',OUT/'whole_sector_pair_accuracy.csv',folder/'verification.json',folder/'historical_model_replay.json',SOURCES['yeti' if winner.family=='rebuilt' else 'rebuilt']/'historical_model_replay.json',folder/'legacy-comparison/verified_opponent_gates.csv',accuracy/'verification.json',ROOT/'experiments/sector-activity-guard-20261010/selection.json']
    verification['sha256']={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    (OUT/'completion.json').write_text(json.dumps(verification,indent=2))
    lines=['# Completed sector-ranking research — 10 October 2026','',
      f"**Selected research candidate: `{winner.model}`.** This continuation completed 32 model/blend candidates from 48 annual fits, plus one fixed price-activity follow-up. The selected candidate was compared with 37 recoverable earlier policies, including the baseline, professor formula and prior sector champion. All nine profiles were included.",'',
      f"Its score is **{1-blend_weight:.0%} previous guarded score + {blend_weight:.0%} new `{component}` sector-percentile score**. This is a blended candidate. Its older component can retain older data defects; rebuilding the new component does not certify the inherited features.",'',
      '## Coverage','',f"The export ranks **all 4,436 stocks** in **{current.sector.nunique()} sector/classification groups**. **{int(current.evidence_fraction.gt(0).sum())}** have usable rebuilt price inputs; **{int(current.evidence_fraction.eq(0).sum())}** have explicitly marked missing or unresolved inputs. It uses the **3 October 2026 snapshot**, not live 10 October prices. A fallback score does not certify input completeness or tradability.",'',
      '## Matched comparison with the previous guarded model','',
      'Equal-sector, equal-profile Top-3 SIP metrics; returns capped to [−100%, +100%] before the per-sector calculations. These are ranking diagnostics, not a realizable portfolio backtest.','',
      '| Scope | Period | Model | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |','|---|---|---|---:|---:|---:|---:|---:|---:|']
    for row in means[means.model.isin([winner.model,'guarded_previous'])&means.return_treatment.eq('capped')].itertuples():
        lines.append(f'| {row.scope} | {row.period} | {"New" if row.model==winner.model else "Previous"} | {row.xirr:.2%} | {row.drawdown:.2%} | {row.achievement:.2%} | {row.shortfall:.2%} | {row.ndcg:.4f} | {row.rank_ic:.4f} |')
    lines+=['','## Whole-sector ordering accuracy','',
      'Pair accuracy awards one point for correctly ordering two stocks by their later XIRR, zero for reversing them and half for ties. It is measured on identical outcome-covered sector peers. It is not the probability that a stock makes money.','',
      '| Scope | Period | Model | Pair accuracy |','|---|---|---|---:|']
    for row in pairs[pairs.model.isin([winner.family+'_selected','guarded_previous','sector_incumbent'])].itertuples():lines.append(f'| {row.scope} | {row.period} | {row.model} | {row.pair_accuracy:.2%} |')
    lines+=['','Sector-resampling uncertainty and the fraction of sectors improved are saved in `experiments/sector-accuracy-20261010/paired_sector_accuracy_differences.csv`. These describe the already-exposed sample; they do not correct repeated research selection.','',
      '## Professor, baseline and company-evidence checks','',
      'Recent-period capped Top-3 outcomes below use matching populations separately for each opponent. The professor comparator replays the project whole-share policy; it is not a claim that the screenshot supplies independent outcomes for every stock.','',
      '| Earlier policy | New XIRR | Earlier XIRR | New rank IC | Earlier rank IC |','|---|---:|---:|---:|---:|']
    legacy=pd.read_csv(folder/'legacy-comparison/all_profile_summary.csv')
    for opponent in ['Baseline four-factor formula replay','Professor whole-share project policy','Production sector champion','V17']:
        g=legacy[legacy.opponent.eq(opponent)&legacy.period.eq('exposed')&legacy.top_n.eq(3)&legacy.return_treatment.eq('capped')].groupby('model')[METRICS].mean()
        n,o=g.loc['open_model'],g.loc['opponent_score'];lines.append(f'| {opponent} | {n.xirr:.2%} | {o.xirr:.2%} | {n.rank_ic:.4f} | {o.rank_ic:.4f} |')
    lines+=['','The current company-evidence rubric is a separate diagnostic. Higher is better; it is not a calibrated probability.','',
      '| Scope | Model | Top-3 company rubric |','|---|---|---:|']
    for row in pd.read_csv(folder/'rubric_summary.csv').itertuples():lines.append(f'| {row.scope} | {row.model} | {row.rubric:.4f} |')
    lines+=['', '## Tradeoffs and stock-level review','',
      f"- The selected model has **{int(winner.top3_regressing_cells)} / {int(winner.top3_cells)} Top-3 regressions** and **{int(winner.regressing_cells)} / {int(winner.total_cells)} total regressions** across the original comparison cells. **{int(trials.strict_gate.sum())} / 32** candidates pass the full broad gate. Aggregate improvements do not establish universal superiority.",
      f'- Recent expanded-universe sector tradeoffs against the previous guarded model include {worst_text}. Complete per-sector and per-profile differences are saved alongside the rankings.',
      f"- Against the 37 earlier policies, **{int(previous.all_cells_nonworse.sum())}** are nonworse in every recorded cell. All per-policy and per-profile results are retained. Missing or non-comparable archived studies are not declared beaten.",
      '- A separate candidate was selected solely for development-period whole-sector rank correlation. Its export and recent-period results are in the accuracy report; that alternative criterion does not replace the original promotion gate.',
      f"- Every current stock received structural checks. Among {struct['top3_rows_including_ties']} sector Top-3 entries, {struct['flags']['SHORT_PRICE_HISTORY']['sector_top3']} have short price histories and {struct['flags']['MORE_THAN_HALF_ZERO_PRICE_CHANGES']['sector_top3']} have more than half zero daily changes. All flags are retained in the compact ranking export.",
      '- The KALYANI review exposed a nearly flat price series ranking first in a sector. A fixed activity-tier experiment moved such stocks down but reduced recent ordering accuracy. It is documented separately and has not silently overridden the selected model.',
      '- The existing company-evidence rubric is joined to all current ranks. This is reused evidence, not 4,436 fresh company investigations or an independent future-return oracle.',
      '', '## Verification and limitations','',
      '- Rebuilt high, momentum, trend and downside features use observations available by each decision date. Unresolved adjustment windows and stale inputs are masked. Training outcomes end before the annual test fold.',
      '- Historical predictions were reproduced from every saved annual model. Current exports reproduce the serialized model and within-sector ranking arithmetic. Source hashes and test results are retained.',
      f"- **{tests['distinct_tests_passed']} distinct tests passed**, including future-price independence, scale invariance, corporate-action guards, frozen-runtime compatibility, sector isolation, pair-accuracy arithmetic and website custom-profile recomputation.",
      '- All historical periods have already been exposed by previous research. The current identity universe and sector classifications are used retrospectively; this is not a survivor-free historical exchange-membership reconstruction. Corporate-action and execution-history reconstruction remains incomplete; masks do not prove that every surviving outcome is correct.',
      '- The live ranking model has not been switched. The frozen-runtime corporate-action guard bug was fixed and tested. Research results are completed, with the remaining qualification limits stated above.',
      '', '## Research sources','',
      '[ICML 2023 learning-to-rank study](https://proceedings.mlr.press/v202/lyzhin23a.html), [financial cross-sectional ranking research](https://arxiv.org/abs/2012.07149), [LightGBM implementation documentation](https://lightgbm.readthedocs.io/en/latest/Parameters.html), and [CatBoost ranking documentation](https://catboost.ai/docs/en/concepts/loss-functions-ranking?lang=en). These informed the tested objectives; performance claims come from the saved project experiments.',
      '', '## Deliverables','',
      '- Full compact ranking: `experiments/sector-research-final-20261010/all_4436_sector_rankings.csv`',
      '- Completed run manifest: `experiments/sector-research-final-20261010/completion.json`',
      '- All 32 candidate comparisons: `experiments/sector-research-final-20261010/all_32_candidate_trials.csv`',
      '- Accuracy diagnostic: `research/reports/sector_accuracy_20261010.md`',
      '- Activity review: `research/reports/sector_activity_review_20261010.md`',
      f'- Earlier-policy audit and company rubric: `{folder.relative_to(ROOT).as_posix()}/`']
    (ROOT/'research/reports/sector_research_complete_20261010.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in verification.items() if k!='sha256'},indent=2),flush=True)

if __name__=='__main__':run()
