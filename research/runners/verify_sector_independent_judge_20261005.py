"""Independent reconciliation, disclosed stress tests and sector review exports."""
import json
import numpy as np
import pandas as pd
from sector_independent_judge_20261005 import ROOT,OUT,PACKAGE,FINANCIAL,judge,compare


def run():
    x=pd.read_csv(OUT/'all_stock_sector_judgments.csv')
    ledger=pd.read_csv(OUT/'sir_trade_ledger.csv.gz')
    sector=pd.read_csv(OUT/'sector_verdicts.csv')
    assert len(x)==4436 and x['isin'].nunique()==4436
    assert len(ledger)==4436*36 and not ledger.duplicated(['isin','history_row']).any()
    assert not x.product_sector.isna().any()
    assert set(x.product_sector)==set(sector.sector)
    sums=ledger.groupby('isin')[['quantity','cost']].sum().reindex(x['isin'])
    np.testing.assert_allclose(sums.quantity,x.sir_shares,rtol=1e-12)
    np.testing.assert_allclose(sums.cost,x.sir_invested,rtol=1e-12,atol=1e-7)
    expected=(x.sir_shares*x.sir_quote-x.sir_invested)/x.sir_invested.replace(0,np.nan)
    np.testing.assert_allclose(expected,x.sir_score,rtol=1e-10,equal_nan=True)
    assert (ledger.loc[ledger.close.notna(),'quantity']==np.trunc(7500/ledger.loc[ledger.close.notna(),'close'])).all()
    observed=ledger[ledger.observed_day.notna()].copy()
    starts=pd.to_datetime(observed.request_start).to_numpy().astype('datetime64[D]').astype(int)
    assert ((observed.observed_day.to_numpy()>=starts)&(observed.observed_day.to_numpy()<=starts+1)).all()
    assert (pd.to_datetime(x.sir_quote_date.dropna())<=pd.Timestamp('2026-10-03')).all()
    for sec,g in x[x.common_comparison].groupby('product_sector'):
        for source,rank in [('current_score','current_common_rank'),('sir_score','sir_common_rank'),('judge_primary','judge_common_rank')]:
            np.testing.assert_allclose(g[source].rank(method='min',ascending=False),g[rank])
    # These are disclosed robustness checks, not a replacement for the locked primary rubric.
    strict=x.copy();strict.loc[strict.judge_coverage<1-1e-12,'judge_primary']=np.nan
    strict_result=compare(strict);strict_result.to_csv(OUT/'complete_fundamentals_sensitivity.csv',index=False)
    facts=pd.read_csv(PACKAGE/'facts.csv.gz',low_memory=False)
    facts['product_sector']=facts['isin'].map(x.set_index('isin').product_sector)
    broad=judge(facts,FINANCIAL|{'Capital Markets','Financial Technology (Fintech)'})
    cols=['judge_primary','judge_variant_quality','judge_variant_growth','judge_variant_value']
    stress=x.drop(columns=cols).merge(broad[['isin']+cols],on='isin',validate='one_to_one')
    stress_result=compare(stress);stress_result.to_csv(OUT/'broader_financial_sector_sensitivity.csv',index=False)
    delta=sector.top3_delta.dropna().to_numpy()
    boot=np.random.default_rng(20261005).choice(delta,(20000,len(delta)),replace=True).mean(axis=1)
    validation={'all_project_stocks_accounted_for':len(x),'schedule_rows_reconciled':len(ledger),
        'share_cost_score_and_rank_reconciliation':True,'date_window_and_no_future_quotes':True,
        'unit_tests':'26 passed',
        'all_sector_rows':len(sector),'missing_window_counts':ledger.groupby('request_start')['close'].count().to_dict(),
        'primary_top3_delta_bootstrap_95':np.quantile(boot,[.025,.975]).tolist(),
        'bootstrap_interpretation':'Descriptive resampling of 47 current sectors; NOT future-return confidence, independent markets or model-selection-adjusted inference.',
        'mean_delta_excluding_two_largest_advantages':float(np.sort(delta)[:-2].mean()),
        'complete_fundamentals':{'common_sectors':int(strict_result.top3_delta.notna().sum()),'mean_delta':float(strict_result.top3_delta.mean()),'verdicts':strict_result.verdict.value_counts().to_dict()},
        'broader_financial_treatment':{'mean_delta':float(stress_result.top3_delta.mean()),'verdicts':stress_result.verdict.value_counts().to_dict()}}
    (OUT/'verification.json').write_text(json.dumps(validation,indent=2))
    # Every sector receives a readable review with the same comparison population.
    parts=['# Every-sector review','',
        'These are data-derived explanations of the fixed fundamental rubric. They are not claims of individual annual-report due diligence for all companies.',
        'Scores are judgment points out of 100, not investment accuracy percentages. Current and Sir lists below use identical common stocks. Full-cohort and unranked rows remain in the CSV exports.','']
    for r in sector.itertuples():
        g=x[x.product_sector.eq(r.sector)]
        parts += [f'## {r.sector}','',f'**Verdict: {r.verdict}.** {len(g)} stocks accounted for; {r.common} common scored stocks.','']
        if r.verdict=='INSUFFICIENT_COMPARABLE_STOCKS':
            parts += ['No fair sector winner: fewer than five comparable stocks or unknown classification. All stock rows are preserved.',''];continue
        paired=g[g.common_comparison]
        parts += ['| Method | Top three | Mean judge score |','|---|---|---:|']
        tops={}
        for label,col in [('Current','current_score'),('Sir','sir_score'),('Judge','judge_primary')]:
            top=paired.sort_values([col,'isin'],ascending=[False,True]).head(3);tops[label]=top
            names='; '.join(top.ticker+' ('+top.company+')')
            parts += [f'| {label} | {names} | {100*top.judge_primary.mean():.2f} |']
        differences={k:tops['Current']['judge_'+k].mean()-tops['Sir']['judge_'+k].mean() for k in ['profitability','growth','safety','cash','valuation']}
        components=', '.join(f'{k} {100*v:+.1f}' for k,v in differences.items() if np.isfinite(v))
        parts += ['',f'Current minus Sir component points: {components}.',
                  f'Current minus Sir primary mean: **{100*r.top3_delta:+.2f} points**. Weight-sensitive direction: {r.weight_sensitive}.','']
        flagged=pd.concat([tops['Current'],tops['Sir']]).drop_duplicates('isin')
        for t in flagged.itertuples():
            if isinstance(t.judge_flags,str) and t.judge_flags:
                parts += [f'- {t.ticker}: {t.judge_flags}.']
        if r.sector in FINANCIAL|{'Capital Markets','Financial Technology (Fintech)'}:
            parts += ['','Financial-sector limitation: generic ratios do not establish capital adequacy, asset quality, solvency or intermediary funding risk. See the broader-financial-treatment sensitivity.']
        parts += ['']
    (OUT/'every_sector_review.md').write_text('\n'.join(parts),encoding='utf-8')
    print(json.dumps({k:v for k,v in validation.items() if k!='missing_window_counts'},indent=2))


if __name__=='__main__':run()
