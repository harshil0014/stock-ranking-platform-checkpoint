"""Import browser-downloaded Screener observations and fill existing current-data gaps.

No provider value checks, historical backfill, model fitting, or runtime promotion.
Only schema, exact identity, source timestamps and import completeness are checked.
"""
from pathlib import Path
from datetime import datetime, timezone
import ast, csv, gzip, hashlib, json, os, re, shutil
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key]='1'
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'work/screener-refresh-20261106'
RAW=WORK/'raw'
OUT=ROOT/'experiments/screener-refresh-20261106'
DELIVERY=Path(r'C:\Users\Harshil\Documents\Codex\2026-10-31\you\outputs\screener-refresh-20261106')
DOWNLOADS=Path(r'C:\Users\Harshil\Downloads')
BASE=ROOT/'experiments/current-data-recovery-20261003/current_company_facts_recovered_v8_yahoo_rescued.csv.gz'
IDENTITY=['Name','BSE Code','NSE Code','ISIN Code','Industry Group','Industry']

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def blank(series):
    return series.fillna('').astype(str).str.strip().isin(['','nan','None','<NA>'])

def key(value):
    return re.sub('[^a-z0-9]','',str(value).lower())

def source_mapping():
    tree=ast.parse((ROOT/'src/stock_ranker/company_facts.py').read_text(encoding='utf-8-sig'))
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='screener_fields' for t in node.targets) and isinstance(node.value,ast.Dict):
            return {k.value:list(dict.fromkeys(a.value.split('__',1)[-1] for a in v.args if isinstance(a,ast.Constant) and isinstance(a.value,str))) for k,v in zip(node.value.keys,node.value.values) if isinstance(k,ast.Constant) and isinstance(v,ast.Call)}
    raise RuntimeError('Canonical Screener field map not found')

