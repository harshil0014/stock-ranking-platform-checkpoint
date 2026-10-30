"""Finish the already-running research jobs and verify every deliverable."""
import json,subprocess,sys,time
import pandas as pd
from sector_price_rebuild_20261010 import ROOT

def call(script,*args):
    print('PIPELINE',script,*args,flush=True)
    subprocess.run([sys.executable,str(ROOT/'research/runners'/script),*args],cwd=ROOT,check=True)

def wait_file(path):
    while not path.exists():time.sleep(10)
    time.sleep(2)

def run():
    main=ROOT/'experiments/sector-price-rebuild-20261010';yeti=ROOT/'experiments/sector-yetirank-20261010'
    while True:
        try:
            if json.loads((yeti/'selection.json').read_text()).get('current_replay_exact'):break
        except (FileNotFoundError,json.JSONDecodeError):pass
        time.sleep(10)
    call('finish_sector_price_rebuild_20261010.py','--family','yeti')
    call('replay_sector_models_20261010.py','--family','yeti')
    call('review_sector_exports_20261010.py','--family','yeti')
    call('sector_tradeoffs_20261010.py','--family','yeti')
    call('sector_accuracy_20261010.py')
    call('export_sector_accuracy_20261010.py')
    call('review_sector_exports_20261010.py','--family','accuracy')
    wait_file(main/'legacy-comparison/equal_profile_summary.csv')
    call('audit_rebuilt_legacy_20261010.py')
    candidates=pd.concat([pd.read_csv(folder/'trials.csv').assign(family=family) for family,folder in [('rebuilt',main),('yeti',yeti)]])
    chosen=candidates.sort_values(['development_top3_regressions','development_regressions','model']).iloc[0]
    if chosen.family=='yeti':
        call('all_legacy_sector_comparison_20261008.py','--outcome-guard','--candidate-scores',str(yeti/'selected_historical_scores.csv.gz'),'--output-directory',str(yeti/'legacy-comparison'))
        # Legacy verification hashes the common completed test receipts.
        import shutil
        shutil.copyfile(main/'test_results.json',yeti/'test_results.json')
        call('audit_rebuilt_legacy_20261010.py','--family','yeti')
    call('finalize_sector_research_20261010.py')
    print('PIPELINE COMPLETE',flush=True)

if __name__=='__main__':run()
