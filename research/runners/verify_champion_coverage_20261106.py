"""Produce local coverage evidence and a private portable runtime bundle."""
from pathlib import Path
from collections import Counter
import argparse
import csv
import hashlib
import json
import shutil
import zipfile
from urllib.request import Request, urlopen

from stock_ranker.sector_champion_product import SectorChampionService
from stock_ranker.global_champion_product import GlobalChampionSelection
from stock_ranker.champion_coverage import DEFAULT_PACKAGE

ROOT=Path(__file__).resolve().parents[2]
DELIVERY=Path(r'C:\Users\Harshil\Documents\Codex\2026-10-31\you\outputs\champion-coverage-20261106')
BASE=dict(amount=7500,lookback_months=36,interval_days=30,target_cagr_percent=20,horizon_months=12)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--api-url',help='Reuse the running local champion API instead of loading a second service')
    args=parser.parse_args()
    DELIVERY.mkdir(parents=True,exist_ok=True)
    if args.api_url:
        request=Request(args.api_url,data=json.dumps({'profile':BASE}).encode(),headers={'Content-Type':'application/json'})
        with urlopen(request,timeout=180) as response:result=json.load(response)
    else:
        service=SectorChampionService()
        result=service.rank(BASE)
    original=GlobalChampionSelection()
    rows=result['rows'];by_isin={r['isin']:r for r in rows}
    assert result['row_count']==len(rows)==5547==len(by_isin)
    assert sum(r['current_data_available'] for r in rows)==5544
    assert [by_isin[r['isin']]['coverage_global_position'] for r in original.rows]==list(range(1,2387))
    assert result['global_champion']['rows']==original.rows[:20]
    assert len({r['isin'] for r in rows if r['identity_match_method']=='NEW_SOURCE_ISIN'})==1111
    assert sorted(r['coverage_global_position'] for r in rows)==list(range(1,5548))
    changed=[r for r in rows if r['screener_source_isin'] and r['screener_source_isin']!=r['isin']]
    assert len(changed)==17 and all(not r['execution_available'] for r in changed)
    added=[r for r in rows if r['identity_match_method']=='NEW_SOURCE_ISIN']
    assert all(r['xirr'] is None and r['days_since_recorded_high'] is None for r in added)
    legacy_sizes=Counter(r['sector'] for r in rows if r['identity_match_method']!='NEW_SOURCE_ISIN')
    for row in added:
        if row['personalized_sector_rank'] is not None:
            assert row['personalized_sector_rank']>legacy_sizes[row['sector']]
    columns=['coverage_global_position','global_model_rank','isin','screener_source_isin','ticker','company',
        'sector','coverage_tier','personalized_score','global_model_score','personalized_sector_rank',
        'fallback_factor_coverage','ranking_as_of_date','current_data_as_of_date','execution_available']
    with (DELIVERY/'all_stocks_coverage.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns,extrasaction='ignore');writer.writeheader()
        writer.writerows(sorted(rows,key=lambda r:r['coverage_global_position']))
    receipt=dict(passed=True,total_stocks=len(rows),tiers=dict(Counter(r['coverage_tier'] for r in rows)),
        fresh_source_matches=sum(r['current_data_available'] for r in rows),
        different_isin_execution_blocked=len(changed),original_global_order_preserved=True,
        champion_training_changed=False,prospective_ledger_changed=False,fresh_daily_inputs=False,
        source_as_of_date=result['coverage']['source_as_of_date'],model_as_of_date=result['as_of_date'],
        governor='12.5% Windows job cap; one compute thread; 4 seconds active / 2 seconds rest',
        result_sha256=hashlib.sha256(json.dumps(result,allow_nan=False,sort_keys=True).encode()).hexdigest())
    (DELIVERY/'verification.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    for name in ['manifest.json','universe.json.gz']:
        target=DELIVERY/'private-runtime'/name;target.parent.mkdir(exist_ok=True)
        shutil.copy2(DEFAULT_PACKAGE/name,target)
    shutil.copy2(ROOT/'work/champion-coverage-20261106/low-load-tests.log',DELIVERY/'test_log.txt')
    text=f'''# Champion coverage integration — 6 November 2026

The local champion page and API now cover {len(rows):,} accepted NSE/BSE identities, including 1,111 additions. Current Screener evidence is attached to 5,544 identities; three old identities have no current match. Three source companies without either exchange code were excluded. The identical total of 5,547 source rows and combined identities is coincidental.

## Ranking coverage

{json.dumps(receipt['tiers'],indent=2)}

The 2,386 frozen global-model stocks retain their exact global order and Top-20. Existing 4,436 sector scores/order are preserved. New stocks follow the frozen stocks within each sector, using an explicitly unvalidated current-data proxy: 30% vendor three-year return percentile, 30% five-year, 20% price/all-time-high proximity, 10% ROCE, and 10% lower debt/equity. Percentiles use all exchange-coded source stocks. Missing proxy factors contribute a midpoint; coverage is displayed. A proxy requires at least one observed return/proximity signal. Missing-evidence rows have a display position, no predictive score.

Coverage positions order evidence tiers; they are not comparable model scores or a new accuracy claim. New financial data appears in each stock's Inspect view. This integrates data into the champion product, without pretending the trained model accepts new financial columns. All 378 original vendor metrics remain in the preserved source master; 101 canonical financial fields are attached to the runtime.

Current financial observations are from 6 November; trained price/SIP evidence remains 3 October. Current prices are separate from historical execution prices. High proximity is not days since the high. New rows have no fabricated SIP XIRR, high dates, daily price paths or execution eligibility. Seventeen changed-ISIN matches retain both identifiers and block current execution continuity. Listing identifiers establish coverage, not active trading status, liquidity, lot size or a survivorship-free historical universe.

No retraining, historical tuning, model promotion or prospective-ledger modification occurred. All work used the existing low-load governor. This is full coverage of the accepted combined dataset, not a certification of every NSE/BSE listing.

## Files and rollback

`all_stocks_coverage.csv` contains every display position, model rank where available, sector rank, score type and dates. `verification.json` and `test_log.txt` preserve checks. `private-runtime/` contains subscription-derived observations and stays local; it is excluded from the public GitHub repository.

To install the private runtime in another authorized checkout, copy its two files to `work/champion-coverage-20261106/runtime/` or set `STOCK_RANKER_CHAMPION_COVERAGE` to that directory. To disable only this coverage overlay, set that variable to a nonexistent local path and restart the website. Frozen model packages are unchanged.
'''
    (DELIVERY/'README.md').write_text(text,encoding='utf-8')
    archive=DELIVERY.parent/'Champion_Coverage_20261106.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for path in DELIVERY.rglob('*'):
            if path.is_file():bundle.write(path,path.relative_to(DELIVERY))
    print(json.dumps(receipt,indent=2),flush=True)
    print('PRIVATE_BUNDLE',archive,flush=True)


if __name__=='__main__':main()