def main():
    RAW.mkdir(parents=True,exist_ok=True); OUT.mkdir(parents=True,exist_ok=True); DELIVERY.mkdir(parents=True,exist_ok=True)
    runtime_paths=[ROOT/'research/runtime/sector-champion-recency/manifest.json',ROOT/'research/runtime/global-rank-correction-20261106/manifest.json']
    runtime_before={str(p.relative_to(ROOT)):digest(p) for p in runtime_paths}
    # Exact file set from observed browser downloads; no glob over unrelated private files.
    names=['query-results.csv']+[f'query-results ({i}).csv' for i in range(1,12)]
    candidates=[DOWNLOADS/n for n in names if (DOWNLOADS/n).is_file()]
    candidates=[p for p in candidates if datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).date().isoformat()=='2026-11-06']
    candidates.sort(key=lambda p:p.stat().st_mtime)
    if len(candidates)<10:raise RuntimeError(f'Incomplete browser export set: {len(candidates)} files')
    master=None; provenance=None; receipts=[]; rejected=[]; offered=set()
    for n,source in enumerate(candidates):
        destination=RAW/f'{n:02d}_{source.name}'
        shutil.copy2(source,destination)
        frame=pd.read_csv(destination,dtype=str,keep_default_na=False)
        missing=set(IDENTITY)-set(frame.columns)
        if missing:raise RuntimeError(f'{source.name} missing identity columns: {sorted(missing)}')
        frame['ISIN Code']=frame['ISIN Code'].str.strip().str.upper()
        invalid=~frame['ISIN Code'].str.fullmatch(r'IN[A-Z0-9]{9}[0-9]')
        duplicates=frame['ISIN Code'].duplicated(keep=False)&~invalid
        bad=frame.loc[invalid|duplicates].copy()
        if len(bad):
            bad['source_file']=destination.name
            bad['reason']=['INVALID_ISIN' if x else 'DUPLICATE_ISIN' for x in invalid[invalid|duplicates]]
            rejected.append(bad)
        frame=frame.loc[~(invalid|duplicates)].set_index('ISIN Code')
        metrics=[c for c in frame.columns if c not in IDENTITY]
        offered.update(key(c) for c in metrics)
        observed=datetime.fromtimestamp(source.stat().st_mtime,timezone.utc).isoformat()
        receipts.append(dict(source_filename=source.name,cached_filename=destination.name,sha256=digest(destination),bytes=destination.stat().st_size,download_observed_at=observed,rows_exported=len(frame)+len(bad),accepted_unique_isins=len(frame),rejected_rows=len(bad),columns=list(frame.columns),source_kind='SCREENER_PREMIUM_BROWSER_CSV',historical_pit_eligible=False))
        union=frame.index if master is None else master.index.union(frame.index)
        master=pd.DataFrame(index=union) if master is None else master.reindex(union)
        provenance=pd.DataFrame(index=union) if provenance is None else provenance.reindex(union)
        for col in frame.columns:
            if col not in master:
                master[col]='';provenance[col]=''
            values=frame[col].reindex(union).fillna('')
            present=~blank(values)
            master.loc[present,col]=values[present]
            provenance.loc[present,col]=destination.name
        print('IMPORTED',destination.name,len(frame),len(frame.columns),flush=True)
    if len(offered)!=378:raise RuntimeError(f'Expected all 378 observed export metrics, received {len(offered)}')
    master=master.fillna('').sort_index();master.index.name='ISIN Code'
    provenance=provenance.fillna('').reindex(master.index);provenance.index.name='ISIN Code'
    master.to_csv(WORK/'screener_current_master.csv.gz',compression='gzip')
    provenance.to_csv(WORK/'screener_current_master_sources.csv.gz',compression='gzip')
    if rejected:pd.concat(rejected,ignore_index=True).to_csv(WORK/'rejected_source_identities.csv',index=False)
    base=pd.read_csv(BASE,dtype=str,keep_default_na=False)
    assert len(base)==4436 and not base['isin'].duplicated().any()
    enriched=base.copy(deep=True)
    exact=base['isin'].isin(master.index)
    source_ids=base['isin'].where(exact,'').copy()
    methods=pd.Series('UNMATCHED',index=base.index)
    methods.loc[exact]='EXACT_ISIN'
    code_index={}
    for source_isin,row in master.iterrows():
        for exchange,col in [('NSE','NSE Code'),('BSE','BSE Code')]:
            code=str(row[col]).strip().removesuffix('.0')
            if code:code_index.setdefault((exchange,code),[]).append(source_isin)
    already=set(source_ids[exact])
    for ix,row in base.loc[~exact].iterrows():
        candidates=code_index.get((row['primary_exchange'],str(row['exchange_security_id']).strip().removesuffix('.0')),[])
        if len(candidates)==1 and candidates[0] not in already:
            source_ids.at[ix]=candidates[0];methods.at[ix]='UNIQUE_PRIMARY_EXCHANGE_SECURITY_ID'
            already.add(candidates[0])
    matched=source_ids.ne('')
    assert not source_ids[matched].duplicated().any()
    identity=base[['isin','ticker','company','primary_exchange','exchange_security_id']].copy()
    identity['screener_source_isin']=source_ids
    identity['match_method']=methods
    identity['different_isin']=matched&source_ids.ne(base['isin'])
    identity['historical_price_bridge_verified']=False
    identity.to_csv(OUT/'identity_matches.csv',index=False)
    mapping=source_mapping()
    # Existing data can contain additional matching fields created by earlier export batches.
    previous=ROOT/'experiments/current-data-recovery-20261003'
    for audit in sorted(previous.glob('screener*_filled_cells.csv')):
        for row in pd.read_csv(audit,dtype=str,keep_default_na=False).to_dict('records'):
            field=row.get('field','');col=row.get('source_column','')
            if field.startswith('screener_') and col:mapping.setdefault(field,[]).append(col)
    aliases={key(c):c for c in master.columns}
    before={};after={};fills=[];date_by_file={r['cached_filename']:r['download_observed_at'] for r in receipts}
    for field,possible in mapping.items():
        if field not in base.columns:continue
        column=next((aliases[key(c)] for c in possible if key(c) in aliases),None)
        if column is None:continue
        missing=blank(base[field]);before[field]=int(missing.sum())
        values=source_ids.map(master[column]).fillna('')
        selected=missing&~blank(values)
        enriched.loc[selected,field]=values[selected]
        after[field]=int(blank(enriched[field]).sum())
        for ix in base.index[selected]:
            isin=base.at[ix,'isin'];source_isin=source_ids.at[ix];source=provenance.at[source_isin,column]
            fills.append(dict(isin=isin,ticker=base.at[ix,'ticker'],source_isin=source_isin,match_method=methods.at[ix],field=field,value=values.at[ix],source_column=column,source_file=source,source_observed_at=date_by_file[source],historical_pit_eligible=False))
        assert enriched.loc[~missing,field].equals(base.loc[~missing,field])
    enriched_path=WORK/'current_company_facts_recovered_v9_screener_20261106.csv.gz'
    enriched.to_csv(enriched_path,index=False,compression='gzip')
    pd.DataFrame(fills,columns=['isin','ticker','source_isin','match_method','field','value','source_column','source_file','source_observed_at','historical_pit_eligible']).to_csv(WORK/'filled_cells.csv',index=False)
    base.loc[~matched,['isin','ticker','company']].to_csv(OUT/'unmatched_current_identities.csv',index=False)
    field_coverage=[]
    for col in master.columns:
        metric_kind='FORECAST_OR_EXPECTATION' if 'expected' in col.lower() else 'CURRENT_VENDOR_VINTAGE'
        field_coverage.append(dict(field=col,reported=int((~blank(master[col])).sum()),missing=int(blank(master[col]).sum()),metric_kind=metric_kind,historical_pit_eligible=False))
    pd.DataFrame(field_coverage).to_csv(OUT/'field_coverage.csv',index=False)
    pd.DataFrame([dict(field=c,missing_before=before[c],missing_after=after[c],filled=before[c]-after[c]) for c in before]).to_csv(OUT/'canonical_gap_coverage.csv',index=False)
    summary=dict(date='2026-11-06',provider='Screener Premium',acquisition='Browser UI exports requested by user; no scraping or private API calls',exports=len(receipts),raw_export_rows=sorted(set(r['rows_exported'] for r in receipts)),master_unique_isins=len(master),distinct_export_metric_names=len(offered),current_platform_identities=len(base),exact_isin_matches=int(matched.sum()),unmatched_current=int((~matched).sum()),canonical_fields_with_source=len(before),canonical_missing_cells_filled=len(fills),stocks_with_gaps_filled=len(set(r['isin'] for r in fills)),existing_nonblank_overwritten=0,source_values_cross_checked_against_other_providers=False,fresh_observation_range=[min(r['download_observed_at'] for r in receipts),max(r['download_observed_at'] for r in receipts)],base_path=str(BASE.relative_to(ROOT)),base_sha256=digest(BASE),fresh_master_path=str((WORK/'screener_current_master.csv.gz').relative_to(ROOT)),gap_filled_company_facts_path=str(enriched_path.relative_to(ROOT)),historical_training_modified=False,champion_runtime_modified=False,prospective_ledger_modified=False,notes=['All offered source columns retained, including custom ratios and expectations. No model features automatically added.','Current exports are current vendor vintages; earlier financial periods are not proof of historical availability.','Screener blanks remain blanks in the fresh master. Previous nonblank values are preserved only in the separately labelled gap-filled legacy facts file.','Daily OHLCV histories, ATH dates, SIP paths and delisted coverage were not manufactured from ratio exports.'])
    summary.update(exact_isin_matches=int(exact.sum()),unique_primary_exchange_code_matches=int((matched&~exact).sum()),total_current_identity_matches=int(matched.sum()),different_isin_current_only_matches=int(identity['different_isin'].sum()))
    summary['notes'].append('Unique primary exchange-code matches preserve both platform and current Screener ISINs in identity_matches.csv. No historical price/ISIN continuity is inferred from that current-only match.')
    for p in runtime_paths:assert digest(p)==runtime_before[str(p.relative_to(ROOT))]
    summary['runtime_hashes_unchanged']=runtime_before
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (OUT/'source_receipts.json').write_text(json.dumps(receipts,indent=2),encoding='utf-8')
    artefacts=[WORK/'screener_current_master.csv.gz',WORK/'screener_current_master_sources.csv.gz',WORK/'filled_cells.csv',enriched_path,*OUT.glob('*.csv'),OUT/'summary.json',OUT/'source_receipts.json',Path(__file__)]
    (OUT/'manifest.json').write_text(json.dumps([dict(path=str(p.relative_to(ROOT)),sha256=digest(p),bytes=p.stat().st_size) for p in artefacts],indent=2),encoding='utf-8')
    for p in [WORK/'screener_current_master.csv.gz',enriched_path,OUT/'summary.json',OUT/'canonical_gap_coverage.csv',OUT/'field_coverage.csv',OUT/'unmatched_current_identities.csv',OUT/'identity_matches.csv']:
        shutil.copy2(p,DELIVERY/p.name)
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
