from stock_ranker.personalized_peak_product import PeakRankingService


def test_review_excludes_unsupported_sector_and_preserves_search_and_cache():
    service=PeakRankingService()
    profile={'amount':7500,'lookback_months':36,'interval_days':30,'target_cagr_percent':20,'horizon_months':12}
    result=service.rank(profile)
    row=next(r for r in result['rows'] if r['ticker']=='BSE-531676')
    assert row['sector']=='Unclassified'
    assert not row['personalized_available']
    assert row['personalized_sector_rank'] is None
    assert row['personalized_score'] is None
    assert row['sector_review_source'].endswith('32nd-Annual-Report.pdf')
    assert result['personalized_count']==1746
    food=[r for r in result['rows'] if r['sector']=='Food Products' and r['personalized_available']]
    assert sorted(r['personalized_sector_rank'] for r in food)==list(range(1,len(food)+1))
    cached=service.rank(profile)
    again=next(r for r in cached['rows'] if r['ticker']=='BSE-531676')
    assert again['review_flags']==row['review_flags']
    assert cached['cache_hit']
