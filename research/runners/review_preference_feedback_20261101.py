"""Independent read-only feedback audit. No new candidates, fitting or promotion."""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[key]='1'
from pathlib import Path
import hashlib,itertools,json
import numpy as np
import pandas as pd
from stock_research.professor_factor_model import price_features, FACTOR_COLUMNS

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/professor-preference-review-20261101'


def table(x):
    return '| '+' | '.join(map(str,x.columns))+' |\n| '+' | '.join(['---']*len(x.columns))+' |\n'+''.join('| '+' | '.join(map(str,row))+' |\n' for row in x.itertuples(index=False,name=None))


def polish_report(text):
    lines=[];performance=False
    for line in text.splitlines():
        if line.startswith('| model | period | rank_ic | attainment3 |'):
            line='| model | period | rank_ic | goal_hit_pct | selected_stock_drawdown_pct | alignment_percentile |';performance=True
        elif line.startswith('| ') and not line.startswith('| ---'):
            cells=[s.strip() for s in line.strip('|').split('|')]
            for i,value in enumerate(cells):
                try:
                    number=float(value)
                    if performance and i>=3:number*=100
                    if '.' in value or (performance and i>=3):cells[i]=f'{number:.4f}'
                except ValueError:pass
            line='| '+' | '.join(cells)+' |'
        elif not line.startswith('| '):performance=False
        lines.append(line)
    text='\n'.join(lines)+'\n'
    for a,b in {'November2026':'November 2026','The20%':'The 20%','The2396':'The 2,396','is2.218':'is 2.218','a2 pplimit':'a 2 pp limit','loss is0.00747':'loss is 0.00747','worsens1.67':'worsens 1.67','%relatively':'% relatively','%lens':'% lens','round69.71':'round 69.71','lens(20%)':'lens (20%)','a98%':'a 98%','this54%':'this 54%','across28':'across 28','October3':'October 3'}.items():text=text.replace(a,b)
    return text


def corr_rows(x,cols,pairs=None,cohort='eligible'):
    rows=[]
    for (day,sector),g in x.groupby(['decision_date','sector']):
        if len(g)<5:continue
        for a,b in pairs if pairs is not None else itertools.combinations(cols,2):
            h=g[[a,b]].replace([np.inf,-np.inf],np.nan).dropna()
            if len(h)<5 or h[a].nunique()<2 or h[b].nunique()<2:continue
            rows.append(dict(decision_date=day,period='development' if day<'2024-01-01' else 'exposed' if day<'2026-01-01' else 'current',sector=sector,cohort=cohort,a=a,b=b,n=len(h),rho=float(h[a].corr(h[b],method='spearman'))))
    return rows


def aggregate(rows):
    x=pd.DataFrame(rows)
    counts=x.groupby(['period','cohort','a','b']).agg(queries=('rho','size'),dates=('decision_date','nunique')).reset_index()
    means=x.groupby(['period','cohort','a','b','decision_date']).rho.mean().groupby(['period','cohort','a','b']).mean().reset_index()
    return means.merge(counts,on=['period','cohort','a','b'])


