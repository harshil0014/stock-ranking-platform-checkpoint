"""Register an isolated shadow stream; frozen audits are never fresh forecasts."""
from pathlib import Path
import argparse
import datetime as dt
import gzip
import json
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import prospective_ledger_20261031 as ledger

ROOT = Path(__file__).resolve().parents[2]
BRANCH = 'prospective-momentum-tilt-v1'
PROTOCOL = ROOT / 'research/protocols/momentum_tilt_shadow_20261031.json'
SOURCE = ROOT / 'experiments/champion-double-emphasis-20261017/current_all_4436_audit.csv'


def overlap(scores):
    """Exactly three slots per eligible sector, stable ISIN boundary tie-break."""
    x = scores.loc[scores.sector.ne('Unclassified') & scores.evidence_fraction.gt(0)].copy()
    x = x.loc[x.groupby('sector')['isin'].transform('size').ge(5)]
    picks = {}; boundary_ties = {}
    for col in ['champion_score', 'candidate_score']:
        top = x.sort_values(['sector', col, 'isin'], ascending=[True, False, True]).groupby('sector').head(3)
        picks[col] = top.groupby('sector')['isin'].agg(set).to_dict()
        boundary_ties[col] = {}
        for sector, group in x.groupby('sector'):
            values = group[col].sort_values(ascending=False).to_numpy()
            boundary_ties[col][sector] = bool(values[2] == values[3])
    rows = []
    for sector, before in sorted(picks['champion_score'].items()):
        after = picks['candidate_score'][sector]
        rows.append(dict(sector=sector, shared=len(before & after), changed=before != after,
                         champion_isins=sorted(before), candidate_isins=sorted(after),
                         champion_boundary_tie=boundary_ties['champion_score'][sector],
                         candidate_boundary_tie=boundary_ties['candidate_score'][sector]))
    count = len(rows)
    shared = sum(r['shared'] for r in rows)
    return dict(sectors=count, changed_sectors=sum(r['changed'] for r in rows),
                shared_slots=shared, slots=3 * count,
                mean_shared_per_sector=shared / count if count else None,
                overlap_fraction=shared / (3 * count) if count else None, rows=rows)


def frozen_observation(x, observed):
    """Only a frozen implementation/overlap audit, regardless of issue timestamp."""
    required = ['isin', 'sector', 'decision_date', 'profile_name', 'dual_w0.01',
                'signal_invested', 'sip_invested_0.05', 'sip_risk_confirmed_0.01', 'evidence_fraction']
    if not set(required).issubset(x):
        raise ValueError('Missing frozen input columns')
    if x['isin'].duplicated().any() or set(x.profile_name) != {'base7500'} or x.decision_date.nunique() != 1:
        raise ValueError('Expected unique issuers and one frozen date/profile')
    if not np.isfinite(x[required[4:]].to_numpy(dtype=float)).all():
        raise ValueError('Nonfinite scores/signals')
    replay = x['dual_w0.01'] + .05 * x.signal_invested
    if not np.allclose(replay, x['sip_invested_0.05'], rtol=0, atol=1e-12):
        raise ValueError('Frozen candidate replay differs')
    if x.signal_invested.abs().gt(.5 + 1e-12).any():
        raise ValueError('SIP signal out of bounds')
    scores = x[['isin', 'sector', 'decision_date', 'profile_name', 'evidence_fraction']].copy()
    scores['champion_score'] = x['sip_risk_confirmed_0.01']
    scores['candidate_score'] = replay
    receipt = dict(stream='momentum_tilt_sip_invested005_v1', candidate='sip_invested_0.05',
                   label='Momentum-tilted preference variant; not a validated improvement',
                   record_kind='FROZEN_IMPLEMENTATION_AUDIT', source_as_of=str(x.decision_date.iloc[0]),
                   recorded_at_utc=observed, eligible_for_fresh_holdout=False,
                   eligibility_reason='Frozen source audit only; complete daily champion inputs not verified',
                   full_daily_champion_refresh_available=False, fresh_forecasts=0,
                   corporate_action_point_in_time_coverage='UNKNOWN', suspension_coverage='UNKNOWN',
                   model_promoted=False, outcome_evaluation_performed=False, rows=len(scores))
    blobs = {'frozen_comparison.csv.gz': gzip.compress(scores.to_csv(index=False, lineterminator='\n').encode(), mtime=0),
             'overlap.json': ledger.canonical(overlap(scores)), 'score_receipt.json': ledger.canonical(receipt)}
    return blobs, receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--publish', action='store_true')
    p.add_argument('--verify', action='store_true')
    args = p.parse_args()
    ledger.BRANCH = BRANCH
    ledger.WORK = ROOT / 'work/momentum-tilt-shadow'
    protocol = PROTOCOL.read_bytes()
    if args.verify:
        print(json.dumps(ledger.verify_ledger(ref=BRANCH, expected_protocol=protocol), indent=2))
        return
    registered = json.loads(protocol)
    if ledger.sha(SOURCE.read_bytes()) != registered['frozen_audit_source_sha256']:
        raise RuntimeError('Frozen source hash differs from registration')
    observed = dt.datetime.now(dt.timezone.utc).isoformat(timespec='microseconds')
    day = dt.datetime.now(ZoneInfo('Asia/Kolkata')).date()
    blobs, metadata = frozen_observation(pd.read_csv(SOURCE), observed)
    metadata['source_sha256'] = registered['frozen_audit_source_sha256']
    metadata['recorder_sha256'] = ledger.sha(Path(__file__).read_bytes())
    metadata['recording_code_commit'] = ledger.git('rev-parse', 'HEAD').decode().strip()
    # One immutable bootstrap audit, never a backfilled date or daily fake forecast.
    record = f'prospective/records/{day.isoformat()}/registration-audit'
    result = ledger.append_record(blobs, record, metadata, protocol, publish=args.publish)
    result['verification'] = ledger.verify_ledger(ref=BRANCH, expected_protocol=protocol)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
