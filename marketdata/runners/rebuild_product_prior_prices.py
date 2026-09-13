"""Rebuild only current Product Baseline and dated quotes from local official evidence."""
from __future__ import annotations
import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
import pandas as pd
from stock_ranker.company_facts import load_company_fact_snapshot, _json_bytes, _sha256_bytes
from stock_ranker.data_state import atomic_write_json
from stock_ranker.product_price_reference import official_prior_references, REFERENCE_COLUMNS
from stock_ranker.product_classification import add_product_classification_and_baseline
from stock_ranker.ranking import rank_stocks_by_sector
from stock_ranker.config import BaselineConfig


def run(prior, output, history, evidence):
    accepted=load_company_fact_snapshot(prior)
    with (prior/'company_facts.csv').open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f); columns=list(reader.fieldnames); old=list(reader)
    if output.exists():
        raise FileExistsError('output must be fresh')
    frame, audit=official_prior_references(accepted.facts, evidence)
    mask=frame.latest_price.isna()
    repaired=add_product_classification_and_baseline(frame.loc[mask],history_root=history)
    fields=['product_baseline_yoy_growth','product_baseline_cagr_3y','product_baseline_cagr_5y','product_baseline_days_since_recorded_high']
    # Read accepted numeric strings without pandas' default float truncation.
    for col in fields:
        frame[col]=[float(r[col]) if r[col] else float('nan') for r in old]
    for col in fields+['product_baseline_eligible','product_baseline_reason_code','product_baseline_reason']:
        frame[col]=frame[col].astype(object)
        frame.loc[mask,col]=repaired[col]
    eligible=frame.loc[frame.product_baseline_eligible.eq(True)]
    changed_sectors=set(frame.loc[mask & frame.product_baseline_eligible.eq(True),'product_sector'])
    metrics=eligible[['ticker','company','product_sector',*fields]].rename(columns=dict(zip(
        ['product_sector',*fields],['sector','yoy_growth','cagr_3y','cagr_5y','days_since_recorded_high'])))
    for col in ('yoy_growth','cagr_3y','cagr_5y','days_since_recorded_high'):
        metrics[col]=pd.to_numeric(metrics[col])
    metrics['as_of_date']=pd.to_datetime(eligible.trade_date)
    metrics['ath_date']=metrics.as_of_date-pd.to_timedelta(metrics.days_since_recorded_high,unit='D')
    metrics['current_price']=eligible.latest_price.fillna(eligible.product_price_reference)
    for horizon,metric in [(1,'yoy_growth'),(3,'cagr_3y'),(5,'cagr_5y')]:
        metrics[f'close_{horizon}y_ago']=metrics.current_price/(1+metrics[metric])**horizon
    ranked=rank_stocks_by_sector(metrics,BaselineConfig()).set_index('ticker')
    for col,source in [('product_baseline_score','baseline_score'),('product_baseline_sector_rank','sector_rank')]:
        affected=frame.product_sector.isin(changed_sectors)
        frame.loc[affected,col]=frame.loc[affected,'ticker'].map(ranked[source])
    new_columns=[c for c in REFERENCE_COLUMNS if c not in columns]
    allowed=set(REFERENCE_COLUMNS)|{c for c in columns if c.startswith('product_baseline_')}
    by=frame.set_index('isin'); changed=[]; output_rows=[]
    for original in old:
        result=dict(original)
        for field in sorted(allowed):
            if original['latest_price'] and field.startswith('product_baseline_') and field not in {'product_baseline_score','product_baseline_sector_rank'}:
                continue
            value=by.at[original['isin'],field]
            value='' if pd.isna(value) else str(value) if isinstance(value,(str,bool)) else format(float(value),'.17g')
            previous=original.get(field,''); equal=previous==value
            if not equal and previous and value:
                try:
                    equal=float(previous)==float(value)
                except ValueError:
                    pass
            result[field]=previous if equal else value
            if not equal:
                changed.append(dict(isin=original['isin'],ticker=original['ticker'],field=field,before=previous,after=value))
        output_rows.append(result)
    output.mkdir(parents=True)
    with (output/'company_facts.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns+new_columns,lineterminator='\n');writer.writeheader();writer.writerows(output_rows)
    coverage=copy.deepcopy(accepted.coverage)
    coverage['metrics']['product_baseline_eligible']={'count':len(eligible),'percent':round(len(eligible)/len(frame)*100,4)}
    count=int(frame.latest_price.notna().sum()+frame.product_price_reference.notna().sum())
    coverage['metrics']['current_or_dated_official_reference_price']={'count':count,'percent':round(count/len(frame)*100,4)}
    atomic_write_json(output/'coverage_summary.json',coverage)
    loaded=pd.read_csv(output/'company_facts.csv',low_memory=False)
    manifest=dict(accepted.manifest)
    manifest['fingerprint']=_sha256_bytes(_json_bytes(dict(schema_version=manifest['schema_version'],market_fingerprint=manifest['market_fingerprint'],screener_bundle_fingerprint=manifest['screener_bundle_fingerprint'],facts=json.loads(loaded.to_json(orient='records',date_format='iso',double_precision=15)),coverage=coverage)))
    manifest['artifacts']={name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in ('company_facts.csv','coverage_summary.json')}
    atomic_write_json(output/'manifest.json',manifest)
    load_company_fact_snapshot(output)
    for name,data in [('price_evidence',audit),('changes',changed)]:
        keys=sorted({k for r in data for k in r})
        with (output/(name+'.csv')).open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');writer.writeheader();writer.writerows(data)
    assert all(a[k]==b[k] for a,b in zip(old,output_rows) for k in columns if k not in allowed)
    summary=dict(before=accepted.manifest['fingerprint'],after=manifest['fingerprint'],market_fingerprint=manifest['market_fingerprint'],unrelated_field_changes=0,waterfall=frame.product_baseline_reason_code.value_counts().to_dict(),price_references=audit)
    atomic_write_json(output/'recovery_report.json',summary)
    print(json.dumps(summary,sort_keys=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prior',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--history',type=Path,default=ROOT/'data/live_market/history_cache')
    p.add_argument('--evidence',type=Path,default=ROOT/'data/live_market/evidence/raw')
    args=p.parse_args();run(args.prior,args.output,args.history,args.evidence)
