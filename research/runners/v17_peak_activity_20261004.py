"""Closing-high recency and activity research, with dated provider features."""
import sys, json, gc
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import lightgbm as lgb
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'research/runners'), str(ROOT/'src')]
import v17_peak_context_20261004 as p
a, v = p.a, p.v
O = ROOT/'experiments/v17-peak-activity-20261004'
O.mkdir(exist_ok=True)
EXTRA = ['high52_freshness', 'nonzero_fraction', 'volume_active_fraction',
         'high_support', 'momentum_12_1', 'quote_freshness', 'traded_value', 'long_peak_freshness']


def write(name, obj):
    (O/name).write_text(json.dumps(v.clean(obj), indent=2, allow_nan=False), encoding='utf-8')


def build():
    dates = set(pd.read_pickle(a.s.O/'historical.pkl').decision_date.unique())
    dates.update(pd.read_csv(p.BASE/'exposed_refined_scores.csv.gz', usecols=['decision_date']).decision_date.unique())
    dates.add('2026-10-03')
    facts = pd.read_csv(v.V7, low_memory=False)
    frames = {}
    for path in sorted(v.YAHOO.glob('*.pkl')):
        entry = pd.read_pickle(path)
        for symbol, f in entry.get('frames', {}).items():
            if f is not None and len(f) and (symbol not in frames or len(f)>len(frames[symbol])):
                frames[symbol] = f
    rows = []
    for i, row in enumerate(facts.itertuples()):
        frame = frames.get(row.yahoo_symbol)
        if frame is None or 'Adj Close' not in frame: continue
        f = frame.copy()
        f.index = pd.to_datetime(f.index).tz_localize(None)
        f = f[~f.index.duplicated(keep='last')].sort_index()
        f = f[np.isfinite(f['Adj Close']) & f['Adj Close'].gt(0)]
        d = f.index.to_numpy(dtype='datetime64[D]')
        close = f['Adj Close'].to_numpy(float)
        raw = f['Close'].to_numpy(float)
        volume = f['Volume'].to_numpy(float)
        for day in sorted(dates):
            cutoff = np.datetime64(day)
            hi = int(np.searchsorted(d, cutoff, side='right'))
            lo = int(np.searchsorted(d, cutoff-np.timedelta64(365,'D')))
            prices = close[lo:hi]
            if len(prices)<40: continue
            assert d[hi-1] <= cutoff
            returns = prices[1:]/prices[:-1]-1
            high = np.max(prices)
            high_day = d[lo+np.flatnonzero(prices==high)[-1]]
            age = int((cutoff-high_day)/np.timedelta64(1,'D'))
            lag = int((cutoff-d[hi-1])/np.timedelta64(1,'D'))
            end1 = np.searchsorted(d, cutoff-np.timedelta64(30,'D'), side='right')-1
            start12 = np.searchsorted(d, cutoff-np.timedelta64(365,'D'), side='right')-1
            momentum = close[end1]/close[start12]-1 if start12>=0 and end1>start12 else np.nan
            vv = volume[lo:hi]
            rows.append({'isin':row.isin, 'decision_date':day,
                'high52_freshness':365/(365+age), 'days_since_52w_closing_high':age,
                'nonzero_fraction':float(np.mean(np.abs(returns)>1e-8)),
                'volume_active_fraction':float(np.mean(vv>0)) if np.isfinite(vv).any() else np.nan,
                'high_support':float(np.mean(prices>=.9*high)),
                'momentum_12_1':float(momentum), 'quote_freshness':30/(30+lag),
                'traded_value':float(np.log1p(np.nanmedian(raw[lo:hi]*vv))),
                'observations_1y':len(prices), 'last_observed_date':str(d[hi-1])})
        if i%500==0: print('FEATURES', i, len(rows), flush=True)
    out = pd.DataFrame(rows)
    assert not out.duplicated(['isin','decision_date']).any()
    assert (out.last_observed_date<=out.decision_date).all()
    out.to_csv(O/'dated_features.csv.gz', index=False)
    feature_audit()


