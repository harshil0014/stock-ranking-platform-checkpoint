"""Freeze the prespecified strict-first selection across refinement rounds."""
import json,shutil
import pandas as pd
from full_coverage_challenger_20261008 import OUT,write


def run():
    frames=[]
    for r in [2,3,4,5]:
        f=pd.read_csv(OUT/f'round{r}_trials.csv');f['round']=r;frames.append(f)
    all_trials=pd.concat(frames,ignore_index=True)
    all_trials.to_csv(OUT/'refinement_trial_ledger.csv',index=False)
    passing=all_trials[all_trials.strict_gate]
    status='STRICT_RETROSPECTIVE_GATE'
    if passing.empty:passing=all_trials[all_trials.secondary_gate];status='TOLERANCE_RETROSPECTIVE_GATE'
    if passing.empty:raise RuntimeError('No candidate passes the prespecified gates')
    chosen=passing.sort_values(['utility','name'],ascending=[False,True]).iloc[0].dropna().to_dict()
    # Save every prior delivery artifact before regenerating with the chosen model.
    backup=OUT/'round1';backup.mkdir(exist_ok=True)
    names=['current_all_stock_rankings.csv','coverage.json','current_training.json','historical_query_metrics.csv.gz',
        'historical_summary.csv','all_profile_summary.csv','locked_all_profile_predictions.csv.gz','verification.json',
        'bounded_xirr_sensitivity.csv','sector_top3_deltas.csv','expanded_historical_top3_selections.csv.gz',
        'expanded_selection_audit.csv','current_sector_top3_review.csv','confidence_coverage.csv','selected_ranker.txt']
    for name in names:
        if (OUT/name).exists() and not (backup/name).exists():shutil.copy2(OUT/name,backup/name)
    active={'selected':chosen,'status':status,'fresh_validation':False,'selected_after_exposure':True,
        'round1_trials':45,'refinement_trials':len(all_trials),'total_trials':45+len(all_trials),
        'strict_passes':int(all_trials.strict_gate.sum()),'tolerance_passes':int(all_trials.secondary_gate.sum()),
        'selection_rule':'Strict gate before tolerance gate, then maximum mean bounded utility',
        'production_status':'Separate challenger; live champion untouched'}
    write('active_selection.json',active);print(json.dumps(active,indent=2))


if __name__=='__main__':run()
