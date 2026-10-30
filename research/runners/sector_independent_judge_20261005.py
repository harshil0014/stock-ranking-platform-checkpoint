"""All-stock, within-sector comparison against a declared fundamental rubric.

This is an analytical judgment benchmark, NOT labels of future investment returns.
Sir's arithmetic is imported from the isolated replication; no model is fit here.
"""
from pathlib import Path
from datetime import date
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from professor_exact_formula_20261005 import schedule, calculate, DEFAULT_WORKBOOK, M, R

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'experiments/sector-independent-judge-20261005'
PACKAGE = ROOT / 'research/runtime/personalized-v17'
FINANCIAL = {'Banks', 'Finance', 'Insurance'}
PROTOCOL = {
    'as_of': '2026-10-03', 'amount': 7500, 'lookback_months': 36, 'interval_days': 30,
    'objective': 'Within-sector fundamental investment-quality judgment; not future-return truth',
    'primary_weights': {'profitability': .2, 'growth': .2, 'safety': .2, 'cash': .2, 'valuation': .2},
    'sensitivity_weights': {
        'quality': {'profitability': .3, 'growth': .15, 'safety': .2, 'cash': .25, 'valuation': .1},
        'growth': {'profitability': .2, 'growth': .35, 'safety': .1, 'cash': .15, 'valuation': .2},
        'value': {'profitability': .2, 'growth': .15, 'safety': .15, 'cash': .15, 'valuation': .35}},
    'missing_values': 'Within-block missing metrics neutral .5; coverage >= .6 for judged rank. Missingness exported.',
    'financial_sectors': 'Banks/Finance/Insurance omit corporate leverage and cash-conversion metrics; reweight remaining blocks.',
    'primary_comparison': 'Top-3 mean judge score, same stocks per sector; 2 points/100 practical tie band',
    'also_report': ['Spearman over all common stocks', 'NDCG@3', 'top1', 'top10', 'coverage', 'weight sensitivity'],
    'small_sectors': 'Fewer than 5 common judged stocks: no comparative verdict',
    'sir_data_adapter': 'Stored raw_close; first observation in inclusive [request_start, request_start+1 calendar day]; latest close <= as_of. No search beyond window.',
    'sir_scope': 'Generalize independent per-stock SIP arithmetic to all identities; workbook slot-specific cross-references have no natural full-universe equivalent.',
    'no_training': True, 'no_price_momentum_or_high_age_in_judge': True,
    'sources': ['https://www.aqr.com/-/media/AQR/Documents/Insights/Working-Papers/Quality-Minus-Junk.pdf',
                'https://support.google.com/docs/answer/3093281?hl=en'],
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workbook_universe():
    """Extract both cached ATH tables; retain code-level duplicates across tables."""
    rows, evidence = [], {}
    with ZipFile(DEFAULT_WORKBOOK) as z:
        shared = [''.join(t.text or '' for t in s.iter(M+'t')) for s in ET.fromstring(z.read('xl/sharedStrings.xml')).findall(M+'si')]
        rels = {r.attrib['Id']: r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        sheets = ET.fromstring(z.read('xl/workbook.xml')).findall(M+'sheets/'+M+'sheet')
        target = next(rels[s.attrib[R+'id']] for s in sheets if s.attrib['name'] == 'ATH').lstrip('/')
        if not target.startswith('xl/'): target = 'xl/' + target
        with z.open(target) as f:
            for _, row in ET.iterparse(f, events=['end']):
                if row.tag != M+'row': continue
                rn = int(row.attrib['r']); vals = {}
                for c in row.findall(M+'c'):
                    a = c.attrib['r']; col = ''.join(filter(str.isalpha, a)); v = c.find(M+'v'); form = c.find(M+'f')
                    if col not in ['A','B','C','I','J']: continue
                    val = v.text if v is not None else None
                    if c.attrib.get('t') == 's' and val is not None: val = shared[int(val)]
                    vals[col] = val
                    if rn == 1 and form is not None: evidence[a] = form.text
                if rn > 1:
                    for codecol, table in [('B','ATH prices'), ('I','Industry and CAGR')]:
                        code = str(vals.get(codecol) or '').strip()
                        if code.startswith(('NSE:', 'BOM:')):
                            rows.append({'sheet_row': rn, 'table': table, 'code': code,
                                         'company': vals.get('C') if codecol == 'B' else '',
                                         'workbook_industry': vals.get('J') if codecol == 'I' else ''})
                row.clear()
    pd.DataFrame(rows).to_csv(OUT/'workbook_stock_inventory.csv', index=False)
    return pd.DataFrame(rows), evidence


def load_histories():
    histories = {}
    for filename in ['history.npz', 'peak_history.npz']:
        with np.load(PACKAGE/filename) as z:
            dates, prices = z['dates'], z['raw']
            for i, identity in enumerate(z['identities']):
                a, b = z['offsets'][i:i+2]
                histories[str(identity)] = (dates[a:b].copy(), prices[a:b].copy())
    return histories


def window_price(days, prices, start, cutoff):
    i = int(np.searchsorted(days, start))
    if i < len(days) and days[i] <= min(start + 1, cutoff) and np.isfinite(prices[i]) and prices[i] > 0:
        return int(days[i]), float(prices[i])
    return None, None


def sir_all(facts):
    histories = load_histories()
    sched = schedule(date.fromisoformat(PROTOCOL['as_of']))
    cutoff = int(np.datetime64(PROTOCOL['as_of']).astype('datetime64[D]').astype(int))
    starts = [int(np.datetime64(d['request_start']).astype('datetime64[D]').astype(int)) for d in sched]
    results, trades = [], []
    for row in facts.itertuples():
        history = histories.get(row.isin)
        ps, quote, quote_day, count = {}, None, None, 0
        if history is not None:
            days, prices = history
            assert np.all(np.diff(days) > 0), row.isin
            terminal = int(np.searchsorted(days, cutoff, side='right')) - 1
            if terminal >= 0 and np.isfinite(prices[terminal]) and prices[terminal] > 0:
                quote, quote_day = float(prices[terminal]), int(days[terminal])
        for d, start in zip(sched, starts):
            observed, price = window_price(*history, start, cutoff) if history is not None else (None, None)
            ps[d['history_row']] = price
            count += price is not None
            trades.append({'isin': row.isin, **d, 'observed_day': observed, 'close': price,
                           'quantity': np.trunc(7500/price) if price is not None else 0,
                           'cost': np.trunc(7500/price)*price if price is not None else 0})
        r, _ = calculate(ps, quote)
        score = r['profit_fraction'] if isinstance(r['profit_fraction'], (int,float)) and quote is not None else np.nan
        results.append({'isin': row.isin, 'sir_score': score, 'sir_invested': r['invested'],
                        'sir_shares': r['shares_bought'], 'sir_current_value': r['current_value'],
                        'sir_price_observations': count, 'sir_requested_observations': len(sched),
                        'sir_quote': quote, 'sir_quote_date': str(np.datetime64(quote_day,'D')) if quote_day is not None else '',
                        'sir_quote_lag_days': cutoff-quote_day if quote_day is not None else np.nan,
                        'sir_status': 'NO_HISTORY' if history is None else 'NO_QUOTE' if quote is None else 'NO_INVESTMENT' if not r['invested'] else 'COMPLETE_OBSERVATIONS' if count==len(sched) else 'PARTIAL_OBSERVATIONS'})
    pd.DataFrame(trades).to_csv(OUT/'sir_trade_ledger.csv.gz', index=False, compression='gzip')
    pd.DataFrame(sched).to_csv(OUT/'sir_schedule.csv',index=False)
    return pd.DataFrame(results)


def judge(f, financial_sectors=FINANCIAL):
    """Only raw fundamental fields enter this function. Neither ranking is an input."""
    f = f.copy(); sector = f.product_sector.fillna('Unclassified'); fin = sector.isin(financial_sectors)
    num = lambda col: pd.to_numeric(f[col], errors='coerce').replace([np.inf,-np.inf],np.nan)
    pat = num('screener_profit_after_tax_crore')
    pe = num('screener_pe_ratio')
    metrics = {
        'roe': num('screener_roe_3y_avg_pct'), 'roce': num('screener_roce_3y_avg_pct').mask(fin),
        'sales_growth': num('screener_sales_growth_3y_pct'), 'profit_growth': num('screener_profit_growth_3y_pct'),
        'debt': -num('screener_debt_to_equity').mask(fin), 'pledge': -num('screener_pledged_pct'),
        'cash_conversion': (num('screener_operating_cash_flow_crore') / pat.where(pat>0)).mask(fin),
        'earnings_yield': (1/pe.where(pe>0)).mask(pat<=0,0),
    }
    blocks = {'profitability':['roe','roce'],'growth':['sales_growth','profit_growth'],
              'safety':['debt','pledge'],'cash':['cash_conversion'],'valuation':['earnings_yield']}
    ranks = {k:v.groupby(sector).rank(pct=True,method='average') for k,v in metrics.items()}
    for k,v in metrics.items(): f['judge_input_'+k]=v
    for block, keys in blocks.items():
        r = pd.DataFrame({k:ranks[k] for k in keys})
        eligible_count = pd.Series(len(keys),index=f.index)
        if block in ['profitability','safety']: eligible_count = eligible_count.mask(fin,1)
        if block=='cash': eligible_count = eligible_count.mask(fin,0)
        # Structural exclusions do not become neutral observations.
        applicable = r.notna() | True
        if block=='profitability': applicable.loc[fin,'roce']=False
        if block=='safety': applicable.loc[fin,'debt']=False
        if block=='cash': applicable.loc[fin,'cash_conversion']=False
        f['judge_'+block] = r.fillna(.5).where(applicable).sum(axis=1)/eligible_count.replace(0,np.nan)
        f['coverage_'+block] = r.notna().sum(axis=1)/eligible_count.replace(0,np.nan)
    f['judge_coverage'] = f[['coverage_'+k for k in blocks]].mean(axis=1)
    for label, weights in {'primary':PROTOCOL['primary_weights'],**PROTOCOL['sensitivity_weights']}.items():
        b = f[['judge_'+k for k in weights]].rename(columns=lambda x:x[6:])
        w = pd.Series(weights)
        output = 'judge_primary' if label=='primary' else 'judge_variant_'+label
        f[output] = (b*w).sum(axis=1)/(b.notna()*w).sum(axis=1)
        f.loc[f.judge_coverage<.6,output]=np.nan
    f['judge_rank'] = f.judge_primary.where(sector.ne('Unclassified')).groupby(sector).rank(ascending=False,method='min')
    f['judge_flags'] = ['; '.join(filter(None,[
        'loss-making' if pd.notna(pat.iloc[i]) and pat.iloc[i]<=0 else '',
        'pledge over 20%' if num('screener_pledged_pct').iloc[i]>20 else '',
        'negative operating cash flow' if not fin.iloc[i] and num('screener_operating_cash_flow_crore').iloc[i]<0 else '',
        'debt/equity over 2' if not fin.iloc[i] and num('screener_debt_to_equity').iloc[i]>2 else '',
        'fundamentals incomplete' if f.judge_coverage.iloc[i]<1 else '',
        'financial-sector cash/leverage analysis unavailable' if fin.iloc[i] else ''
    ])) for i in range(len(f))]
    return f


def compare(x):
    rows = []
    for sector,g in x.groupby('product_sector',dropna=False):
        paired = g[g.current_score.notna() & g.sir_score.notna() & g.judge_primary.notna()].sort_values('isin')
        r = {'sector':sector,'stocks':len(g),'current_ranked':int(g.current_score.notna().sum()),
             'sir_ranked':int(g.sir_score.notna().sum()),'judge_ranked':int(g.judge_primary.notna().sum()),'common':len(paired)}
        if sector=='Unclassified' or len(paired)<5:
            r['verdict']='INSUFFICIENT_COMPARABLE_STOCKS';rows.append(r);continue
        for name, score in [('current','current_score'),('sir','sir_score')]:
            ranked = paired.sort_values([score,'isin'],ascending=[False,True])
            r[name+'_rho'] = float(spearmanr(paired[score],paired.judge_primary).statistic)
            r[name+'_top1'] = float(ranked.judge_primary.iloc[0])
            r[name+'_top3'] = float(ranked.judge_primary.head(3).mean())
            r[name+'_top10'] = float(ranked.judge_primary.head(10).mean())
            weights=1/np.log2(np.arange(3)+2)
            r[name+'_ndcg3']=float(np.dot(ranked.judge_primary.head(3),weights)/np.dot(paired.judge_primary.nlargest(3),weights))
            r[name+'_top3_names']='; '.join(ranked.ticker.head(3))
            for sensitivity in PROTOCOL['sensitivity_weights']:
                r[name+'_'+sensitivity]=float(ranked['judge_variant_'+sensitivity].head(3).mean())
        delta=r['current_top3']-r['sir_top3'];r['top3_delta']=delta
        r['verdict']='CURRENT' if delta>.02 else 'SIR' if delta<-.02 else 'PRACTICAL_TIE'
        signs=[r['current_'+s]-r['sir_'+s] for s in PROTOCOL['sensitivity_weights']]
        r['weight_sensitive']=any(v*delta<0 for v in signs)
        rows.append(r)
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(exist_ok=True)
    # Persist the protocol before any competing scores are loaded or compared.
    p=OUT/'protocol.json'; encoded=json.dumps(PROTOCOL,indent=2)
    if p.exists() and p.read_text()!=encoded: raise ValueError('Protocol already locked differently')
    p.write_text(encoded)
    inventory, sheet_evidence = workbook_universe()
    facts=pd.read_csv(PACKAGE/'facts.csv.gz',low_memory=False)
    facts['product_sector']=facts.product_sector.fillna('Unclassified')
    for r in json.loads((PACKAGE/'sector_review.json').read_text())['entries']:
        facts.loc[facts['isin'].eq(r['isin']),'product_sector']=r['sector']
    assert len(facts)==facts['isin'].nunique()
    print('Judging',len(facts),'stocks',flush=True)
    x=judge(facts)
    print('Calculating Sir across all stocks',flush=True)
    sir=sir_all(facts)
    current_path=ROOT/'experiments/sector-championship-20261005/corrected_current_rankings.csv.gz'
    current=pd.read_csv(current_path);current=current[current.profile_name.eq('base7500')]
    assert len(current)==len(facts) and not current['isin'].duplicated().any()
    current=current.rename(columns={'sector_rank':'personalized_sector_rank'})
    current['personalized_available']=current.personalized_score.notna()
    cur=current[['isin','personalized_score','personalized_available','personalized_sector_rank']].copy()
    cur['current_score']=cur.personalized_score.where(cur.personalized_available)
    x=x.merge(sir,on='isin',validate='one_to_one').merge(cur,on='isin',validate='one_to_one')
    x['sir_sector_rank']=x.sir_score.where(x.product_sector.ne('Unclassified')).groupby(x.product_sector).rank(ascending=False,method='min')
    x['common_comparison']=x.current_score.notna() & x.sir_score.notna() & x.judge_primary.notna() & x.product_sector.ne('Unclassified')
    x['sir_common_rank']=x.sir_score.where(x.common_comparison).groupby(x.product_sector).rank(ascending=False,method='min')
    x['current_common_rank']=x.current_score.where(x.common_comparison).groupby(x.product_sector).rank(ascending=False,method='min')
    x['judge_common_rank']=x.judge_primary.where(x.common_comparison).groupby(x.product_sector).rank(ascending=False,method='min')
    fields=['isin','ticker','company','product_sector','current_score','personalized_sector_rank','sir_score','sir_sector_rank','judge_primary','judge_rank','judge_coverage','judge_flags','common_comparison','current_common_rank','sir_common_rank','judge_common_rank']
    fields += [c for c in x if c.startswith(('sir_','judge_input_','coverage_')) and c not in fields]
    fields += ['judge_'+c for c in ['profitability','growth','safety','cash','valuation','variant_quality','variant_growth','variant_value'] if 'judge_'+c not in fields]
    fields += ['screener_source_observed_at','screener_fresh_export_observed_at','screener_batch2_observed_at']
    fields=list(dict.fromkeys(fields))
    x.sort_values(['product_sector','judge_rank','isin'])[fields].to_csv(OUT/'all_stock_sector_judgments.csv',index=False)
    scores=compare(x);scores.to_csv(OUT/'sector_verdicts.csv',index=False)
    # Join workbook codes by exact identifiers only. No fuzzy identity substitution.
    aliases={}
    for r in facts.itertuples():
        code=('BOM:'+str(r.exchange_security_id).split('.')[0]) if r.primary_exchange=='BSE' else 'NSE:'+r.ticker
        aliases.setdefault(code,set()).add(r.isin)
    inventory['matched_isin']=inventory.code.map(lambda c: next(iter(aliases[c])) if c in aliases and len(aliases[c])==1 else None)
    inventory['match_status']=np.where(inventory.matched_isin.notna(),'EXACT_PRIMARY_CODE','UNMATCHED_OR_SECONDARY_LISTING')
    inventory.to_csv(OUT/'workbook_universe_coverage.csv',index=False)
    full_sheet=inventory.sort_values('table').drop_duplicates('code').merge(
        x[fields],left_on='matched_isin',right_on='isin',how='left',validate='many_to_one',suffixes=('_workbook',''))
    full_sheet.to_csv(OUT/'all_workbook_stock_judgments.csv',index=False)
    native=[]
    for sector,g in x.groupby('product_sector'):
        for method,col in [('current','current_score'),('sir','sir_score')]:
            top=g[g[col].notna()].sort_values([col,'isin'],ascending=[False,True]).head(3)
            native.append({'sector':sector,'method':method,'selected':len(top),'judged':int(top.judge_primary.notna().sum()),
                           'mean_judge_score':top.judge_primary.mean(),
                           'top_names':'; '.join(top.ticker),
                           'partial_price_observations':int(top.sir_status.eq('PARTIAL_OBSERVATIONS').sum()),
                           'min_price_observations':top.sir_price_observations.min() if len(top) else np.nan})
    pd.DataFrame(native).to_csv(OUT/'native_top3_coverage.csv',index=False)
    comparable=scores[scores['verdict'].ne('INSUFFICIENT_COMPARABLE_STOCKS')]
    summary={'stocks':len(x),'sectors':x.product_sector.nunique(),'common_stocks':int(x.common_comparison.sum()),
             'current_ranked':int(x.current_score.notna().sum()),'sir_ranked':int(x.sir_score.notna().sum()),
             'judge_ranked':int(x.judge_primary.notna().sum()),'comparable_sectors':len(comparable),
             'sector_verdict_counts':scores.verdict.value_counts().to_dict(),
             'sir_data_status':x.sir_status.value_counts().to_dict(),
             'weight_sensitive_sectors':int(comparable.weight_sensitive.sum()),
             'sensitivity_mean_top3_delta':{s:float((comparable['current_'+s]-comparable['sir_'+s]).mean()) for s in PROTOCOL['sensitivity_weights']},
             'sector_equal_mean':{c:float(comparable[c].mean()) for c in ['current_top1','sir_top1','current_top3','sir_top3','current_top10','sir_top10','current_rho','sir_rho','current_ndcg3','sir_ndcg3']},
             'workbook_unique_codes':inventory.code.nunique(),'workbook_tables':inventory.groupby('table').code.nunique().to_dict(),
             'workbook_matched_unique_codes':inventory.loc[inventory.matched_isin.notna(),'code'].nunique(),
             'protocol_sha256':digest(p),'source_hashes':{str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path):digest(path) for path in [PACKAGE/'facts.csv.gz',PACKAGE/'history.npz',PACKAGE/'peak_history.npz',current_path,DEFAULT_WORKBOOK]},
             'workbook_reference_formulas':sheet_evidence,
             'limitations':['Judge is a declared fundamental rubric, not omniscient AI labels or individually researched company valuations.',
                 'Sir uses an explicit local price adapter, not verified live GoogleFinance parity.',
                 'Only 1746 stocks receive current-model scores; all others remain visible as abstentions.',
                 'Snapshot fundamentals may contain stale/misaligned or bad vendor fields; cash flow and profit periods need scrutiny.',
                 'This is not evidence of greater future-return accuracy.']}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in summary.items() if k not in ['source_hashes','workbook_reference_formulas','limitations']},indent=2),flush=True)


if __name__=='__main__': main()
