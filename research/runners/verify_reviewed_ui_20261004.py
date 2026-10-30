"""Exercise reviewed rankings in the rendered desktop/mobile website."""
from pathlib import Path
import sys,json
from threading import Thread

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from stock_ranker.webapp import create_server
from playwright.sync_api import sync_playwright

def run():
    out=ROOT/'experiments/closing-high-recovery-20261004'
    server=create_server(port=0,refresh_enabled=False)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    errors=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_address[1]}/closing-high')
            page.locator('#personalizedRun').click()
            page.wait_for_selector('#personalizedResults:not(.hidden)',timeout=120000)
            assert 'Top 100 by company count' in page.locator('#personalizedDisplayNote').inner_text()
            page.locator('#personalizedSearch').fill('LALPATHLAB')
            page.wait_for_function("document.querySelectorAll('#personalizedRows tr').length===1")
            assert page.locator('#personalizedRows tr td').first.inner_text()=='11'
            page.locator('#personalizedRows button').click()
            assert '2026-10-01' in page.locator('#personalizedStockSummary').inner_text()
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(out/'reviewed-desktop.png'),full_page=True)
            page.locator('#personalizedSearch').fill('KPL')
            assert 'Kwality' in page.locator('#personalizedRows').inner_text()
            page.locator('#personalizedSearch').fill('BSE-540718')
            assert 'lot size is unverified' in page.locator('#personalizedRows').inner_text()
            page.locator('#personalizedRows button').click()
            assert 'P/E above 60' in page.locator('#personalizedStockReason').inner_text()
            page.set_viewport_size({'width':390,'height':844})
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(out/'reviewed-mobile.png'),full_page=True)
            page.locator('#personalizedModel').select_option('personalized-v17')
            assert page.locator('#personalizedResults').is_hidden()
            page.locator('#personalizedModel').select_option('closing-high')
            page.locator('#personalizedAmount').fill('8250')
            page.locator('#personalizedRun').click()
            page.wait_for_selector('#personalizedResults:not(.hidden)',timeout=180000)
            assert '8,250' in page.locator('#personalizedProfileSummary').inner_text()
            assert not errors,errors
            browser.close()
        (out/'browser_verification.json').write_text(json.dumps({'passed':True,'desktop':True,'mobile':True,
            'recovery_rank':True,'recovered_company_search':True,'sme_exclusion_visible':True,
            'financial_flags_visible':True,'mode_change_clears_results':True,'custom_profile':True,'javascript_errors':errors},indent=2))
        print('BROWSER VERIFIED',flush=True)
    finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':run()
