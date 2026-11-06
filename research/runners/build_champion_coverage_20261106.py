"""Build private current-data coverage, without retraining or altering frozen inputs."""
from pathlib import Path
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[name]='1'
import numpy as np
import pandas as pd

from import_screener_refresh_20261106 import source_mapping

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'work/screener-refresh-20261106'
OUT=ROOT/'work/champion-coverage-20261106/runtime'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    master_path=WORK/'screener_current_master.csv.gz'
    match_path=ROOT/'experiments/screener-refresh-20261106/identity_matches.csv'
    master=pd.read_csv(master_path,dtype=str,keep_default_na=False).set_index('ISIN Code')
    matches=pd.read_csv(match_path,dtype=str,keep_default_na=False).set_index('isin')
    facts_path=ROOT/'research/runtime/personalized-v17/facts.csv.gz'
    facts=pd.read_csv(facts_path,dtype=str,keep_default_na=False).set_index('isin')
    assert len(matches)==len(facts)==4436 and not master.index.has_duplicates
    eligible=master['NSE Code'].str.strip().ne('')|master['BSE Code'].str.strip().ne('')
    excluded=master.loc[~eligible]
    current=master.loc[eligible]
    used=set(matches.screener_source_isin)-{''}
    extra=current.loc[~current.index.isin(used)]
    summary=json.loads((ROOT/'experiments/screener-refresh-20261106/summary.json').read_text())
    observed=summary['fresh_observation_range'][1]
    # Scores rank vendor metrics as reported, never inferred daily histories.
    signals=pd.DataFrame(index=current.index)
    for label,column in [('return_3y','Return over 3years'),('return_5y','Return over 5years'),
                         ('roce','Return on capital employed'),('debt','Debt to equity')]:
        signals[label]=pd.to_numeric(current[column],errors='coerce').replace([np.inf,-np.inf],np.nan)
    price=pd.to_numeric(current['Current Price'],errors='coerce')
    high=pd.to_numeric(current['High price all time'],errors='coerce')
    signals['proximity']=(price/high).where(price.gt(0)&high.gt(0)&price.le(high*1.01))
    weights={'return_3y':.3,'return_5y':.3,'proximity':.2,'roce':.1,'debt':.1}
    score=pd.Series(0.,index=current.index)
    for label,weight in weights.items():
        # Missing evidence contributes a midpoint only to this disclosed proxy;
        # it is not filled into the financial data or trained model inputs.
        score+=weight*signals[label].rank(pct=True,ascending=label!='debt').fillna(.5)
    coverage=signals.notna().mean(axis=1)
    # Require at least one actual price-performance signal to offer a proxy.
    score=score.where(signals[['return_3y','return_5y','proximity']].notna().any(axis=1))
    mapping=source_mapping()
    def record(identity,source_id,legacy):
        source=master.loc[source_id] if source_id else None
        base=facts.loc[identity] if legacy else None
        nse=str(source['NSE Code']).strip() if source is not None else ''
        bse=str(source['BSE Code']).strip() if source is not None else ''
        aliases={identity}
        if nse:aliases.update([nse,'NSE:'+nse])
        if bse:aliases.update([bse,'BSE:'+bse,'BOM:'+bse,'BSE-'+bse])
        if source_id:aliases.add(source_id)
        ticker=base['ticker'] if legacy else nse or 'BSE-'+bse
        aliases.add(ticker)
        data={}
        if source is not None:
            for canonical,options in mapping.items():
                value=next((str(source[c]).strip() for c in options if c in source and str(source[c]).strip()),None)
                data[canonical.removeprefix('screener_')]=value
        different=bool(source_id and source_id!=identity)
        value=score.get(source_id,np.nan)
        return dict(isin=identity,source_isin=source_id or None,legacy=legacy,
            ticker=ticker,company=base['company'] if legacy else source['Name'],
            sector=(base['product_sector'] or 'Unclassified') if legacy else source['Industry Group'] or 'Unclassified',
            aliases=sorted(aliases),match_method=matches.loc[identity,'match_method'] if legacy else 'NEW_SOURCE_ISIN',
            different_isin=different,observed_at=observed if source_id else None,
            current_fundamentals=data,fallback_score=float(value) if pd.notna(value) else None,
            fallback_factor_coverage=float(coverage.get(source_id,0)))
    rows=[record(i,matches.loc[i,'screener_source_isin'],True) for i in facts.index]
    rows += [record(i,i,False) for i in extra.index]
    assert len({r['isin'] for r in rows})==len(rows)
    with gzip.open(OUT/'universe.json.gz','wt',encoding='utf-8') as stream:
        json.dump(rows,stream,allow_nan=False,separators=(',',':'))
    manifest=dict(policy_id='champion_coverage_20261106',created_at_utc=datetime.now(timezone.utc).isoformat(),
        total_stocks=len(rows),legacy_stocks=len(facts),additional_stocks=len(extra),
        fresh_source_matches=sum(bool(r['source_isin']) for r in rows),
        source_as_of_date='2026-11-06',source_observed_range=summary['fresh_observation_range'],
        different_isin_current_only_matches=sum(r['different_isin'] for r in rows),
        excluded_without_exchange_code=len(excluded),excluded_names=list(excluded['Name']),
        fallback_weights=weights,missing_proxy_factor_policy='Midpoint percentile; require at least one observed price-performance signal; report factor coverage.',
        fallback_validation='Unvalidated current-data coverage proxy, not a trained champion prediction.',
        historical_training_modified=False,fresh_daily_inputs=False,
        source_hashes={str(p.relative_to(ROOT)):digest(p) for p in [master_path,match_path,facts_path]},
        files={'universe.json.gz':digest(OUT/'universe.json.gz')})
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({k:manifest[k] for k in ['total_stocks','additional_stocks','fresh_source_matches','excluded_without_exchange_code']},indent=2),flush=True)


if __name__=='__main__':build()
