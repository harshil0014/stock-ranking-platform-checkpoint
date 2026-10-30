"""Retrain profile-aware challengers with unreconciled outcome windows masked."""
import json,shutil
import profile_aware_sector_20261008 as p
OUT=p.ROOT/'experiments/action-guarded-sector-20261008'

def run():
    OUT.mkdir(exist_ok=True)
    source=p.ROOT/'experiments/sector-action-integrity-20261008/guarded_training.pkl.gz'
    destination=OUT/'prepared.pkl.gz'
    if not destination.exists():shutil.copy2(source,destination)
    original=json.loads((p.OUT/'protocol.json').read_text())
    original.update(outcome_gate='Provider multiplier event lacking matching official multiplier within seven days: outcome windows spanning that event are masked for training and all model evaluation.',
      event_gate_status='Conservative evidence screen, not adjudication that all provider events are correct; source data unchanged.',
      feature_limits='Existing price-derived features and anchor predictions may still contain action/history defects; this is an outcome-label guard, not a complete source-data repair.',
      blends=[.025,.05,.1,.2,.35,.5,1.0],selection='28 guarded candidates including four pure models; all dates previously exposed.',adaptive=True,fresh_validation=False)
    (OUT/'protocol.json').write_text(json.dumps(original,indent=2))
    p.OUT=OUT;p.learn();p.evaluate(blend_weights=original['blends'])

if __name__=='__main__':run()
