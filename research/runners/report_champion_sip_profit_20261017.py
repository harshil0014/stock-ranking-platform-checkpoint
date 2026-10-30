import hashlib,json
import pandas as pd
import champion_sip_profit_20261017 as r

def main():
    d=json.loads((r.OUT/'decision.json').read_text());protocol=json.loads((r.OUT/'protocol.json').read_text())
    date_audit=json.loads((r.OUT/'source_date_audit.json').read_text())
    assert date_audit['as_of_after_decision']==0
    for path,digest in protocol['source_hashes'].items():assert hashlib.sha256((r.h.p.ROOT/path).read_bytes()).hexdigest()==digest
    summaries=[];dispersion=[]
    for stage in ['development','recent']:
        q=pd.read_csv(r.OUT/f'queries_{stage}.csv.gz')
        keys=['date','profile','sector','n','top_n','scope','treatment']
        anchor=q[q.model.eq(r.h.base.ANCHOR)]
        for name in q.model.unique():
            pd.testing.assert_frame_equal(anchor[keys].sort_values(keys).reset_index(drop=True),q[q.model.eq(name)][keys].sort_values(keys).reset_index(drop=True))
        q=q[q.scope.eq('expanded')&q.treatment.eq('capped')&q.top_n.eq(3)]
        cells=q.groupby(['model','sector','profile'])[r.h.p.METRICS].mean()
        for name in [r.h.base.ANCHOR,d['selected']]:
            summaries.append(dict(stage=stage,model=name,**cells.loc[name].mean().to_dict()))
        delta=cells.loc[d['selected']]-cells.loc[r.h.base.ANCHOR];delta.shortfall=-delta.shortfall
        delta=delta.reset_index();delta['stage']=stage;dispersion.append(delta)
    a=pd.DataFrame(summaries);a.to_csv(r.OUT/'aggregate_results.csv',index=False)
    pd.concat(dispersion).to_csv(r.OUT/'sector_profile_deltas.csv',index=False)
    current=pd.read_csv(r.OUT/'current_all_4436_audit.csv')
    changed=int(current.candidate_sector_rank.ne(current.patch_sector_rank).sum())
    dev=r.primary(pd.read_csv(r.OUT/'deltas_development.csv')).sort_values('utility',ascending=False)
    lines=['# Explicit SIP profit weighting for the active champion','',
       f"Selected: `{d['selected']}`. Research activation gate: **{'PASS' if d['accept_research_patch'] else 'DO NOT ACTIVATE'}**.",'',
       '## What was tested','',
       'The comparator is the currently active original champion plus dual_w0.01. Its component coefficients and high-recency adjustment are preserved exactly. Each candidate adds w × centered within-sector trailing SIP-profit percentile. Tested w: .01, .025, .05, .10, .20. These are additive score coefficients, not a claimed percentage of total nonlinear model importance.','',
       '- Plain: direct profit percentile, with larger profit always favored.',
       '- Invested: scale the adjustment by the fraction of the SIP budget actually invested, to reduce low-denominator affordability effects.',
       '- Risk confirmed: also scale by the within-sector inverse downside-volatility percentile.',
       '- Missing profit, missing champion evidence, unknown sector, stale/inactive trading, fewer than five valid peers, or unresolved provider/official discrepancies within the trailing lookback receive zero adjustment. No stock is removed from numerical coverage.','',
       '## Profit definition and literature','',
       'The signal uses the stored trailing professor-mode gain divided by actual invested cost, excluding unused cash. It is neither XIRR nor forward profit. The project simulator uses its own calendar/trading-day and corporate-action rules, so this is not exact Google Sheets replication.',
       '[Grinblatt and Han (2005)](https://www.sciencedirect.com/science/article/pii/S0304405X05000747) motivates testing gains relative to acquisition cost. Their aggregate capital-gains measure differs from this hypothetical SIP ledger; their findings do not validate these weights or this Indian stock universe. [FINRA performance guidance](https://www.finra.org/sites/default/files/2020-06/Regulatory-Notice-20-21.pdf) distinguishes cash-flow-sensitive IRR from other return measures. The investment-fraction and downside multipliers are engineering hypotheses, not direct paper replications.','',
       '## Evaluation','',
       'Fifteen configurations predefined before evaluation. Select on 2020–2023, lock one, then evaluate it on 2024–2025. Equal-sector/profile Top3 capped outcomes; weighted utility: 40% rank IC, 25% NDCG, 15% achievement, 10% inverse shortfall, 10% drawdown; directional deltas divided by .01. XIRR is not optimized but is an activation gate. The selected candidate must improve weighted utility and not worsen any of the six aggregate metrics in either period. Common/expanded populations, raw/capped outcomes and Top1/3/5 diagnostics are exported.','',
       '| Candidate | Development utility |','|---|---:|']
    for row in dev.itertuples():lines.append(f'| {row.model} | {row.utility:.6f} |')
    lines+=['','| Period | Model | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |','|---|---|---:|---:|---:|---:|---:|---:|']
    for row in a.itertuples():lines.append(f'| {row.stage} | {row.model} | {row.xirr:.3%} | {row.drawdown:.3%} | {row.achievement:.3%} | {row.shortfall:.6f} | {row.ndcg:.6f} | {row.rank_ic:.6f} |')
    lines+=['',f"Current coverage: {len(current):,}; nonzero selected adjustments: {d['current_nonzero_sip_adjustment']:,}; changed sector ranks: {changed:,}. Stock-order changes are not evidence of increased accuracy.",'',
       '## Verification and limitations','',
       '- Source hashes verified; identical historical query identities and population counts for compared models; current score replay within 1e-12. All current scores finite, bounded corrections, inherited fallback scores unchanged.',
       '- Three tests pass: profit direction/bounds/reliability, abstention, and independence from future dates/outcome columns.',
       f"- Source simulation-date audit: {date_audit['source_rows']:,} rows checked; zero simulation as-of dates after their decision dates.",
       '- Previously researched historical dates; no fresh out-of-sample validation. Current-survivor universe, retrospective sectors, gross outcomes and incomplete corporate-action certification remain.',
       '- The SIP feature is unavailable for some stocks. The champion remains their fallback; no performance claim is made from invented SIP values.',
       '- Website was not switched by this experiment. A gate pass is research evidence, not proof of future superiority.','',
       '## Reproduction','',
       'Set PYTHONPATH=src; run `python research/runners/champion_sip_profit_20261017.py`, then `python research/runners/report_champion_sip_profit_20261017.py`. Full scores, query metrics, sector/profile deltas, coverage, protocol and decision are under `experiments/champion-sip-profit-20261017/`.']
    path=r.h.p.ROOT/'research/reports/champion_sip_profit_20261017.md';path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(a.to_string(index=False));print('DECISION',d['accept_research_patch']);print(path)

if __name__=='__main__':main()