def feature_audit():
    out = pd.read_csv(O/'dated_features.csv.gz')
    assert not out.duplicated(['isin','decision_date']).any()
    assert (out.last_observed_date<=out.decision_date).all()
    write('feature_audit.json', {'rows':len(out), 'stocks':out['isin'].nunique(), 'dates':out.decision_date.nunique(),
        'minimum_observations':40, 'no_future_prices':True,
        'limits':'Current-universe symbol mapping and retrospectively adjusted provider history inherit survivorship and revision limits of this research. Sparse observations are counted; no forward fill or zero-volume imputation.'})


def trade_freshness():
    write('execution_freshness_amendment.json', {'created_at':datetime.now(timezone.utc).isoformat(),
        'reason':'A recent quote can have zero volume. Require a positive-reported-volume observation within seven days, in addition to annual activity and quoted-price freshness.',
        'last_trade_lag_days_max':7, 'score_weights_unchanged':True})
    data=pd.read_csv(O/'dated_features.csv.gz')
    facts=pd.read_csv(v.V7,low_memory=False).set_index('isin')
    frames={}
    for path in sorted(v.YAHOO.glob('*.pkl')):
        for symbol,f in pd.read_pickle(path).get('frames',{}).items():
            if f is not None and len(f) and (symbol not in frames or len(f)>len(frames[symbol])):frames[symbol]=f
    data['last_positive_volume_lag_days']=np.nan
    for isin,g in data.groupby('isin'):
        f=frames.get(facts.loc[isin,'yahoo_symbol'])
        if f is None:continue
        dates=pd.to_datetime(f.index).tz_localize(None).to_numpy(dtype='datetime64[D]')
        good=np.sort(dates[f.Volume.to_numpy()>0])
        if not len(good):continue
        decisions=pd.to_datetime(g.decision_date).to_numpy(dtype='datetime64[D]')
        loc=np.searchsorted(good,decisions,side='right')-1
        valid=loc>=0
        lag=np.full(len(g),np.nan)
        lag[valid]=(decisions[valid]-good[loc[valid]]).astype('timedelta64[D]').astype(float)
        data.loc[g.index,'last_positive_volume_lag_days']=lag
    data.to_csv(O/'dated_features.csv.gz',index=False)
    assert data.last_positive_volume_lag_days.dropna().ge(0).all()
    print('TRADE FRESHNESS',data.last_positive_volume_lag_days.notna().sum(),flush=True)


def features(source):
    z = a.features(source).merge(pd.read_csv(O/'dated_features.csv.gz'), on=['isin','decision_date'], how='left', validate='many_to_one')
    z['long_peak_freshness'] = np.exp(-z.days_since_recorded_high.clip(lower=0)/1826.25)
    for c in EXTRA:
        z['p_'+c] = z.groupby(['decision_date','profile_name'])[c].rank(pct=True).fillna(.5).astype('float32')
    return z


def fit(source, test, tag):
    cols = a.s.NORM+a.EXTRA+['p_'+c for c in EXTRA]
    train = source[source.endpoint.lt(test.decision_date.min())].dropna(subset=v.OUTCOME+['enhanced_carry_xirr_score']).copy()
    assert train.endpoint.max()<test.decision_date.min()
    groups = train.groupby(['decision_date','profile_name'])
    weights = 1/groups.isin.transform('size'); weights /= weights.mean()
    constraints = [1]*len(a.s.POS+a.s.NEG)+[0]*len(a.s.CONTEXT)+[1]*(len(a.EXTRA)+len(EXTRA))
    model = lgb.LGBMRegressor(n_estimators=160, learning_rate=.035, num_leaves=15, max_depth=4,
        min_child_samples=300, reg_lambda=40, n_jobs=4, verbosity=-1, deterministic=True,
        force_col_wise=True, random_state=20261004, monotone_constraints=constraints,
        monotone_constraints_method='advanced')
    model.fit(train[cols], a.s.target(train), sample_weight=weights)
    model.booster_.save_model(str(O/f'model_{tag}.txt'))
    write(f'audit_{tag}.json', {'max_training_endpoint':train.endpoint.max(),
        'first_scored_date':test.decision_date.min(), 'rows':len(train), 'features':cols})
    return pd.Series(model.predict(test[cols],num_threads=4), index=test.index)


def pct(z, raw):
    return raw.where(z.repair_score.notna()).groupby([z.decision_date,z.profile_name]).rank(pct=True)


