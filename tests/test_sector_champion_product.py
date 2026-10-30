from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from stock_ranker.personalized_product import parse_profile,PersonalizationError
from stock_ranker.sector_champion_product import ChampionScorer

ROOT=Path(__file__).resolve().parents[1]
BASE=dict(amount=7500,lookback_months=36,interval_days=30,target_cagr_percent=20,horizon_months=12)

@pytest.fixture(scope='module')
def scorer():return ChampionScorer()

def test_approved_export_and_sector_ranks_reproduce(scorer):
    expected=pd.read_csv(ROOT/'experiments/champion-high-recency-20261017/current_all_4436_audit.csv').sort_values('isin').reset_index(drop=True)
    actual=scorer.score(parse_profile(BASE))
    np.testing.assert_allclose(actual.personalized_score,expected['dual_w0.01'],atol=1e-12,rtol=0)
    np.testing.assert_array_equal(actual.personalized_sector_rank,expected.patch_sector_rank)

@pytest.mark.parametrize('change',[{'amount':12345},{'lookback_months':12},{'lookback_months':60},{'interval_days':47},{'target_cagr_percent':23.5}])
def test_profile_fields_preserve_selected_models_actual_stock_order(scorer,change):
    base=scorer.score(parse_profile(BASE));other=scorer.score(parse_profile(BASE|change))
    assert len(other)==4436 and np.isfinite(other.personalized_score).all()
    # The frozen rankers learned zero splits on profile parameters. Preserve
    # their actual behavior; profile execution is verified separately.
    np.testing.assert_array_equal(base.personalized_score,other.personalized_score)
    np.testing.assert_array_equal(base.recency_adjustment,other.recency_adjustment)

def test_invalid_profile_is_not_silently_replaced(scorer):
    with pytest.raises(PersonalizationError):parse_profile(BASE|{'horizon_months':24})
    with pytest.raises(PersonalizationError):parse_profile(BASE|{'amount':float('nan')})

def test_package_tampering_fails_closed(tmp_path):
    manifest=json.loads((ROOT/'research/runtime/sector-champion-recency/manifest.json').read_text())
    manifest['files']={'price.txt':'incorrect'}
    (tmp_path/'manifest.json').write_text(json.dumps(manifest));(tmp_path/'price.txt').write_text('corrupted')
    with pytest.raises(PersonalizationError,match='integrity'):ChampionScorer(tmp_path)

def test_sip_activation_reproduces_selected_export(scorer):
    assert scorer.sip_enabled
    p=parse_profile(BASE)
    a=scorer.add_sip(scorer.score(p),p,scorer.sip_profiles[scorer.sip_profiles.profile_name.eq('base7500')]).set_index('isin').sort_index()
    b=pd.read_csv(ROOT/'experiments/champion-sip-profit-20261017/current_all_4436_audit.csv').set_index('isin').sort_index()
    np.testing.assert_allclose(a.personalized_score,b['sip_risk_confirmed_0.01'],atol=1e-12,rtol=0)
    np.testing.assert_array_equal(a.personalized_sector_rank,b.candidate_sector_rank)
    assert len(a)==4436 and a.personalized_score.notna().all()

def test_sip_profile_changes_only_new_adjustment(scorer):
    results=[]
    for name,change in [('base7500',{}),('amount1000',{'amount':1000})]:
        p=parse_profile(BASE|change)
        results.append(scorer.add_sip(scorer.score(p),p,scorer.sip_profiles[scorer.sip_profiles.profile_name.eq(name)]))
    a,b=results
    np.testing.assert_array_equal(a.recency_champion_score,b.recency_champion_score)
    assert (a.personalized_score-b.personalized_score).abs().max()>1e-10
