import gzip
import hashlib
import json

import pytest

from stock_ranker.champion_coverage import ChampionCoverage, DEFAULT_PACKAGE
from stock_ranker.personalized_product import PersonalizationError


def package(tmp_path):
    rows=[]
    for identity,legacy,score in [('OLD',True,.7),('NEW',False,.9),('EMPTY',False,None)]:
        rows.append(dict(isin=identity,legacy=legacy,source_isin=identity+'CURRENT',ticker=identity,
            company=identity+' company',sector='Sector',aliases=[identity,identity+'CURRENT'],
            current_fundamentals={'current_price':'123','company_name':identity+' current name'},match_method='EXACT_ISIN',different_isin=False,
            observed_at='2026-11-06T04:53:32+00:00',fallback_score=score,fallback_factor_coverage=.8))
    with gzip.open(tmp_path/'universe.json.gz','wt',encoding='utf-8') as f:json.dump(rows,f)
    manifest=dict(policy_id='champion_coverage_20261106',total_stocks=3,legacy_stocks=1,
        additional_stocks=2,fresh_source_matches=3,source_as_of_date='2026-11-06',
        source_observed_range=['2026-11-06T04:37:00+00:00','2026-11-06T04:53:32+00:00'],
        different_isin_current_only_matches=0,excluded_without_exchange_code=0,
        files={'universe.json.gz':hashlib.sha256((tmp_path/'universe.json.gz').read_bytes()).hexdigest()})
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    return ChampionCoverage(tmp_path)


def frozen():
    return dict(as_of_date='2026-10-03',rows=[dict(isin='OLD',ticker='OLD',company='Old company',
        sector='Sector',search_aliases='OLD',personalized_score=.2,personalized_sector_rank=1,
        personalized_available=True,execution_available=True,review_flags=[])])


def test_proxy_never_displaces_trained_order_and_missing_evidence_is_unscored(tmp_path):
    coverage=package(tmp_path)
    result=coverage.apply(frozen(),[dict(isin='OLD',global_champion_rank=1,global_champion_score=.1)])
    rows={r['isin']:r for r in result['rows']}
    assert rows['OLD']['coverage_global_position']==1
    assert rows['NEW']['coverage_global_position']==2
    assert rows['NEW']['personalized_sector_rank']==2
    assert rows['NEW']['xirr'] is None and rows['NEW']['days_since_recorded_high'] is None
    assert not rows['NEW']['execution_available']
    assert rows['EMPTY']['coverage_global_position']==3
    assert rows['EMPTY']['personalized_sector_rank']==3
    assert rows['EMPTY']['sector_rank_basis']=='PROVISIONAL_DISPLAY_ORDER'
    assert rows['EMPTY']['personalized_score'] is None
    assert not rows['EMPTY']['personalized_available']
    assert result['sector_unranked_count']==0 and result['sector_ranked_count']==3
    assert rows['OLD']['ranking_as_of_date']=='2026-10-03'
    assert rows['NEW']['ranking_as_of_date']=='2026-11-06'
    assert result['coverage']['fresh_daily_inputs'] is False
    json.dumps(result,allow_nan=False)


def test_current_alias_resolution_and_invalid_identity(tmp_path):
    coverage=package(tmp_path)
    result=coverage.apply(frozen(),[],securities=['NEWCURRENT'])
    assert next(r for r in result['rows'] if r['isin']=='NEW')['requested_code']=='NEWCURRENT'
    result=coverage.apply(frozen(),[],securities=['NEW current name'])
    assert next(r for r in result['rows'] if r['isin']=='NEW')['requested_code']=='NEW current name'
    with pytest.raises(PersonalizationError,match='Unknown or ambiguous'):
        coverage.apply(frozen(),[],securities=['UNKNOWN'])


def test_changed_isin_never_implies_execution_continuity(tmp_path):
    coverage=package(tmp_path)
    coverage.by_isin['OLD']['different_isin']=True
    result=coverage.apply(frozen(),[])
    row=next(r for r in result['rows'] if r['isin']=='OLD')
    assert not row['execution_available'] and not row['identity_history_bridge_verified']
    assert 'Changed ISIN' in row['execution_blocker']


