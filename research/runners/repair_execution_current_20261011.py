"""Preserve and repair stale current inference without retraining or reselection."""
import json
import shutil
import numpy as np
import pandas as pd
import sector_execution_specialist_20261011 as e
from sector_specialist_ensemble_20261011 import digest


def main():
    out = e.OUT
    backup = out / 'before_current_activity_repair'
    backup.mkdir(exist_ok=True)
    names = ['predictions_current.csv.gz', 'all_4436_all_candidates.csv', 'audit_current.json']
    for name in names:
        if not (backup / name).exists():
            shutil.copy2(out / name, backup / name)
    old = pd.read_csv(backup / names[0])
    old_meta = pd.read_csv(backup / names[1])
    activity = pd.read_csv(e.SOURCE)
    z = e.enrich(e.h.current(), activity)
    pd.testing.assert_frame_equal(z[e.p.KEYS], old[e.p.KEYS])
    protocol = json.loads((out / 'protocol.json').read_text())
    assert protocol['source_sha256'] == digest(e.SOURCE)
    receipts = json.loads((out / 'audit_current.json').read_text())
    pred = z[e.p.KEYS + ['sector', e.h.ANCHOR, 'evidence_fraction']].copy()
    keys = ['decision_date', 'profile_name', 'sector']
    records = []
    for loss, features in e.CONFIGS:
        path = out / f'{loss}_{features}_current.txt'
        receipt = next(r for r in receipts if r['loss'] == loss and r['feature_set'] == features)
        assert receipt['model_sha256'] == digest(path)
        cols = e.p.COLS + (e.EXTRA if features == 'activity' else [])
        model = e.lgb.Booster(model_file=str(path))
        # Prove the original mismatch came from the saved missing input.
        previous = z.copy()
        previous[e.EXTRA] = old_meta[e.EXTRA]
        for label, frame in [('saved_inputs', previous), ('repaired_inputs', z)]:
            raw = model.predict(frame[cols], num_threads=3)
            rank = pd.Series(raw, index=z.index).groupby([z[k] for k in keys]).rank(pct=True).where(z.evidence_fraction.gt(0), z.champion_percentile)
            for weight in e.WEIGHTS:
                name = f'{loss}_{features}_w{weight}'
                score = (1-weight)*z.champion_percentile + weight*rank
                error = float(np.max(np.abs(score-old[name])))
                if label == 'saved_inputs':
                    assert error < 1e-12, (name, error)
                else:
                    pred[name] = score
                    records.append(dict(model=name, changed_rows=int((abs(score-old[name])>1e-12).sum()), maximum_score_change=error))
    assert np.isfinite(pred[e.NAMES]).all().all()
    cur = pred.merge(z[['isin','ticker','company','input_status','rebuilt_input_confidence','rebuilt_sector_rank'] + e.EXTRA], on='isin', validate='one_to_one')
    assert len(cur) == 4436 and cur['isin'].is_unique
    for name in e.NAMES:
        cur[name+'_rank'] = cur[name].groupby(cur.sector).rank(method='min', ascending=False)
    pred.to_csv(out / names[0], index=False)
    cur.to_csv(out / names[1], index=False)
    report = dict(reason='Original current export had entirely missing volume_active_fraction; dated source has values. Saved-input replay proves source of mismatch.', available_before=int(old_meta.volume_active_fraction.notna().sum()), available_after=int(z.volume_active_fraction.notna().sum()), backup_hashes={n:digest(backup/n) for n in names}, new_hashes={n:digest(out/n) for n in names[:2]}, changes=records, models_retrained=False, selection_changed=False, historical_predictions_changed=False)
    e.write('current_activity_repair.json', report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