def score(z, raw, alpha):
    return (z.repair_score*(1-alpha)+alpha*pct(z,raw)-.005*z.evidence_confidence*p.components(z)['age_momentum']).where(z.repair_score.notna())


def search():
    if not (O/'protocol.json').exists():
        write('protocol.json', {'created_at':datetime.now(timezone.utc).isoformat(),
            'features':EXTRA, 'alphas':[.05,.1,.2,.35], 'direct_age_penalty':.005,
            'selection':'Highest utility among aggregate median XIRR, NDCG, drawdown, achievement nonnegative and shortfall nonpositive versus V17 refined. Profile tradeoffs reported, current overlap not required.',
            'exposure':'Hypothesis follows prior historical/current inspection; no blind-validation claim.',
            'sources':['https://academic.oup.com/rfs/article-abstract/12/5/1113/1565408',
                'https://www.sciencedirect.com/science/article/abs/pii/S0378426613002446',
                'https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4587697']})
    x = features(pd.read_pickle(a.s.O/'historical.pkl'))
    z = x.merge(pd.read_csv(p.BASE/'development_refined_scores.csv.gz', usecols=p.KEYS+['repair_score']), on=p.KEYS,validate='one_to_one')
    raw = pd.Series(np.nan,index=z.index)
    for year in ['2020','2021','2022','2023']:
        test = z[z.decision_date.str.startswith(year)]
        raw.loc[test.index] = fit(x,test,year)
        print('FIT',year,flush=True)
    z[p.KEYS].assign(prediction=raw).to_csv(O/'development_predictions.csv.gz',index=False)
    ref = v.evaluate(z,'repair_score'); records=[]
    for alpha in [.05,.1,.2,.35]:
        z['candidate_score'] = score(z,raw,alpha)
        st = p.summary(z,'candidate_score',ref); d=st['delta']
        eligible = min(d[k] for k in ['median_xirr_top20','ndcg20','mean_asset_drawdown_top20','target_achievement_top20'])>=0 and d['target_shortfall_top20']<=0
        records.append({'alpha':alpha, 'eligible':eligible, **st})
        print('ACTIVITY',alpha,eligible,st['utility'],flush=True)
    write('trials.json',records)
    passing=[r for r in records if r['eligible']]
    write('selection_lock.json', {'winner':max(passing,key=lambda r:r['utility']) if passing else None,
        'locked_at':datetime.now(timezone.utc).isoformat()})


def priority_score(z):
    """Fixed investor preference, not weights estimated from outcome labels."""
    z = z.copy()
    age = z.days_since_recorded_high.clip(lower=0)
    z['closing_high_component'] = (.5*np.exp(-age/1095.75)
        +.3*(1+z.distance_from_recorded_high.clip(-1,0))+.2*z.high52_freshness)
    z['momentum_component'] = z.groupby(['decision_date','profile_name']).momentum_12_1.rank(pct=True).fillna(.5)
    z['priority_score_unfiltered'] = .7*z.repair_score+.2*z.closing_high_component+.1*z.momentum_component
    z['median_daily_value'] = np.expm1(z.traded_value)
    z['activity_eligible'] = (z.volume_active_fraction.ge(.8)
        & z.median_daily_value.ge(100*z.amount_per_contribution)
        & z.observations_1y.ge(120) & z.quote_freshness.ge(30/37)
        & z.last_positive_volume_lag_days.le(7)
        & z.closing_high_component.notna() & z.repair_score.notna())
    z['priority_score'] = z.priority_score_unfiltered.where(z.activity_eligible)
    z['eligible_v17_score'] = z.repair_score.where(z.activity_eligible)
    z['research_rank_unfiltered'] = v.ranked(z,'priority_score_unfiltered')
    z['activity_filter_reason'] = np.select([
        z.repair_score.isna(),z.closing_high_component.isna()|z.volume_active_fraction.isna()|z.traded_value.isna(),
        z.observations_1y.lt(120),z.quote_freshness.lt(30/37)|z.last_positive_volume_lag_days.gt(7)|z.last_positive_volume_lag_days.isna(),z.volume_active_fraction.lt(.8),
        z.median_daily_value.lt(100*z.amount_per_contribution)],
        ['BASELINE_UNAVAILABLE','ACTIVITY_OR_HIGH_UNVERIFIED','LESS_THAN_120_OBSERVATIONS',
         'NO_RECENT_QUOTE_OR_REPORTED_TRADE','INFREQUENT_REPORTED_TRADING','INSUFFICIENT_REPORTED_TRADED_VALUE'],default='ELIGIBLE')
    z['priority_rank'] = v.ranked(z,'priority_score')
    return z


