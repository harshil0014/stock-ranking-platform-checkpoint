"""Frozen-score age attribution diagnostics; no training or product mutation."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'research/reports/top100-human-review-20261004'
SOURCE = ROOT / 'experiments/v17-peak-confirmation-20261004/current_rankings.csv.gz'
FACTS = ROOT / 'experiments/current-data-recovery-20261003/current_company_facts_recovered_v7_full_yahoo.csv.gz'

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    d = pd.read_csv(SOURCE, low_memory=False)
    d = d[d.profile_name.eq('base7500')].copy()
    age = d.days_since_recorded_high.clip(lower=0)
    d['explicit_age_points'] = .15 * np.exp(-age / 1095.75)
    d['explicit_proximity_points'] = .09 * (1 + d.distance_from_recorded_high.clip(-1, 0))
    d['explicit_rolling_points'] = .06 * d.high52_freshness
    reproduced = .5*d.repair_score+d.explicit_age_points+d.explicit_proximity_points+d.explicit_rolling_points+.1*d.momentum_component+.1*d.downside_confirmation
    np.testing.assert_allclose(reproduced[d.activity_eligible], d.loc[d.activity_eligible, 'new_score'], atol=1e-12, rtol=0)
    eligible = d.new_score.notna()
    assert eligible.equals(d.activity_eligible)
    scores = d.loc[eligible, 'new_score'].to_numpy()
    for days in [30, 365]:
        altered = d.new_score-d.explicit_age_points+.15*np.exp(-days/1095.75)
        d[f'age_{days}_score'] = altered
        # One stock changed at a time. Remove its original self from the comparison.
        d[f'age_{days}_rank_other_stocks_fixed'] = [
            1+int(np.sum(scores > value))-int(old > value) if pd.notna(value) else np.nan
            for value, old in zip(altered, d.new_score)]
    scenarios = {
        'remove_explicit_age': d.new_score-d.explicit_age_points,
        'replace_age_with_rolling_same_decay': d.new_score-d.explicit_age_points+.15*np.exp(-d.days_since_52w_closing_high/1095.75),
        'replace_age_with_rolling_freshness': d.new_score-d.explicit_age_points+.15*d.high52_freshness,
    }
    for name, values in scenarios.items():
        d[name+'_score'] = values
        d[name+'_rank'] = values.rank(ascending=False, method='min')
    d['age_365_rank_improvement'] = d.new_rank-d.age_365_rank_other_stocks_fixed
    cols = ['isin','ticker','company','new_rank','winner_rank','activity_eligible','days_since_recorded_high','days_since_52w_closing_high','distance_from_recorded_high','history_months','has_true_5y','strict_cagr_1y','momentum_component','downside_confirmation','repair_score','new_score','explicit_age_points','explicit_proximity_points','explicit_rolling_points']
    cols += [c for c in d if c.startswith(('age_30_', 'age_365_', 'remove_explicit_', 'replace_age_'))]
    d[cols].sort_values('new_rank').to_csv(OUT/'age_sensitivity.csv',index=False)
    facts = pd.read_csv(FACTS,low_memory=False)
    wanted = ['NYKAA','PAYTM','LALPATHLAB','NAZARA','ONEPOINT','STEELCAS','PTCIL','LLOYDSME','RAMRAT','MWL','DIVISLAB','IPCALAB','APLAPOLLO','HINDUNILVR','ASIANPAINT','HDFCBANK']
    f = facts[facts.ticker.isin(wanted)].copy()
    fcols = ['ticker','yahoo_symbol','listing_date','history_start_date','yahoo_history_start_date','yahoo_history_end_date','yahoo_adjusted_ath','yahoo_adjusted_ath_date','yahoo_days_since_adjusted_ath','yahoo_latest_adjusted_close','yahoo_latest_raw_close','yahoo_raw_ath_high','yahoo_raw_ath_high_date','latest_price']
    f[fcols].to_csv(OUT/'age_history_definitions.csv',index=False)
    symbols = set(f.yahoo_symbol)
    frames = {}
    for path in sorted((FACTS.parent/'yahoo-full-recovery-v1/history-cache').glob('*.pkl')):
        for symbol, frame in pd.read_pickle(path).get('frames', {}).items():
            if symbol in symbols and frame is not None and len(frame) and (symbol not in frames or len(frame)>len(frames[symbol])):
                frames[symbol] = frame
    receipts = []
    for row in f.itertuples():
        if row.yahoo_symbol not in frames: continue
        frame = frames[row.yahoo_symbol].copy()
        frame.index = pd.to_datetime(frame.index).tz_localize(None)
        frame = frame.loc[frame.index.le(pd.Timestamp('2026-10-03'))] if hasattr(frame.index,'le') else frame.loc[frame.index <= pd.Timestamp('2026-10-03')]
        adj = frame['Adj Close'].dropna().sort_index()
        adj = adj[adj.gt(0)]
        high_date = adj.idxmax()
        receipts.append({'ticker':row.ticker,'first_date':str(adj.index[0].date()),'last_date':str(adj.index[-1].date()),'first_adjusted_close':float(adj.iloc[0]),'last_adjusted_close':float(adj.iloc[-1]),'adjusted_high_date':str(high_date.date()),'adjusted_high':float(adj.max()),'age_at_last_quote':(adj.index[-1]-high_date).days,'age_at_decision':(pd.Timestamp('2026-10-03')-high_date).days,'observations':len(adj)})
    pd.DataFrame(receipts).to_csv(OUT/'age_raw_history_receipts.csv',index=False)
    top = d[d.new_rank.le(100)].copy()
    top['has_true_5y'] = top.has_true_5y.eq(1)
    summary = {'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'scope':'base7500 frozen 2026-10-03; diagnostic only, all other components fixed', 'eligible':int(eligible.sum()),'top100_oldest_ath_days':float(top.days_since_recorded_high.max()),'top100_ath_over_365':int(top.days_since_recorded_high.ge(365).sum()),'top100_history_under_60_months':int(top.history_months.lt(60).sum()),'top100_history_under_36_months':int(top.history_months.lt(36).sum()),'top100_missing_true5y':int((~top.has_true_5y).sum()),'top100_history_median_months':float(top.history_months.median()),'top100_ath_median_days':float(top.days_since_recorded_high.median()),'scenarios':{}}
    for name in scenarios:
        changed=d[d[name+'_rank'].le(100)]
        summary['scenarios'][name]={'top100_overlap':int(len(set(top.isin if False else top['isin'])&set(changed['isin']))),'old_ath_ge730_top100':int(changed.days_since_recorded_high.ge(730).sum()),'entries':changed.loc[~changed['isin'].isin(top['isin']),['ticker','new_rank',name+'_rank']].to_dict('records')}
    (OUT/'age_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    print(d[d.ticker.isin(wanted)][cols].sort_values('new_rank').to_string(index=False))

if __name__ == '__main__':
    main()
