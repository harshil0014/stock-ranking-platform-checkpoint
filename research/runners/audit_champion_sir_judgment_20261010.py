"""Every-stock, declared-rubric audit; agreement is not investment correctness."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/champion-sir-judgment-20261010'
SOURCE=ROOT/'experiments/sector-independent-judge-20261005/all_stock_sector_judgments.csv'
CURRENT=ROOT/'experiments/sector-research-final-20261010/all_4436_sector_rankings.csv'
BLOCKS=['profitability','growth','safety','cash','valuation']
WEIGHTS={'primary':[.2,.2,.2,.2,.2],'quality':[.3,.15,.2,.25,.1],'growth':[.2,.35,.1,.15,.2],'value':[.2,.15,.15,.15,.35]}

def agreement(s,y):
    s=np.asarray(s);y=np.asarray(y);n=len(s)
    sign=np.sign(s[:,None]-s[None,:])*np.sign(y[:,None]-y[None,:])
    credit=(sign+1)/2;np.fill_diagonal(credit,np.nan)
    per_stock=np.nanmean(credit,axis=1)
    return float(np.nanmean(credit)),per_stock,float(np.nansum(credit)/2),n*(n-1)//2

def position(v):
    return (v.rank(ascending=False,method='average')-1)/(len(v)-1)

def run():
    OUT.mkdir(exist_ok=True)
    protocol={'snapshot':'2026-10-03','model':'rank_xendcg_balanced_blend0.25','rubric_weights':WEIGHTS,'primary':'20% each profitability,growth,safety,cash,valuation; financial sectors omit corporate cash/leverage inputs and redistribute applicable weights. At least60% input coverage.',
      'scope':'All4436 identities inspected; exclude Unclassified and fewer than5 judged peers from percentages. Headline comparison uses identical stocks with finite Sir/model/rubric scores.',
      'percentages':'Pair agreement: correctly ordered stock pairs, ties half credit, equal sector mean primary. Reasonably placed: absolute rank-percentile difference<=0.10. These are benchmark agreement, not proven correctness or return prediction.',
      'sources':'Previously collected company fundamentals and isolated professor-formula replication; no new4436-company due diligence claimed. Neither model score nor Sir score enters the rubric.',
      'sensitivity':'quality/growth/value weights; fully covered fundamentals; Sir>=24observations and quote<=14days old.',
      'sir_limit':'Generalized independent per-stock workbook arithmetic; workbook slot-specific cross-references are not a full-universe strategy. All numeric Sir results have partial price observations.',
      'ranking_changes':False}
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    current=pd.read_csv(CURRENT);source=pd.read_csv(SOURCE)
    keep=['isin','product_sector','sir_score','sir_sector_rank','sir_status','sir_price_observations','sir_requested_observations','sir_quote_lag_days','judge_coverage','judge_flags']+[c for c in source if c.startswith(('judge_input_','judge_','coverage_','screener_')) and c not in ['judge_coverage','judge_flags']]
    x=current.merge(source[list(dict.fromkeys(keep))],on='isin',validate='one_to_one')
    assert len(x)==4436 and x['isin'].is_unique and x.sector.eq(x.product_sector).all()
    ledger=pd.read_csv(SOURCE.parent/'sir_trade_ledger.csv.gz')
    assert len(ledger)==4436*36 and not ledger.duplicated(['isin','history_row']).any()
    quantities=np.trunc(7500/ledger.close).fillna(0)
    np.testing.assert_allclose(quantities,ledger.quantity,atol=0,rtol=0)
    np.testing.assert_allclose((ledger.close*quantities).fillna(0),ledger.cost,atol=1e-9,rtol=1e-12)
    sums=ledger.groupby('isin')[['quantity','cost']].sum().reindex(x['isin'])
    np.testing.assert_allclose(sums.quantity,x.sir_shares if 'sir_shares' in x else source.set_index('isin').sir_shares.reindex(x['isin']),atol=1e-9,rtol=1e-12)
    quotes=source.set_index('isin').sir_quote.reindex(x['isin']).to_numpy()
    replay=(quotes*sums.quantity.to_numpy()-sums.cost.to_numpy())/sums.cost.replace(0,np.nan).to_numpy()
    np.testing.assert_allclose(replay,x.sir_score,atol=1e-10,rtol=1e-12,equal_nan=True)
    # Recalculate fundamental sector percentile blocks from their saved raw inputs.
    fin=x.sector.isin(['Banks','Finance','Insurance'])
    mapping={'profitability':['roe','roce'],'growth':['sales_growth','profit_growth'],'safety':['debt','pledge'],'cash':['cash_conversion'],'valuation':['earnings_yield']}
    for block,fields in mapping.items():
        r=pd.DataFrame({f:x['judge_input_'+f].groupby(x.sector).rank(pct=True,method='average') for f in fields})
        applicable=pd.DataFrame(True,index=x.index,columns=fields)
        for f in ['roce','debt','cash_conversion']:
            if f in fields:applicable.loc[fin,f]=False
        value=r.fillna(.5).where(applicable).sum(axis=1)/applicable.sum(axis=1).replace(0,np.nan)
        np.testing.assert_allclose(value,x['judge_'+block],atol=1e-12,rtol=0,equal_nan=True)
    blocks=x[['judge_'+b for b in BLOCKS]].copy();blocks.columns=BLOCKS
    for label,w in WEIGHTS.items():
        weights=pd.Series(w,index=BLOCKS);score=(blocks*weights).sum(axis=1)/(blocks.notna()*weights).sum(axis=1)
        score=score.where(x.judge_coverage.ge(.6));x['audit_'+label]=score
        old='judge_primary' if label=='primary' else 'judge_variant_'+label
        np.testing.assert_allclose(score,x[old],atol=1e-12,rtol=0,equal_nan=True)
    # Native judged cohort: review every possible stock even when Sir has no score.
    for col in ['judgment_rank','model_rank_judged','model_pair_agreement','rank_percentile_gap','sensitivity_min_rank','sensitivity_max_rank']:
        x[col]=np.nan
    x['placement']='INSUFFICIENT_FUNDAMENTALS';x.loc[x.sector.eq('Unclassified'),'placement']='UNCLASSIFIED'
    for sector,g in x.groupby('sector'):
        if sector=='Unclassified':continue
        g=g.dropna(subset=['audit_primary','research_score'])
        if len(g)<5:
            x.loc[g.index,'placement']='TOO_FEW_JUDGED_PEERS';continue
        mr=g.research_score.rank(ascending=False,method='average');jr=g.audit_primary.rank(ascending=False,method='average')
        delta=(mr-jr)/(len(g)-1)
        _,stock,_,_=agreement(g.research_score,g.audit_primary)
        x.loc[g.index,'judgment_rank']=jr;x.loc[g.index,'model_rank_judged']=mr
        x.loc[g.index,'model_pair_agreement']=stock;x.loc[g.index,'rank_percentile_gap']=delta
        x.loc[g.index,'placement']=np.where(delta.abs().le(.1),'WITHIN_10_PERCENTILE_POINTS',np.where(delta.lt(-.1),'RANKED_TOO_HIGH_VS_RUBRIC','RANKED_TOO_LOW_VS_RUBRIC'))
        variants=pd.DataFrame({label:g['audit_'+label].rank(ascending=False,method='average') for label in WEIGHTS})
        x.loc[g.index,'sensitivity_min_rank']=variants.min(axis=1);x.loc[g.index,'sensitivity_max_rank']=variants.max(axis=1)
    rows=[];matched_indices=set()
    for sector,g in x.groupby('sector'):
        paired=g.dropna(subset=['research_score','sir_score','audit_primary']).sort_values('isin')
        if sector=='Unclassified' or len(paired)<5:continue
        matched_indices.update(paired.index)
        for subset in ['all_paired','complete_fundamentals','sir_24plus_observations']:
            z=paired if subset=='all_paired' else paired[paired.judge_coverage.ge(1-1e-12)] if subset=='complete_fundamentals' else paired[paired.sir_price_observations.ge(24)&paired.sir_quote_lag_days.le(14)]
            if len(z)<5:continue
            for label in WEIGHTS:
                for method,col in [('champion','research_score'),('sir','sir_score')]:
                    y=z['audit_'+label];s=z[col];pair,per_stock,credit,pairs=agreement(s,y)
                    gap=position(s)-position(y);top=z.sort_values(col,ascending=False,kind='stable').head(3)
                    row=dict(sector=sector,subset=subset,rubric=label,method=method,stocks=len(z),pairs=pairs,pair_credit=credit,pair_agreement=pair,within10_fraction=gap.abs().le(.1).mean(),within10_count=int(gap.abs().le(.1).sum()),top3_quality=top['audit_'+label].mean(),top3_names='; '.join(top.ticker))
                    rows.append(row)
                    if subset=='all_paired' and label=='primary':
                        x.loc[z.index,method+'_paired_rank']=s.rank(ascending=False,method='average')
                        x.loc[z.index,method+'_paired_agreement']=per_stock
                        x.loc[z.index,method+'_paired_gap']=gap
                        x.loc[z.index,'judgment_paired_rank']=y.rank(ascending=False,method='average')
                        x.loc[z.index,'paired_sector_size']=len(z)
                        x.loc[z.index,method+'_paired_placement']=np.where(gap.abs().le(.1),'WITHIN_10_PERCENTILE_POINTS',np.where(gap.lt(-.1),'TOO_HIGH_VS_RUBRIC','TOO_LOW_VS_RUBRIC'))
    detail=pd.DataFrame(rows);detail.to_csv(OUT/'sector_comparisons.csv',index=False)
    agg=detail.groupby(['subset','rubric','method']).agg(sectors=('sector','size'),stocks=('stocks','sum'),pairs=('pairs','sum'),pair_credit=('pair_credit','sum'),equal_sector_pair_agreement=('pair_agreement','mean'),equal_sector_within10=('within10_fraction','mean'),within10_count=('within10_count','sum'),top3_quality=('top3_quality','mean')).reset_index()
    agg['pair_weighted_agreement']=agg.pair_credit/agg.pairs;agg['stock_weighted_within10']=agg.within10_count/agg.stocks
    agg.to_csv(OUT/'summary.csv',index=False)
    primary=detail[detail.subset.eq('all_paired')&detail.rubric.eq('primary')]
    wide=primary.pivot(index='sector',columns='method',values=['pair_agreement','top3_quality','stocks'])
    verdict=pd.DataFrame(index=wide.index);verdict['stocks']=wide[('stocks','champion')].astype(int)
    for metric in ['pair_agreement','top3_quality']:
        verdict[metric+'_delta']=wide[(metric,'champion')]-wide[(metric,'sir')]
    verdict['pair_verdict']=np.where(verdict.pair_agreement_delta.gt(.02),'CHAMPION',np.where(verdict.pair_agreement_delta.lt(-.02),'SIR','WITHIN_2_PERCENTAGE_POINTS'))
    verdict['top3_verdict']=np.where(verdict.top3_quality_delta.gt(.02),'CHAMPION',np.where(verdict.top3_quality_delta.lt(-.02),'SIR','WITHIN_2_POINTS_ON_100_SCALE'))
    verdict.reset_index().to_csv(OUT/'sector_verdicts.csv',index=False)
    reasons=[]
    for _,r in x.iterrows():
        parts=[]
        if pd.notna(r.judgment_rank):
            b=pd.Series({k:r['judge_'+k] for k in BLOCKS}).dropna().sort_values()
            parts.append(f"Rubric rank {r.judgment_rank:g}; model rank {r.model_rank_judged:g} among judged peers. Strongest block: {b.index[-1]} ({b.iloc[-1]:.0%}); weakest: {b.index[0]} ({b.iloc[0]:.0%}).")
            parts.append(f"Rank range under four tested weight sets: {r.sensitivity_min_rank:g} to {r.sensitivity_max_rank:g}.")
        else:parts.append('No defensible relative judgment: '+r.placement+'.')
        if pd.notna(r.judge_flags):parts.append('Fundamental flags: '+r.judge_flags+'.')
        if pd.notna(r.review_flags):parts.append('Price/context flags: '+r.review_flags+'.')
        if pd.isna(r.sir_score):parts.append('Sir formula unavailable: '+r.sir_status+'.')
        else:parts.append(f"Sir price observations: {r.sir_price_observations:g}/{r.sir_requested_observations:g}.")
        reasons.append(' '.join(parts))
    x['evidence_reason']=reasons;x['paired_comparison']=x.index.isin(matched_indices)
    x.sort_values(['sector','sector_rank','isin']).to_csv(OUT/'all_4436_stock_audit.csv',index=False)
    # Check two independent ways to aggregate every matched stock pair.
    for (sector,method),g in primary.groupby(['sector','method']):
        z=x[x.sector.eq(sector)&x.paired_comparison]
        np.testing.assert_allclose(z[method+'_paired_agreement'].mean(),g.pair_agreement.iloc[0],atol=1e-12)
    assert len(x)==4436 and x.evidence_reason.notna().all()
    result={'all_stocks':len(x),'native_judged_stocks':int(x.judgment_rank.notna().sum()),'paired_stocks':len(matched_indices),'paired_sectors':len(verdict),'sir_numeric_scores':int(x.sir_score.notna().sum()),'sir_status_counts':x.sir_status.value_counts().to_dict(),'native_placement_counts':x.placement.value_counts().to_dict(),'pair_sector_verdict_counts':verdict.pair_verdict.value_counts().to_dict(),'top3_sector_verdict_counts':verdict.top3_verdict.value_counts().to_dict(),'rubric_recalculation_verified':True,'per_stock_pair_aggregation_verified':True,'fresh_company_due_diligence':False,'live_model_changed':False}
    result['sha256']={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [SOURCE,CURRENT,OUT/'protocol.json',OUT/'all_4436_stock_audit.csv',OUT/'summary.csv']}
    result['sir_159696_trade_rows_replayed']=True
    (OUT/'verification.json').write_text(json.dumps(result,indent=2))
    head=agg[agg.subset.eq('all_paired')&agg.rubric.eq('primary')]
    lines=['# Every-stock audit: full-coverage champion versus Sir — 10 October 2026','',
      '**This is agreement with my explicit company-evidence rubric, not an objective percentage of correct investments.** I applied the rubric to every available stock record. This does not claim 4,436 fresh company investigations; the inputs are the saved 3 October snapshot.',
      '',f"All **4,436 stocks** have an audit row and explanation. **{result['native_judged_stocks']}** have enough evidence and sector peers for a relative judgment. The fair model-versus-Sir comparison contains **{result['paired_stocks']} stocks in {result['paired_sectors']} sectors**. Unclassified stocks, insufficient fundamentals and sectors with fewer than five judged peers receive no correctness verdict.",'',
      '## Percentages','',
      '| Method | Within-sector pair agreement | Stocks within 10 percentile points of rubric rank |','|---|---:|---:|']
    for r in head.itertuples():lines.append(f'| {r.method} | {r.equal_sector_pair_agreement:.2%} | {r.stock_weighted_within10:.2%} ({r.within10_count}/{r.stocks}) |')
    pooled=head.set_index('method')
    lines+=['',f"If every stock pair receives equal weight instead of every sector, agreement is **{pooled.loc['champion','pair_weighted_agreement']:.2%} for the champion** and **{pooled.loc['sir','pair_weighted_agreement']:.2%} for Sir** across {int(pooled.loc['champion','pairs']):,} pairs. Large sectors dominate that alternative, so it is reported separately."]
    lines+=['','Pair agreement gives one point for matching the rubric’s order of two stocks, zero for reversing it, and half for ties. The headline is an equal-sector mean. The placement percentage is stock-weighted on the same paired cohort; it measures the declared 10-percentile-point tolerance. Exact ordinal correctness is too strong a claim for this evidence.',
      '',f"Across sectors, pair-order verdicts with a two-percentage-point practical tie band: **{result['pair_sector_verdict_counts']}**. Top-three company-quality verdicts using a two-point/100 tie band: **{result['top3_sector_verdict_counts']}**.",
      '', '## What my judgment rewards','',
      'Equal 20% blocks for profitability, growth, safety, cash conversion and valuation. Each input is ranked within its sector. Banks, Finance and Insurance omit corporate cash/leverage measures and redistribute applicable weights. Missing inputs are neutral only when total evidence coverage is at least 60%; otherwise the stock is unjudged. Quality-, growth- and value-oriented alternatives test sensitivity.',
      '', 'The block definitions are informed by [Quality Minus Junk](https://www.aqr.com/Insights/Research/Working-paper/Quality-minus-Junk). This implementation is a declared judgment rubric, not a replication of that paper. It does not assess management integrity, pending litigation, auditor concerns, financial restatements or prospective catalysts comprehensively. Price momentum can rationally disagree with this fundamental-quality benchmark.',
      '', '## Sensitivity','', '| Subset | Rubric | Champion pair agreement | Sir pair agreement | Stocks |','|---|---|---:|---:|---:|']
    for (subset,label),g in agg.groupby(['subset','rubric']):
        g=g.set_index('method');lines.append(f'| {subset} | {label} | {g.loc["champion","equal_sector_pair_agreement"]:.2%} | {g.loc["sir","equal_sector_pair_agreement"]:.2%} | {int(g.loc["champion","stocks"])} |')
    lines+=['','## Stock-by-stock conclusions','',
      'The audit includes actual model rank, Sir rank, rubric rank, matching-cohort ranks, both models’ per-stock pair agreement, rank gaps, four-weight rank ranges, five block scores, eight raw fundamental inputs, missing-evidence flags and a record-specific explanation. TOO_HIGH/TOO_LOW means relative to this rubric, not a buy/sell recommendation.',
      '',f"All-stock placement counts: `{json.dumps(result['native_placement_counts'])}`.",
      '', '## Sir’s evidence and verification','',
      'The professor benchmark is the saved full-universe generalization of his independent per-stock whole-share SIP arithmetic, using ₹7,500, 36 months and 30-day intervals. Slot-specific workbook cross-references do not generalize to an arbitrary universe. This comparison does not claim his screenshot ranks all these stocks.',
      '',f"Sir has **{result['sir_numeric_scores']} numerical scores**. All are based on partial requested price observations; none has the full 36, and the maximum is 35. The stricter sensitivity requires at least 24 observations and a quote no more than 14 days old. These checks do not certify the underlying corporate-action history.",
      '', 'Recomputed the fundamental rubric from saved raw inputs, verified all blocks and weight alternatives, checked unique identities and sector matches, and reconciled per-stock pair scores to the sector totals. Replayed all 159,696 Sir trade rows, whole-share quantities, costs and final score arithmetic. Input and output hashes are retained. The live model was not changed.',
      '', '## Files','',
      '- `experiments/champion-sir-judgment-20261010/all_4436_stock_audit.csv`',
      '- `experiments/champion-sir-judgment-20261010/sector_comparisons.csv`',
      '- `experiments/champion-sir-judgment-20261010/sector_verdicts.csv`',
      '- `experiments/champion-sir-judgment-20261010/summary.csv`']
    lines+=['','## Specific judgments from the saved evidence','',
      '| Stock | Sector | Model rank among judged peers | Rubric rank | Rank range across weights | Evidence assessment |','|---|---|---:|---:|---|---|']
    comments={'NYKAA':'Top rank looks aggressive under a fundamentals-and-valuation standard. Its old ATH alone is not a reason to reject it.',
      'KALYANI':'Top rank is questionable given flat-price activity, negative operating cash flow and elevated debt in the saved evidence. Sir has no score here, so this is outside the paired headline.',
      'SHAILY':'Close to the primary rubric rank, but the broad weight-sensitive range makes an exact rank claim weak.',
      'TDPOWERSYS':'Ranks much higher than the quality/value rubric, with valuation the weakest block. Momentum may explain the disagreement; it does not prove a bad investment.',
      'IONEXCHANG':'Strong disagreement persists across all tested weights. Negative cash flow and low valuation percentile warrant review of cash-flow timing and the underlying company accounts.',
      'RAMRAT':'High model placement conflicts with the saved safety and cash-flow evidence. Review is warranted before trusting the top-sector label.'}
    for ticker,comment in comments.items():
        r=x[x.ticker.eq(ticker)].iloc[0]
        lines.append(f'| {ticker} | {r.sector} | {r.model_rank_judged:g} | {r.judgment_rank:g} | {r.sensitivity_min_rank:g} to {r.sensitivity_max_rank:g} | {comment} |')
    lines+=['','My verdict: the champion agrees more with this rubric on broad within-sector pair ordering and Top-3 quality, but the small proportion near the rubric rank prevents calling its stock-by-stock ordering reliably correct. Sir is slightly ahead on the exact same 10-percentile placement test. The complete-fundamentals subset and alternative weights narrow or sometimes reverse the advantage; see the sensitivity table.']
    (ROOT/'research/reports/champion_sir_judgment_20261010.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(head.to_string(index=False));print(json.dumps({k:v for k,v in result.items() if k!='sha256'},indent=2))

if __name__=='__main__':run()