def priority():
    if not (O/'priority_protocol.json').exists():
        write('priority_protocol.json', {'created_at':datetime.now(timezone.utc).isoformat(),
            'purpose':'User preference for materially stronger closing-high influence with execution plausibility. This is not a claim to maximize historical returns.',
            'weights':{'V17_refined':.7,'closing_high':.2,'momentum_12_1_percentile':.1},
            'closing_high_formula':'.5*exp(-ATH_age_days/1095.75)+.3*(1+ATH_distance)+.2*365/(365+52week_high_age_days)',
            'activity_screen':{'positive_volume_fraction_min':.8,'median_daily_value_over_contribution_min':100,'observations_1y_min':120,'quote_lag_days_max':7},
            'screen_interpretation':'A contribution is at most 1% of median reported daily traded value. This is an eligibility assumption, not a measured transaction cost or fill guarantee.',
            'benchmark':'Show original V17 and V17 on exactly the same eligible stocks. Fixed formula; no selection of weights from resulting company ranks.',
            'exposure':'Design uses current-universe diagnostics and already-researched history; no fresh holdout.'})
    outputs=[];coverage=[]
    for period in ['development','early','exposed']:
        source = v.load_historical(True) if period=='exposed' else pd.read_pickle(a.s.O/'historical.pkl')
        source = features(source)
        scores = pd.read_csv(p.BASE/f'{period}_refined_scores.csv.gz',usecols=p.KEYS+['repair_score'])
        z = source.merge(scores,on=p.KEYS,validate='one_to_one')
        assert len(z)==len(scores)
        z=priority_score(z)
        for model in ['repair_score','eligible_v17_score','priority_score']:
            met=v.evaluate(z,model);met['period']=period;met['model']=model;outputs.append(met)
        coverage.append(z.groupby(['decision_date','profile_name']).agg(universe=('isin','size'),baseline_ranked=('repair_score','count'),priority_ranked=('priority_score','count')).reset_index().assign(period=period))
        z[p.KEYS+['priority_score','priority_rank','activity_eligible']].to_csv(O/f'priority_{period}_scores.csv.gz',index=False)
        print('PRIORITY',period,int(z.priority_score.notna().sum()),flush=True)
        del source,z;gc.collect()
    metrics=pd.concat(outputs,ignore_index=True)
    metrics.to_csv(O/'priority_metrics.csv',index=False)
    pd.concat(coverage,ignore_index=True).to_csv(O/'priority_coverage.csv',index=False)
    metrics.groupby(['period','model'])[v.METRICS].mean().reset_index().to_csv(O/'priority_summary.csv',index=False)
    current=features(pd.read_csv(p.BASE/'final_current_rankings.csv.gz',low_memory=False))
    current['repair_score']=current.winner_score
    current=priority_score(current)
    current.to_csv(O/'priority_current_rankings.csv.gz',index=False)
    for n in [20,50,100]:
        current[current.priority_rank.le(n)].sort_values(['profile_name','priority_rank']).to_csv(O/f'priority_current_top{n}.csv',index=False)
    # Holding all other inputs fixed, moving the ATH date further into the
    # past must never increase the explicit preference score.
    old=current.copy();old.days_since_recorded_high=old.days_since_recorded_high+365
    older=priority_score(old)
    valid=current.priority_score_unfiltered.notna()&older.priority_score_unfiltered.notna()
    assert (older.loc[valid,'priority_score_unfiltered']<=current.loc[valid,'priority_score_unfiltered']+1e-12).all()
    observed=metrics.decision_date.nunique()
    assert observed==44, observed
    write('priority_audit.json',{'decision_dates':observed,'current_universe':current['isin'].nunique(),
        'current_eligible_default':int(current.loc[current.profile_name.eq('base7500'),'priority_score'].notna().sum()),
        'older_ath_score_never_increases':True,'sensitivity_rows':int(valid.sum()),
        'website_changed':False,'status':'Preference-aligned experimental model; backtest tradeoffs are published'})


