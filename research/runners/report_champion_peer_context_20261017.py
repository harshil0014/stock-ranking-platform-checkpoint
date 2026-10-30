"""Verify receipts and report the bounded internal champion feature experiment."""
import json, hashlib
import numpy as np
import pandas as pd
import champion_peer_context_20261017 as r

def main():
    out=r.OUT; decision=json.loads((out/'decision.json').read_text()); name=decision['selected_patch']
    audits=[]
    for path in sorted(out.glob('*_audit.json')):
        a=json.loads(path.read_text()); model=out/path.name.replace('_audit.json','.txt')
        assert hashlib.sha256(model.read_bytes()).hexdigest()==a['model_sha256']
        assert a['max_training_endpoint']<a['cutoff'];audits.append(a)
    current=pd.read_csv(out/'current_all_4436_patch_audit.csv')
    assert len(current)==4436 and current['isin'].is_unique
    fallback=current.evidence_fraction.le(0)
    np.testing.assert_array_equal(current.loc[fallback,name],current.loc[fallback,r.ANCHOR])
    assert np.isfinite(current[[name,r.ANCHOR]]).all().all()
    tables=[]; trials=[]; sector=[]
    for stage in ['development','recent']:
        s=pd.read_csv(out/f'summary_{stage}.csv')
        tables.append(s[s.scope.eq('expanded')&s.return_treatment.eq('capped')&s.top_n.eq(3)].groupby(['model','period'])[r.p.METRICS].mean().reset_index())
        t=pd.read_csv(out/f'trials_{stage}.csv');t['stage']=stage;trials.append(t)
        for scope in ['common','expanded']:
            for treat in ['raw','capped']:
                q=pd.read_csv(out/f'queries_{stage}_{scope}_{treat}.csv.gz')
                keys=['period','date','profile','sector','top_n']
                assert q.groupby(keys).n.nunique().eq(1).all()
                assert q.groupby(keys).model.nunique().eq(q.model.nunique()).all()
                if scope=='expanded' and treat=='capped':
                    a=q[q.model.isin([r.ANCHOR,name])&q.top_n.eq(3)].groupby(['model','period','profile','sector'])[r.p.METRICS].mean()
                    d=(a.loc[name]-a.loc[r.ANCHOR]).reset_index();d.shortfall=-d.shortfall;sector.append(d)
    pd.concat(sector).to_csv(out/'selected_patch_sector_profile_deltas.csv',index=False)
    table=pd.concat(tables);table.to_csv(out/'aggregate_top3.csv',index=False)
    for k in [1,3,20,100]:
        current[current[name+'_sector_rank'].le(k)].sort_values(['sector',name+'_sector_rank','isin']).to_csv(out/f'within_sector_top{k}.csv',index=False)
    current[['isin','ticker','sector',r.ANCHOR+'_sector_rank',name+'_sector_rank','rank_change','rebuilt_input_confidence']].sort_values('rank_change').to_csv(out/'current_rank_changes.csv',index=False)
    lines=['# Champion improvement: small peer-context feature patch','',
      'Completed 17 October 2026. This changes the existing ranking component in an isolated research experiment; it does not introduce a new product/model selector.','',
      '## Decision','',f"Selected internal patch: **{name}**. Decision: **{decision['status']}**.",'',
      'Selection was locked on development 2020–2023 before evaluating 2024–2025. Those later dates were already exposed in earlier project research, so this is not fresh validation.','',
      '## What changed','',
      '- Kept the champion formula C = 0.75 G + 0.25 R and all inherited G components unchanged.',
      '- Added leave-one-out, same-date sector deviations to R: momentum, closing-high distance/persistence, downside volatility and drawdown. Tested strength-only, risk-only and combined ablations.',
      '- Kept the original rank_xendcg objective, 180 trees, hyperparameters, balanced relevance target and mature-label training rules.',
      '- This borrows the peer-context idea from [FinGAT](https://arxiv.org/abs/2106.10159) and [HIST](https://arxiv.org/abs/2110.13716); it is not a graph-model reproduction.',
      '- Peer statistics count each company once, exclude the company itself and invalid evidence, and become missing with fewer than four valid peers or constant peers. No new outcome enters feature construction.','',
      '## Aggregate results','',
      'Expanded universe, capped-return Top3; equal sector/profile aggregation. XIRR is the inherited SIP diagnostic, not a cost-complete portfolio return. Lower shortfall is better.','',
      '| Period | Component patch | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |',
      '|---|---|---:|---:|---:|---:|---:|---:|']
    for row in table.itertuples():
        lines.append(f'| {row.period} | {row.model} | {row.xirr:.2%} | {row.drawdown:.2%} | {row.achievement:.2%} | {row.shortfall:.5f} | {row.ndcg:.5f} | {row.rank_ic:.5f} |')
    lines+=['','## Matched metric/profile comparisons','','These overlapping cells are diagnostic comparisons, not independent statistical tests. XIRR has no selection weight; return regressions remain a promotion veto.','',
      '| Stage | Patch | Non-return improvements | Non-return regressions | Top3 non-return regressions | XIRR regressions | Pass |','|---|---|---:|---:|---:|---:|---|']
    for row in pd.concat(trials).itertuples():
        lines.append(f'| {row.stage} | {row.model} | {row.nonreturn_improvements} | {row.nonreturn_regressions} | {row.top3_nonreturn_regressions} | {row.xirr_regressions} | {row.passes} |')
    lines+=['','## Verification and coverage','',
      f'- {len(audits)} serialized fit receipts verified; each training endpoint precedes its cutoff. Predictions were checked against saved model replay in the runner.',
      '- Three feature tests pass: no cross-date/profile contamination, valid leave-one-out population, and small/constant-sector behavior.',
      '- Query populations match exactly for every compared model in each common/expanded and raw/capped evaluation.',
      f'- 4,436 unique current stocks with finite scores; {int(fallback.sum())} unavailable-evidence scores exactly preserve the champion fallback. Current snapshot remains 3 October 2026.',
      f'- {int(current.rank_change.ne(0).sum())} current stock sector ranks change under the selected research patch. Score preservation on fallback rows does not guarantee their ordinal ranks stay fixed when peers move.',
      '- No website or existing champion artifact was overwritten. Current exports cover base7500; historical evaluation covers all nine profiles.',
      '- Current-universe and retrospective sector limitations remain; this patch does not repair underlying data availability or corporate-action defects.','',
      '## Reproduce and inspect','',
      'Run `python research/runners/champion_peer_context_20261017.py`, then `python research/runners/report_champion_peer_context_20261017.py`. Outputs are in `experiments/champion-peer-context-20261017/`: protocol, development lock, model receipts, query-level metrics, sector/profile deltas, all-stock audit, rank changes and within-sector Top1/3/20/100.','']
    tradeoff=out/'tradeoff_review/decision.json'
    if tradeoff.exists():
        review=json.loads(tradeoff.read_text())
        lines += ['## User-authorized tradeoff review','',
          'The user subsequently allowed regressions when benefits outweigh costs. Accordingly, the strict gate above is only a diagnostic; a separate net-benefit analysis is authoritative for this follow-up.','',
          'Before computing that analysis, the recorded preference weights were rank IC 40%, NDCG 25%, achievement 15%, inverse shortfall 10%, drawdown 10%. Each directional difference is divided by .01. XIRR has zero selection weight. These are engineering preferences, not an objective definition of investment quality.','',
          'Quarter-, half- and full-strength application of the locked risk-context patch were compared. Strength was selected on development only; later outcomes did not choose a different winner. Equal-weight and ranking-only sensitivities were also reported.','',
          f"Selected: {review['selected']}. Development net-benefit score {review['development']['utility']:.4f}; later-period score {review['recent']['utility']:.4f}. Accept patch: {review['accept_research_patch']}.",'',
          'The selected patch loses on every reported aggregate later-period dimension, so rejection does not depend on demanding zero individual regressions. Its later ranking-only and equal-weight utilities are also negative. These utility values are dimensionless preference scores, not accuracy percentages.','',
          'The tradeoff analysis averages sector/profile cells directly; the earlier table first aggregates through the original profile summary. Small numerical differences reflect weighting order and are preserved explicitly rather than silently combined.','',
          'Reproduce with `python research/runners/champion_tradeoff_review_20261017.py`. See `tradeoff_review/protocol.json`, `lock.json`, `decision.json`, and full common/expanded, raw/capped Top1/3/5 deltas. The champion remains unchanged because this particular modification does not deliver a robust net benefit.','']
    (r.p.ROOT/'research/reports/champion_peer_context_20261017.md').write_text('\n'.join(lines),encoding='utf-8')
    sources=[r.p.OUT/'prepared.pkl.gz',r.p.OUT/'current_all_stock_rankings.csv',r.p.ROOT/'research/runners/champion_peer_context_20261017.py']
    r.write('verification.json',dict(fits=len(audits),rows=len(current),fallback_rows=int(fallback.sum()),paired_query_populations=True,source_hashes={str(p.relative_to(r.p.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}))
    print(table.to_string(index=False));print(decision)

if __name__=='__main__':main()
