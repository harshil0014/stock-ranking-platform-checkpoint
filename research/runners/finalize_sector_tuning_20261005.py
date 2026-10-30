"""Independent serving arithmetic, sector exports and rendered workflow checks."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from stock_ranker.personalized_peak_product import PeakRankingService
from stock_ranker.personalized_product import parse_profile
OUT=ROOT/'experiments/sector-tuning-20261005'

def verify():
    new=PeakRankingService(sector_review=False);old=PeakRankingService(sector_tuned=False)
    pieces=[];checks=[]
    for name,group in new.current.groupby('profile_name'):
        r=group.iloc[0]
        payload={'amount':float(r.amount_per_contribution),'lookback_months':int(r.lookback_months),
            'interval_days':int(r.frequency_days),'target_cagr_percent':float(r.target_cagr)*100,'horizon_months':int(r.horizon_months)}
        prior,_=old._calculate(parse_profile(payload));actual,_=new._calculate(parse_profile(payload))
        prior['sector']=new.facts.set_index('isin').product_sector.reindex(prior['isin']).to_numpy()
        expected=prior.personalized_score.copy()
        for sector,g in prior[prior.personalized_score.notna()].groupby('sector'):
            if len(g)<5 or sector=='Unclassified':continue
            expected.loc[g.index]=(.25*g.v17_score.rank(pct=True).fillna(.5)
                +.25*g.closing_high_component+.25*g.closing_high_component.rank(pct=True).fillna(.5)
                +.2*g.downside_volatility_1y.rank(pct=True,ascending=False).fillna(.5)
                +.05*g.momentum_12_1.rank(pct=True).fillna(.5))
        np.testing.assert_allclose(actual.personalized_score,expected,atol=1e-12,rtol=0,equal_nan=True)
        assert actual.personalized_score.notna().equals(prior.personalized_score.notna())
        response=new.rank(payload);rows=pd.DataFrame(response['rows'])
        eligible=rows[rows.personalized_available].sort_values(['sector','personalized_score','isin'],ascending=[True,False,True])
        oracle=eligible.groupby('sector').cumcount()+1
        np.testing.assert_array_equal(eligible.personalized_sector_rank,oracle)
        assert rows.loc[rows.sme_lot_unverified,'personalized_available'].eq(False).all()
        rows['profile_name']=name
        keep=['profile_name','isin','ticker','sector','personalized_score','personalized_sector_rank',
              'personalized_sector_peer_count','personalized_available','sector_scoring_fallback','days_since_recorded_high']
        pieces.append(rows[keep]);checks.append({'profile':name,'rows':len(rows),'ranked':len(eligible),'sector_rank_verified':True})
        print('VERIFIED',name,flush=True)
    data=pd.concat(pieces,ignore_index=True)
    data.to_csv(OUT/'current_sector_rankings.csv.gz',index=False)
    data[data.personalized_sector_rank.le(3)].to_csv(OUT/'current_sector_top3.csv',index=False)
    base=data[data.profile_name.eq('base7500')]
    assert base.loc[base.ticker.eq('NYKAA'),'days_since_recorded_high'].iloc[0]==1765
    custom=new.rank({'amount':8250,'lookback_months':36,'interval_days':30,'target_cagr_percent':20,'horizon_months':12})
    assert custom['model_id']=='closing_high_sector' and custom['ranking_scope']=='WITHIN_SECTOR'
    assert custom['evaluation_mode']=='CLOSING_HIGH_FROZEN_MODEL_RECOMPUTATION'
    (OUT/'serving_verification.json').write_text(json.dumps({'profiles':checks,'custom_profile':8250,
        'independent_score_arithmetic':True,'eligibility_unchanged':True,'nykaa_ath_age':1765},indent=2))

def browser():
    from threading import Thread
    from playwright.sync_api import sync_playwright
    from stock_ranker.webapp import create_server
    server=create_server(port=0,refresh_enabled=False)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    errors=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_address[1]}/closing-high')
            page.locator('#personalizedRun').click()
            page.wait_for_selector('#personalizedRows tr',timeout=120000)
            page.locator('#personalizedSector').select_option('Banks')
            assert page.locator('#personalizedRows tr').count()>5
            assert page.locator('#personalizedRows tr').first.locator('td').nth(0).is_hidden()
            assert page.locator('#personalizedRows tr').first.locator('td').nth(3).inner_text().startswith('1 /')
            page.screenshot(path=str(OUT/'sector_desktop.png'),full_page=True)
            page.locator('#personalizedRows tr').first.get_by_role('button',name='Inspect').click()
            assert 'Overall Personalized Rank' not in page.locator('#personalizedStockSummary').inner_text()
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(OUT/'sector_mobile.png'),full_page=True)
            assert page.locator('#personalizedSector').is_visible()
            assert not errors,errors
            browser.close()
        (OUT/'browser_verification.json').write_text(json.dumps({'desktop':True,'mobile':True,'sector_filter':'Banks',
            'global_rank_hidden':True,'sector_rank_one_first':True,'javascript_errors':errors},indent=2))
        print('BROWSER VERIFIED',flush=True)
    finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':globals()[sys.argv[1]]()