def test_tampered_coverage_fails_closed(tmp_path):
    package(tmp_path)
    with (tmp_path/'universe.json.gz').open('ab') as f:f.write(b'tampered')
    with pytest.raises(PersonalizationError,match='integrity'):
        ChampionCoverage(tmp_path)


def test_new_stock_follows_every_occupant_of_a_frozen_bottom_tie(tmp_path):
    coverage=package(tmp_path)
    second=dict(coverage.by_isin['OLD'],isin='OLD2')
    coverage.records.append(second);coverage.by_isin['OLD2']=second
    result=frozen()
    result['rows'].append(dict(result['rows'][0],isin='OLD2'))
    coverage.apply(result,[])
    assert next(r for r in result['rows'] if r['isin']=='NEW')['personalized_sector_rank']==3


def test_quality_only_proxy_is_ranked_after_momentum_without_invented_history(tmp_path):
    coverage=package(tmp_path)
    quality=coverage.by_isin['EMPTY']
    quality.update(fallback_basis='FUNDAMENTALS_ONLY',fallback_score=.99)
    result=coverage.apply(frozen(),[])
    rows={r['isin']:r for r in result['rows']}
    assert rows['EMPTY']['coverage_tier']=='FUNDAMENTALS_FALLBACK'
    assert rows['EMPTY']['personalized_available']
    assert rows['EMPTY']['personalized_sector_rank']==3
    assert rows['EMPTY']['days_since_recorded_high'] is None
    assert rows['EMPTY']['xirr'] is None
    assert rows['EMPTY']['coverage_score_kind']=='UNVALIDATED_FUNDAMENTALS_ONLY_PROXY'
    assert result['fallback_count']==2


@pytest.mark.skipif(not (DEFAULT_PACKAGE/'manifest.json').exists(),reason='Private Screener package is local')
def test_real_union_and_fresh_data_matches_source_without_fake_histories():
    from stock_ranker.sector_champion_product import SectorChampionService
    from stock_ranker.global_champion_product import GlobalChampionSelection
    from stock_ranker.personalized_product import parse_profile
    base=dict(amount=7500,lookback_months=36,interval_days=30,target_cagr_percent=20,horizon_months=12)
    service=SectorChampionService()
    result=service.rank(base)
    assert len(result['rows'])==5547
    assert result['row_count']==5547
    rows={r['isin']:r for r in result['rows']}
    assert len(rows)==5547 and result['coverage']['additional_stocks']==1111
    assert result['coverage']['fresh_source_matches']==5544
    assert sum(r['current_data_available'] for r in rows.values())==5544
    assert sorted(r['coverage_global_position'] for r in rows.values())==list(range(1,5548))
    original=GlobalChampionSelection().rows
    assert [rows[r['isin']]['coverage_global_position'] for r in original]==list(range(1,len(original)+1))
    assert result['global_champion']['rows']==original[:20]
    p=parse_profile(base)
    expected=service.scorer.add_sip(service.scorer.score(p),p,service.scorer.sip_profiles.query("profile_name == 'base7500'"))
    for r in expected.itertuples():
        assert rows[r.isin]['personalized_score']==pytest.approx(r.personalized_score,abs=1e-12)
        assert rows[r.isin]['personalized_sector_rank']==r.personalized_sector_rank
    additions=[r for r in rows.values() if r['coverage_tier'] in ('SCREENER_FALLBACK','FUNDAMENTALS_FALLBACK','COVERAGE_ONLY')]
    assert len(additions)==1111
    assert all(r['personalized_sector_rank'] is not None and r['personalized_available'] for r in rows.values())
    assert sum(r['coverage_tier']=='FUNDAMENTALS_FALLBACK' for r in rows.values())==3
    assert result['sector_unranked_count']==0 and result['sector_ranked_count']==5547
    assert all(r['xirr'] is None and r['days_since_recorded_high'] is None and not r['execution_available'] for r in additions)
    assert sum(r['screener_source_isin'] is not None and r['screener_source_isin']!=r['isin'] for r in rows.values())==17
    added=additions[0]
    second=service.rank(base,securities=[added['screener_source_isin']])
    assert len(second['rows'])==5547  # Repeat requests never accumulate extra rows.
    assert next(r for r in second['rows'] if r['isin']==added['isin'])['requested_code']==added['screener_source_isin']
    json.dumps(second,allow_nan=False)
