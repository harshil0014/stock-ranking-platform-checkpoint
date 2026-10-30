"""Non-destructive delivery index and reproducibility manifest; no model selection."""
import hashlib
import json
import os
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'experiments/major-research-delivery-20261011'
STUDIES = ['sector-execution-specialist-20261011', 'sector-specialist-ensemble-20261011', 'sector-tabm-continuation-20261011']
ANCHOR = 'current_champion'
STACK = 'stack_breadth_balanced_w1.0'
METRICS = ['xirr', 'drawdown', 'achievement', 'shortfall', 'ndcg', 'rank_ic']
WEBSITE = {
    'src/stock_ranker/webapp.py': '094f04ab3261403252f1c07b61bb5620583bc777d4fdd89f056756f0040868b8',
    'src/stock_ranker/web_assets.py': '8df118f877925dfffd47abf75aa330008cb49ff9d378ca09ccfb14d3c8734c7d',
}

def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def write(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2, default=str), encoding='utf-8')

def build():
    OUT.mkdir(exist_ok=True)
    for path, expected in WEBSITE.items():
        assert digest(ROOT/path) == expected, path
    evidence = []
    def record(path, role):
        evidence.append(dict(path=str(path.relative_to(ROOT)), role=role, bytes=path.stat().st_size, sha256=digest(path)))
    checks = []
    for study in STUDIES:
        directory = ROOT/'experiments'/study
        replay = json.loads((directory/'replay_verification.json').read_text())
        evaluation = json.loads((directory/'evaluation_verification.json').read_text())
        assert replay['cutoffs_verified'] and evaluation['strict_gate_passes'] == 0
        assert evaluation['current_rows'] == 4436 and evaluation['historical_rows'] == 797443
        assert evaluation['champion_reference_reproduced'] and evaluation['current_ranks_verified']
        summary = pd.read_csv(directory/'finalist_summary.csv')
        assert summary.profile.nunique() == 9
        assert set(summary.period) == {'development', 'exposed'}
        assert set(summary.scope) == {'common', 'expanded'}
        checks.append(dict(study=study, replay=replay, evaluation=evaluation, profiles=sorted(summary.profile.unique())))
        for p in directory.rglob('*'):
            if p.is_file() and p.suffix in ['.json', '.pkl', '.pt', '.txt'] and 'before_current' not in str(p):
                record(p, 'protocol_model_or_receipt')
        for name in ['finalist_trials.csv', 'aggregate_metrics.csv', 'finalist_summary.csv', 'sector_profile_metrics.csv', 'worst_query_regressions.csv', 'serialized_replay.csv', 'financial_comparison.csv', 'rank_stability_summary.csv', 'pair_accuracy.csv', 'descriptive_date_block_bootstrap.csv', 'leave_one_year_out_differences.csv', 'all_4436_financial_evidence.csv']:
            if name == 'serialized_replay.csv' and study == STUDIES[0]:
                record(directory/'finish_sector_execution_specialist_20261011.py_replay.log', 'execution_replay_log')
                continue
            record(directory/name, 'verified_study_evidence')
        for variant in ['supplemental_global', 'supplemental_global_transport']:
            for name in ['profile_metrics.csv', 'oriented_differences.csv', 'current_global_top100.csv']:
                record(directory/variant/name, 'global_diagnostic')
    specialist = ROOT/'experiments'/STUDIES[1]
    neural = ROOT/'experiments'/STUDIES[2]
    matched = json.loads((neural/'matched_12epoch_controls/verification.json').read_text())
    assert matched['rows'] == 797443 and not matched['selection_changed']
    for directory in [neural/'matched_12epoch_controls', specialist/'stack_ablation']:
        for p in directory.glob('*.csv'):
            record(p, 'matched_component_or_budget_control')

    # Global positions use stable ISIN tie breaks, while score-rank preserves ties.
    source = pd.read_csv(specialist/'supplemental_global_transport/current_global_top100.csv', float_precision='round_trip')
    cols = ['evaluated_model', 'global_position', 'global_score_rank', 'isin', 'ticker', 'company', 'sector', 'evaluated_score', 'input_status', 'rebuilt_input_confidence', 'judge_primary', 'judge_coverage', 'judge_flags', 'review_flags', 'evidence_reason', 'sir_sector_rank']
    source = source[source.evaluated_model.isin([ANCHOR, STACK])][cols]
    for n in [1, 3, 20, 100]:
        selected = source[source.global_position.le(n)]
        assert selected.groupby('evaluated_model').size().eq(n).all()
        selected.to_csv(OUT/f'current_global_top{n}.csv', index=False)
    current = pd.read_csv(specialist/'all_4436_financial_evidence.csv', float_precision='round_trip')
    assert len(current) == 4436 and current['isin'].nunique() == 4436 and current.sector.nunique() == 59
    assert np.isfinite(current[[ANCHOR, STACK]]).all().all()
    current['retained_sector_rank'] = current[ANCHOR].groupby(current.sector).rank(method='min', ascending=False)
    current['challenger_sector_rank'] = current[STACK].groupby(current.sector).rank(method='min', ascending=False)
    current.to_csv(OUT/'all_4436_current_sector_evidence.csv', index=False)
    for n in [1, 3, 20, 100]:
        parts=[]
        for model, rank in [(ANCHOR, 'retained_sector_rank'), (STACK, 'challenger_sector_rank')]:
            part=current[current[rank].le(n)].copy()
            part['evaluated_model']=model; part['sector_score_rank']=part[rank]
            parts.append(part)
        pd.concat(parts).to_csv(OUT/f'current_sector_top{n}.csv', index=False)

    summary = pd.read_csv(specialist/'finalist_summary.csv')
    chosen = summary[summary.model.isin([ANCHOR, STACK])]
    chosen.to_csv(OUT/'retained_vs_stack_all_profiles.csv', index=False)
    ix=['period','profile','top_n','scope','return_treatment']
    delta=chosen[chosen.model.eq(STACK)].set_index(ix)[METRICS]-chosen[chosen.model.eq(ANCHOR)].set_index(ix)[METRICS]
    delta.shortfall=-delta.shortfall
    delta.reset_index().to_csv(OUT/'retained_vs_stack_oriented_profile_differences.csv', index=False)
    sector=pd.read_csv(specialist/'sector_profile_metrics.csv')
    sector=sector[sector.model.isin([ANCHOR,STACK])]
    sector.to_csv(OUT/'retained_vs_stack_sector_profile_metrics.csv', index=False)
    ix=['period','sector','profile','top_n','scope','return_treatment']
    sd=sector[sector.model.eq(STACK)].set_index(ix)[METRICS]-sector[sector.model.eq(ANCHOR)].set_index(ix)[METRICS]
    sd.shortfall=-sd.shortfall
    sd.reset_index().to_csv(OUT/'retained_vs_stack_oriented_sector_differences.csv', index=False)
    worst=[]
    for study in STUDIES:
        a=pd.read_csv(ROOT/'experiments'/study/'worst_query_regressions.csv')
        a['study']=study;worst.append(a)
    pd.concat(worst).to_csv(OUT/'all_finalist_worst_queries.csv', index=False)
    pd.concat([pd.read_csv(ROOT/'experiments'/s/'finalist_trials.csv').assign(study=s) for s in STUDIES]).to_csv(OUT/'finalist_gate_ledger.csv',index=False)
    # Preserve heterogeneous archived tables as source-attributed records, not a
    # fabricated count of independent trials. Partial/duplicate tables are labeled.
    ledger=[];inventory=[];errors=[]
    def onerror(exc):
        errors.append(dict(path=str(exc.filename),error=str(exc)))
    for directory, dirs, files in os.walk(ROOT/'experiments', onerror=onerror):
        dirs[:]=[d for d in dirs if 'dependencies' not in d and d != OUT.name]
        for name in files:
            if not name.endswith('.csv'):continue
            take=any(t in name for t in ['trial','leaderboard','tournament']) or name in ['candidate_summary.csv','candidate_metrics.csv','development_candidates.csv','candidate_frontier.csv']
            if not take or name=='research_experiment_ledger.csv':continue
            p=Path(directory)/name
            try:
                df=pd.read_csv(p);sha=digest(p)
                entry=dict(path=str(p.relative_to(ROOT)),sha256=sha,rows=len(df),columns=list(df.columns),partial='partial' in name,may_duplicate_other_archives=True)
                inventory.append(entry)
                for number, row in enumerate(df.astype(object).where(pd.notna(df), None).to_dict('records')):
                    ledger.append(dict(source=entry['path'],source_sha256=sha,source_row=number,partial=entry['partial'],record=row))
                record(p,'archived_trial_table')
            except Exception as exc:errors.append(dict(path=str(p),error=str(exc)))
    write('archive_trial_inventory.json',dict(sources=inventory,errors=errors,scope='All discoverable trial/leaderboard/tournament and named candidate-summary tables, including partial runs. Duplicate records and different populations are not independent trials. Inaccessible pytest temporary directory is disclosed.'))
    # JSON avoids flattening unlike metric schemas into a misleading common gate.
    write('complete_discoverable_trial_ledger.json',ledger)
    legacy=ROOT/'experiments/sector-price-rebuild-20261010/legacy-comparison'
    for p in legacy.glob('*.csv'):record(p,'matched_37_earlier_policy_comparison')
    record(legacy/'availability.json','earlier_policy_cohort_availability')
    for study in ['sector-price-rebuild-20261010','action-guarded-sector-20261008','profile-aware-sector-20261008','full-coverage-open-models-20261008','full-coverage-challenger-20261008']:
        for p in (ROOT/'experiments'/study).glob('*'):
            if p.is_file() and p.suffix in ['.json','.txt','.pkl']:
                record(p,'retained_reference_model_or_protocol')
    for p in (specialist/'issuer_review').rglob('*.pdf'):
        record(p,'archived_primary_issuer_source')
    for name in ['individual_and_combined_contributions.csv','learned_component_weights.csv','stack_audit.csv']:
        record(specialist/name,'specialist_contribution_evidence')
    for p in (ROOT/'research/runners').glob('*.py'):
        record(p,'reproducible_source')
    for p in (ROOT/'tests').glob('*specialist*.py'):record(p,'safeguard_test')
    for name in ['test_sector_execution_activity_join.py','test_global_score_transport.py']:
        record(ROOT/'tests'/name,'safeguard_test')
    for p in (ROOT/'research/reports').glob('*.md'):record(p,'research_report')
    for path in WEBSITE:record(ROOT/path,'unchanged_website')
    for p in OUT.glob('*'):
        if p.is_file() and p.name not in ['manifest.json','verification.json','completion.json']:
            record(p,'delivery')
    unique={r['path']:r for r in evidence}
    write('manifest.json',list(unique.values()))
    write('completion.json',dict(status='RESEARCH_COMPLETE_NO_CHAMPION_PROMOTION',retained_reference='rank_xendcg_balanced_blend0.25',promising_challenger=STACK,production_replaced=False,fresh_validation=False,as_of='2026-10-03',current_profile='base7500',historical_profiles=checks[0]['profiles'],historical_rows=797443,current_stocks=4436,current_groups=59,checks=checks,archive_sources=len(inventory),archive_records=len(ledger),archive_read_errors=errors,website_sha256=WEBSITE,qualification='Completed research outcome and deliverable package, not achievement of universal superiority, full PIT data reconstruction, or authorization to invest. No new deployment.'))
    print(json.dumps(dict(studies=len(checks),archive_sources=len(inventory),archive_records=len(ledger),archive_errors=errors,hashed_artifacts=len(unique)),indent=2))

def verify():
    manifest=json.loads((OUT/'manifest.json').read_text())
    for item in manifest:assert digest(ROOT/item['path'])==item['sha256'],item['path']
    for p,expected in WEBSITE.items():assert digest(ROOT/p)==expected
    for n in [1,3,20,100]:
        df=pd.read_csv(OUT/f'current_global_top{n}.csv')
        assert df.groupby('evaluated_model').size().eq(n).all()
    write('verification.json',dict(passed=True,hashed_artifacts=len(manifest),website_unchanged=True,qualification='Verifies this manifest and package invariants; model replay and chronological evidence are in source-specific receipts. Does not certify market profitability.'))
    print('VERIFIED',len(manifest),'artifacts; no production switch')

if __name__=='__main__':
    {'build':build,'verify':verify}[sys.argv[1]]()
