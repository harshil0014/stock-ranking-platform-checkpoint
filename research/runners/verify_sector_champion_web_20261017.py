"""HTTP integration check against the locally running website."""
import json,urllib.request,urllib.error
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
URL='http://127.0.0.1:8765'
def post(profile):
    req=urllib.request.Request(URL+'/api/sector-champion/rank',data=json.dumps({'profile':profile}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=1200) as r:return json.load(r)
def main():
    with urllib.request.urlopen(URL+'/sector-champion') as r:html=r.read().decode()
    for field in ['personalizedAmount','personalizedLookback','personalizedInterval','personalizedTarget','personalizedHorizon']:assert field in html
    assert 'Sector Champion' in html
    profile=dict(amount=7500,lookback_months=36,interval_days=30,target_cagr_percent=20,horizon_months=12)
    try:post(profile|{'amount':-1})
    except urllib.error.HTTPError as e:assert e.code==400
    else:raise AssertionError('Invalid input accepted')
    base=post(profile);print('BASE',base['row_count'],flush=True)
    rows=pd.DataFrame(base['rows']).set_index('isin').sort_index()
    expected=pd.read_csv(ROOT/'experiments/champion-high-recency-20261017/current_all_4436_audit.csv').set_index('isin').sort_index()
    np.testing.assert_allclose(rows.personalized_score,expected['dual_w0.01'],atol=1e-12,rtol=0)
    np.testing.assert_array_equal(rows.personalized_sector_rank,expected.patch_sector_rank)
    other=post(profile|{'amount':1000});print('AMOUNT1000',other['row_count'],flush=True)
    alternate=pd.DataFrame(other['rows']).set_index('isin').sort_index()
    np.testing.assert_array_equal(rows.personalized_score,alternate.personalized_score)
    valid=rows.amount_contributed.notna()&alternate.amount_contributed.notna()
    changes=int(rows.loc[valid,'amount_contributed'].ne(alternate.loc[valid,'amount_contributed']).sum())
    assert changes>0
    assert base['profile_affects_ranking'] is False and base['evidence_fallback_count']==133
    receipt=dict(http_base_rows=len(rows),default_score_max_error=float((rows.personalized_score-expected['dual_w0.01']).abs().max()),
      exact_sector_ranks=True,invalid_input_http400=True,amount_field_changes_execution_for_stocks=changes,
      numerical_coverage=4436,evidence_fallbacks=133,profile_changes_stock_order=False,browser_visual_check='Unavailable: local browser disabled in Work settings')
    (ROOT/'research/runtime/sector-champion-recency/http_verification.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