def report():
    current=priority_score(pd.read_csv(O/'priority_current_rankings.csv.gz',low_memory=False))
    current.to_csv(O/'priority_current_rankings.csv.gz',index=False)
    for n in [20,50,100]:
        current[current.priority_rank.le(n)].sort_values(['profile_name','priority_rank']).to_csv(O/f'priority_current_top{n}.csv',index=False)
    base=current[current.profile_name.eq('base7500')]
    columns=['ticker','company','winner_rank','research_rank_unfiltered','priority_rank','days_since_recorded_high',
        'days_since_52w_closing_high','volume_active_fraction','median_daily_value','closing_high_component',
        'momentum_component','priority_score','activity_filter_reason']
    base[columns].sort_values('priority_rank').to_csv(O/'default_rankings_readable.csv',index=False)
    diagnostics=current[current.ticker.isin(['NYKAA','BSE-519413'])][['profile_name']+columns]
    diagnostics.to_csv(O/'stock_diagnostics.csv',index=False)
    counter=[]
    nykaa=base[base.ticker.eq('NYKAA')].iloc[0]
    for age in [30,365,1765,3650]:
        high=.5*np.exp(-age/1095.75)+.3*(1+nykaa.distance_from_recorded_high)+.2*nykaa.high52_freshness
        val=.7*nykaa.repair_score+.2*high+.1*nykaa.momentum_component
        others=base[base.ticker.ne('NYKAA')].priority_score.dropna()
        counter.append({'age_days':age,'score':val,'rank_holding_other_stocks_fixed':int((others>val).sum()+1)})
    pd.DataFrame(counter).to_csv(O/'nykaa_age_sensitivity.csv',index=False)
    stats=pd.read_csv(O/'priority_summary.csv')
    metrics=pd.read_csv(O/'priority_metrics.csv')
    pair=v.compare_metrics(metrics[metrics.model.eq('priority_score')],metrics[metrics.model.eq('eligible_v17_score')])
    pair.to_csv(O/'same_universe_profile_date_comparison.csv',index=False)
    grouped=pair.groupby('profile')[[c+'_delta' for c in v.METRICS]].mean()
    grouped.to_csv(O/'same_universe_profile_deltas.csv')
    activity=json.loads((O/'feature_audit.json').read_text())
    audit=json.loads((O/'priority_audit.json').read_text())
    balanced=json.loads((p.OUT/'decision.json').read_text())
    lines=['# Closing-high-priority research model', '',
        'The requested stronger closing-high preference is implemented as an explicit 20% score component. This is a fixed preference model; it is not claimed to outperform V17 on every return metric. A separate balanced experimental model provides stronger aggregate historical return results.', '',
        '## Exact score and eligibility','',
        '`score = 0.70 * V17_refined + 0.20 * closing_high_component + 0.10 * momentum_12_1_percentile`','',
        '`closing_high_component = 0.50 * exp(-ATH_age_days / 1095.75) + 0.30 * (1 + ATH_distance) + 0.20 * 365 / (365 + age_of_52_week_closing_high)`','',
        'Thus lifetime closing-high age has a direct 10% score weight, closeness to the lifetime closing high 6%, and rolling closing-high recency 4%. V17 contributes its existing high-price signals as well. Raising ATH age while holding the remaining inputs fixed cannot improve the new explicit score.', '',
        'Lifetime ATH fields retain the frozen benchmark definition (age at the last quote and first occurrence for equal highs). The new rolling-high age uses the latest equal adjusted closing high in the preceding 365 days, measured at the decision date. NYKAA has no equal-ATH tie; its 1,765-day stored age is preserved.', '',
        'The eligible shortlist requires at least 120 observations over the last year, positive reported volume on at least 80% of those observations, both a quote and a positive-volume observation within seven calendar days, and median daily reported traded value of at least 100 times the contribution. This represents an assumed maximum 1% participation in median daily traded value; it does not measure transaction costs or guarantee execution.', '',
        'Every stock remains in the full export with its unfiltered research rank and explicit eligibility reason. Missing activity evidence is not represented as proven liquidity.', '',
        f"Validation covers {audit['decision_dates']} historical decision dates and {audit['current_universe']:,} current stocks. The default eligible shortlist contains {audit['current_eligible_default']:,} scored stocks. New provider features cover {activity['rows']:,} stock/date observations, {activity['stocks']:,} stocks, and {activity['dates']} dates including training dates. Features use no quotes after the observation date.", '',
        '## Historical comparison','',
        'Rates are averages of date/profile Top20 basket statistics, not a portfolio CAGR or a transaction-cost-adjusted trading backtest. Drawdown is average asset drawdown; closer to zero is better. The same-universe V17 row applies exactly the new eligibility screen, so the model comparison does not attribute the screen itself to better scoring.', '',
        '| Period | Model | Top20 median XIRR | Achievement | Shortfall | Asset drawdown | NDCG@20 |',
        '|---|---|---:|---:|---:|---:|---:|']
    names={'repair_score':'V17 original universe','eligible_v17_score':'V17 same eligible universe','priority_score':'Closing-high priority'}
    for r in stats.itertuples():
        lines.append(f'| {r.period} | {names[r.model]} | {r.median_xirr_top20:.2%} | {r.target_achievement_top20:.2%} | {r.target_shortfall_top20:.2%} | {r.mean_asset_drawdown_top20:.2%} | {r.ndcg20:.4f} |')
    lines+=['','Profile changes against V17 on the same eligible stocks, averaged across the 44 dates:', '',
        '| Profile | Median XIRR change (pp) | Drawdown change (pp) |','|---|---:|---:|']
    for name,r in grouped.iterrows():
        lines.append(f'| {name} | {100*r.median_xirr_top20_delta:+.2f} | {100*r.mean_asset_drawdown_top20_delta:+.2f} |')
    lines+=['','## Alternative balanced experimental model','',
        'The earlier selected age/momentum model blends 90% V17 refined with 10% learned age-aware ranking plus an explicit age/momentum penalty. It is available in `experiments/v17-peak-context-20261004/current_top20.csv`. Its median-return/drawdown changes against V17 refined are:','',
        '| Period | Median XIRR change (pp) | Drawdown change (pp) |','|---|---:|---:|']
    for period, result in balanced['results'].items():
        d=result['delta'];lines.append(f"| {period} | {100*d['median_xirr_top20']:+.2f} | {100*d['mean_asset_drawdown_top20']:+.2f} |")
    lines+=['','The balanced alternative has profile tradeoffs: its development default-profile median XIRR falls 3.64 percentage points and its 60-month profile falls 3.91 points. It was selected under aggregate rules adopted after the user authorized a broader redesign, not the earlier all-profile gates. Previously observed results are not a fresh holdout.', '',
        '## Current default Top20','', '| Rank | Company | Ticker | ATH age (days) | Positive-volume fraction |', '|---:|---|---|---:|---:|']
    for r in base[base.priority_rank.le(20)].sort_values('priority_rank').itertuples():
        lines.append(f'| {int(r.priority_rank)} | {r.company} | {r.ticker} | {r.days_since_recorded_high:.0f} | {r.volume_active_fraction:.1%} |')
    lines+=['','## NYKAA and the liquidity diagnostic','',
        f"NYKAA retains its verified 1,765-day ATH age. Its default V17 rank is {int(nykaa.winner_rank)}, its new unfiltered rank is {int(nykaa.research_rank_unfiltered)}, and its eligible shortlist rank is {int(nykaa.priority_rank)}. Its rolling 52-week closing high is {int(nykaa.days_since_52w_closing_high)} days old and positive reported volume occurs on {nykaa.volume_active_fraction:.1%} of observations. Those facts explain why an old lifetime peak and a recent annual peak can coexist.", '',
        'Datiware (BSE-519413) has positive reported volume on only about 16% of observations and is excluded from the eligible shortlist. Its apparently low volatility is not treated as sufficient evidence of tradability. These are provider observations, not an allegation about the company.', '',
        '| Hypothetical NYKAA ATH age | Rank with other inputs and companies fixed |', '|---:|---:|']
    for r in counter:lines.append(f"| {r['age_days']} | {r['rank_holding_other_stocks_fixed']} |")
    lines+=['','## Research evidence and limits','',
        '- [Bhootra and Hur (2013)](https://www.sciencedirect.com/science/article/abs/pii/S0378426613002446) studies recency of the 52-week high as a momentum signal. It motivates rolling-high age; it does not establish an optimal ATH penalty here.',
        '- [Raju, Indian 52-week-high study](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4587697) motivates high-price proximity in Indian equities.',
        '- [Lesmond, Ogden and Trzcinka (1999)](https://academic.oup.com/rfs/article-abstract/12/5/1113/1565408) uses zero returns in transaction-cost estimation. It motivates investigating inactive prices; it does not validate the fixed 80% activity screen.',
        '- Development, early history, and 2024-2025 periods have all been exposed during this research. Current-universe mapping and adjusted provider histories carry survivorship/revision limitations. No fresh holdout, causal profitability claim, or execution guarantee is supplied.',
        '- The extra learned activity model and stronger logarithmic age penalties were also tested. Their full trial ledgers are retained; they were not chosen as return improvements. The priority model is an explicit preference design, not a relabeling of those trial results.',
        '- Product website rankings have not been switched. This package supplies reproducible research rankings and a materially stronger closing-high option for review.', '',
        '## Files','',
        '`priority_current_top20.csv`, `priority_current_top50.csv`, `priority_current_top100.csv`: all nine profiles. `default_rankings_readable.csv`: compact default ranking and eligibility reasons. `stock_diagnostics.csv` and `nykaa_age_sensitivity.csv`: company diagnostics. `priority_metrics.csv` and `same_universe_profile_date_comparison.csv`: full dated benchmarks. `priority_protocol.json` fixes the design.', '']
    (ROOT/'research/reports/v17_closing_high_priority_20261004.md').write_text('\n'.join(lines),encoding='utf-8')
    print('REPORT COMPLETE',flush=True)