def main():
    OUT.mkdir(exist_ok=True)
    folder=ROOT/'experiments/professor-weight-curve-20261031'
    x=pd.read_pickle(folder/'scored.pkl.gz',compression='gzip')
    x=x.loc[x.decision_date.ge('2020-01-01')].copy()
    rawpath=ROOT/'research/runtime/personalized-v17/history.npz'
    x['log_nominal_price']=np.nan;x['log_provider_close']=np.nan
    samples=x.loc[x.factor_eligible & x.decision_date.lt('2026-01-01')].copy()
    samples['sample_key']=[hashlib.sha256((i+'|'+d).encode()).hexdigest() for i,d in zip(samples['isin'],samples.decision_date)]
    samples=samples.sort_values('sample_key').groupby('decision_date').head(2)
    audits=[]
    with np.load(rawpath,allow_pickle=False) as a:
        ids=a['identities'].astype(str);offsets=a['offsets'];dates=a['dates'].astype('datetime64[D]');raw=a['raw'];nominal=a['nominal']
        groups=x.groupby('isin').groups;samplegroups=samples.groupby('isin').groups
        for k,identity in enumerate(ids):
            if identity not in groups:continue
            lo,hi=int(offsets[k]),int(offsets[k+1]);d=dates[lo:hi];p=raw[lo:hi];np_=nominal[lo:hi]
            selected=x.loc[groups[identity]];wanted=selected.decision_date.to_numpy(dtype='datetime64[D]')
            loc=np.searchsorted(d,wanted,side='right')-1
            valid=loc>=0
            if valid.any():
                indices=selected.index[valid];at=loc[valid];days=wanted[valid]
                okay=((days-d[at]).astype(int)<=7)&np.isfinite(np_[at])&(np_[at]>0)&np.isfinite(p[at])&(p[at]>0)
                x.loc[indices[okay],'log_nominal_price']=np.log(np_[at[okay]])
                x.loc[indices[okay],'log_provider_close']=np.log(p[at[okay]])
            if identity in samplegroups:
                for row in samples.loc[samplegroups[identity]].itertuples():
                    rebuilt=price_features(d,p,row.decision_date)
                    expected={c:getattr(row,c) for c in rebuilt}
                    error=max(abs(rebuilt[c]-expected[c]) for c in rebuilt)
                    altered=p.copy();altered[d>np.datetime64(row.decision_date)]=1e12
                    second=price_features(d,altered,row.decision_date)
                    invariant=all(rebuilt[c]==second[c] for c in rebuilt)
                    assert error<=1e-12 and invariant
                    audits.append(dict(isin=identity,decision_date=row.decision_date,max_error=error,future_price_perturbation_invariant=invariant))
    # Idle cash earns zero; keep integer-purchase behaviour unchanged.
    frac=x.sip_invested_fraction.where(x.sip_invested_fraction.between(0,1))
    x['full_budget_idle_cash_profit']=x.sip_profit*frac
    eligible=x.loc[x.factor_eligible].copy()
    cols=['champion_percentile','factor20_fixed']+['q_'+c for c in FACTOR_COLUMNS]
    rows=corr_rows(eligible,cols)
    summary=aggregate(rows);summary.to_csv(OUT/'factor_correlations.csv',index=False,lineterminator='\n')
    pairs=[('sip_profit','log_nominal_price'),('sip_profit','log_provider_close'),('sip_invested_fraction','log_nominal_price'),('full_budget_idle_cash_profit','log_nominal_price'),('sip_profit','full_budget_idle_cash_profit')]
    price=[]
    for label,z in [('before_factor_eligibility',x.loc[x.sector.notna()&x.sector.ne('Unclassified')]),('eligible_lens',eligible)]:price.extend(corr_rows(z,[],pairs,label))
    prices=aggregate(price);prices.to_csv(OUT/'price_level_correlations.csv',index=False,lineterminator='\n')
    current=x.loc[x.decision_date.eq('2026-10-03')].copy()
    features=['cagr3','cagr5','high_recency']+[f'annual{i}' for i in range(1,6)]
    reasons={
      'missing_one_or_more_required_price_features':int(current[features].isna().any(axis=1).sum()),
      'missing_five_annual_returns':int(current[[f'annual{i}' for i in range(1,6)]].isna().any(axis=1).sum()),
      'missing_5Y_CAGR':int(current.cagr5.isna().sum()),
      'missing_SIP_profit':int(current.sip_profit.isna().sum()),
      'known_SIP_action_block':int(current.sip_action_blocked.sum()),
      'investment_fraction_below_half_or_unknown':int((~current.sip_invested_fraction.ge(.5)).sum()),
      'inactive_or_missing_volume':int((~current.volume_active_fraction.ge(.8)).sum()),
      'stale_or_missing_positive_volume':int((~current.last_positive_volume_lag_days.between(0,14)).sum()),
      'unclassified':int(current.sector.eq('Unclassified').sum()),
      'total_unavailable':int((~current.factor_eligible).sum())}
    # Counts overlap; missing price features also include guarded action windows.
    old=json.loads(Path(r'C:\Users\Harshil\Documents\Codex\2026-10-31\you\outputs\tested-Sir-factor-priority-evidence-20261031.json').read_text())
    old_value=old['paired_complete_feature_alignment']['cagr_3y']['active_champion']
    new=pd.read_csv(folder/'summary_development.csv').set_index('model').loc['factor20_fixed']
    recomputed=float(new[['q_'+c for c in FACTOR_COLUMNS]].mean()*100)
    assert abs(recomputed-new.alignment*100)<1e-12
    receipt=dict(no_training=True,no_new_candidates=True,no_weights_changed=True,historical_price_feature_replays=len(audits),
                 max_price_feature_error=max(r['max_error'] for r in audits),future_price_tests_passed=all(r['future_price_perturbation_invariant'] for r in audits),
                 old_current_champion_3year_percentile=old_value,new_development_lens_alignment=recomputed,
                 equality_check='Different exact values and definitions; both round69.71. New alignment independently equals the mean of its five reported component means.',
                 coverage_reasons_overlapping=reasons,source_date_audit=json.loads((ROOT/'experiments/champion-sip-profit-20261017/source_date_audit.json').read_text()),
                 pit_boundary='Prefix price calculations replay, but provider historical vintages,sectors and complete announcement-known action histories are not certified PIT. Trailing SIP is imported from dated archived simulations,not independently rebuilt here.',
                 execution_timing_status='NOT_CERTIFIED: price features may include decision-date close while the portfolio proxy can buy that close; live pipeline needs first executable fill strictly after forecast issuance.')
    (OUT/'audit_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');pd.DataFrame(audits).to_csv(OUT/'prefix_replays.csv',index=False,lineterminator='\n')
    baseline=[]
    for name,file,profile in [('Original broad benchmark: nine profiles','full/sector_summary.csv',None),('Original broad benchmark: base7500','full/profile_name_slices.csv','base7500')]:
        z=pd.read_csv(ROOT/'experiments/champion-vs-market-20261031'/file)
        z=z.loc[z.model.eq('active_champion')]
        if profile:z=z.loc[z.profile_name.eq(profile)]
        for row in z.itertuples():baseline.append(dict(cohort=name,period=row.period,rank_ic=row.rank_ic,drawdown_pct=row.drawdown3*100))
    for row in pd.read_csv(folder/'summary.csv').query("model == 'active_champion'").itertuples():baseline.append(dict(cohort='Long-history complete-factor: base7500',period=row.period,rank_ic=row.rank_ic,drawdown_pct=row.drawdown3*100))
    baselines=pd.DataFrame(baseline);baselines.to_csv(OUT/'baseline_cohorts.csv',index=False,lineterminator='\n')
    text='# Review of the proposed checks: results and corrections\n\n1 November2026. Read-only audit; no new weights,candidates,training,registration or production changes. Descriptive name: **Long-history momentum lens(20%)**; historical model ID remains unchanged.\n\n'
    text+='## Verdict\n\nThe criticism is mostly correct. The20%lens passed only the separately registered retrospective **alignment/IC/selected-stock-drawdown point gate**. It did not pass the earlier small-SIP-tilt stream\'s investment adoption rule. Its development globalTop20mean SIP XIRR loss is2.218pp,which exceeds a2pplimit; that old stream also freezes a different candidate. Do not silently transfer or rewrite either protocol. No performance upgrade or production promotion is justified.\n\n'
    text+='## Exposed results were recorded\n\n'+table(pd.read_csv(folder/'summary.csv').query("model in ['active_champion','factor20_fixed']")[['model','period','rank_ic','attainment3','drawdown3','alignment']])+'\nThey are diagnostics only. Development IC falls about45.2%relatively; describing that as a negligible accuracy cost would be misleading. The absolute loss is0.00747. Exposed selected-stock drawdown worsens1.67pp; the positive exposed global portfolio XIRR difference rests on only7/12valid dates.\n\n'
    text+='## The different champion numbers are different supports\n\n'+table(baselines)+'\nThe new table uses one profile,a stricter six-year-boundary/complete-factor universe,additional data guards,and family-wide matched Top3outcome availability. It is not the broad nine-profile cohort. The2396eligible issuers are the current snapshot count,not a fixed historical membership list. The raw champion scoring rule is unchanged; its within-sector percentile is recomputed over the shared lens cohort.\n\n'
    text+=f'## The repeated69.71 is a rounding coincidence\n\nOld October3champion3Y-CAGR percentile: **{old_value:.12f}**. New development lens five-factor alignment: **{recomputed:.12f}**. Both round69.71,but they are different quantities. The latter was independently reconciled to the mean of five component summary values,not copied from the former.\n\n'
    text+='## Correlation audit: nominal weights are not independent influence\n\nSpearman correlations are calculated within sector/date on the complete eligible cohort,then equal-sector averages within date and equal-date averages within period. Constant or unsupported pairs are unavailable. These are descriptive dependency measures,not causal attribution.\n\n'
    important=summary.loc[(summary.a.eq('champion_percentile')&summary.b.eq('factor20_fixed'))|summary.a.eq('factor20_fixed')].copy()
    text+=table(important)+'\nThe full component-pair matrix is in factor_correlations.csv. Annual returns,CAGRs,SIP profit and recency overlap; the existing champion also contains price/high signals.20%is an explicit coefficient budget on normalized blocks,not20%independent information,turnover or predictive influence.\n\n'
    text+='## Price level and cash-denominator audit\n\n'+table(prices)+'\nThe SIP factor is profit divided by actual invested capital,excluding unused cash. The audit compares it with log reconstructed nominal price and log provider split-adjusted Close. The zero-interest full-budget diagnostic equals stored profit times invested fraction; it retains unused cash without reinvesting it and is not XIRR. The>=50%investment-utilisation guard attenuates extreme unaffordability but cannot establish absence of price-level bias. Correlations do not identify a causal rounding effect. No score was changed to use this diagnostic.\n\n'
    text+='## Missing history stays unavailable\n\n'+table(pd.DataFrame([dict(reason=k,count=v) for k,v in reasons.items()]))+'\nReason counts overlap. Missing price features combine insufficient history and known invalid adjustment windows; they do not all imply a recent IPO. Five completed annual returns need six year-end boundaries. No neutral imputation or per-stock weight redistribution is used. Other stocks retain the separate champion rank. Long-history survivors are a selected population; within-cohort comparison does not remove survivorship bias.\n\n'
    text+=f'## Historical cutoffs: verified narrowly,not certified PIT\n\nIndependently replayed **{len(audits)}**historical feature cases across28decision dates,checking all five annual returns,3Y/5Y CAGR and recorded-high age. Maximum difference from stored features: **{receipt["max_price_feature_error"]}**. Replacing all later prices with an extreme value changed none of these features. Thus they were not calculated once from October3and pasted into historical rows.\n\n'
    text+='Trailing SIP comes from dated archived simulations; the earlier full-source as-of audit is included in audit_receipt.json. We did not independently rebuild every historical SIP purchase here. Provider-price vintages,retrospective sectors and announcement-known corporate-action state are not independently point-in-time certified. Price-prefix correctness alone does not prove an investable historical pipeline.\n\n'
    text+='## Additional execution-timing boundary\n\nThe price-feature function includes an observed close on the decision date. The existing fractional portfolio proxy starts its contribution schedule on that date and uses the first price on or after it,so it permits buying the same close on trading dates. There is no demonstrated forecast-issuance time that would make that fill executable. This is a code-path finding,not a measured estimate of the resulting bias. A fresh pipeline must enforce a first executable fill after forecast issuance; reproducing the old batch formula alone is insufficient. Historical results remain research proxies. Archived-date parity must also pin that date\'s model weights,preprocessor and universe. Applying the current2026model to2020inputs cannot be expected to reproduce an archived2020annual-fold model.\n\n'
    text+='## What to take from the recommendations\n\nKeep the current weights frozen and the production champion unchanged. Do not start a fresh holdout clock or silently replace the already registered small-tilt stream. A verified daily-input manifest,adjustment guards and archived-date end-to-end score parity are required before eligible shadow forecasts. Daily market prices need trading-session freshness;sector classifications and fundamental filings need their own availability/version policies rather than a blanket daily rule.\n\nA98%coverage threshold is a design choice,not a number validated by these results;it cannot be silently applied to this54%-coverage long-history lens. Keep one primary prospective comparison once inputs exist and report dependence/multiplicity. Running a scheduler off the laptop may be sensible,but it requires an actual host,credentials,resource budget and parity-tested implementation;no cloud deployment or spend was authorised by the pasted advice. No fresh pipeline or scheduler was created by this audit.\n'
    # Keep report prose readable without changing numeric evidence.
    from report_professor_majority_20261031 import clean_prose
    text=polish_report(clean_prose(text))
    target=ROOT/'research/reports/preference_feedback_review_20261101.md';target.write_text(text,encoding='utf-8')
    outputs=Path(r'C:\Users\Harshil\Documents\Codex\2026-10-31\you\outputs');(outputs/'Preference-feedback-review-20261101.md').write_text(text,encoding='utf-8')
    (OUT/'evidence_manifest.json').write_text(json.dumps({str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name!='evidence_manifest.json'},indent=2)+'\n')
    print(json.dumps(receipt,indent=2),flush=True)
    print(important.to_string(index=False),flush=True)
    print(prices.loc[prices.cohort.eq('eligible_lens')].to_string(index=False),flush=True)


if __name__=='__main__':main()