def verify():
    current=pd.read_csv(O/'priority_current_rankings.csv.gz',low_memory=False)
    baseline=pd.read_csv(p.BASE/'final_current_rankings.csv.gz',usecols=p.KEYS)
    assert not current.duplicated(p.KEYS).any()
    assert len(current.merge(baseline,on=p.KEYS,validate='one_to_one'))==len(baseline)==len(current)
    reconstructed=priority_score(current)
    np.testing.assert_allclose(current.priority_score,reconstructed.priority_score,equal_nan=True,rtol=0,atol=1e-12)
    np.testing.assert_allclose(current.priority_rank,reconstructed.priority_rank,equal_nan=True,rtol=0,atol=0)
    assert current.loc[current.priority_score.notna(),'last_positive_volume_lag_days'].le(7).all()
    assert current.loc[~current.activity_eligible,'priority_score'].isna().all()
    metrics=pd.read_csv(O/'priority_metrics.csv')
    common=v.compare_metrics(metrics[metrics.model.eq('priority_score')],metrics[metrics.model.eq('eligible_v17_score')])
    assert len(common)==44*9
    assert (common.n_v15==common.n_champion).all()
    assert common.n_v15.ge(20).all()
    hashes=json.loads((p.OUT/'baseline_hashes.json').read_text())
    assert all(p.sha(ROOT/name)==h for name,h in hashes.items())
    for n in [20,50,100]:
        top=pd.read_csv(O/f'priority_current_top{n}.csv')
        assert len(top)==9*n
        assert top.priority_rank.le(n).all()
    audit={'score_and_rank_reproduced':True,'identical_benchmark_universe_per_query':True,
        'date_profile_queries':len(common),'minimum_eligible_basket':int(common.n_v15.min()),
        'full_universe_rows_preserved':len(current),'baseline_hashes_unchanged':True,
        'all_top_exports_verified':True,'recent_positive_volume_enforced':True}
    write('verification.json',audit)
    write('manifest.json',{'model':'V17 closing-high priority','status':'Experimental preference model',
        'formula':'70% V17 refined, 20% closing high, 10% 12-1 momentum',
        'inputs_and_outputs':{str(file.relative_to(ROOT)):p.sha(file) for file in [
            Path(__file__),O/'priority_protocol.json',O/'execution_freshness_amendment.json',
            O/'dated_features.csv.gz',O/'priority_current_rankings.csv.gz',O/'priority_metrics.csv',
            O/'verification.json']}})
    print(json.dumps(audit),flush=True)


if __name__=='__main__':
    globals()[sys.argv[1]]()
