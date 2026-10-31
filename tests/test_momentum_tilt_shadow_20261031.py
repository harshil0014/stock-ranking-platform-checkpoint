import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research/runners'))
import momentum_tilt_shadow_20261031 as m


def frame():
    return pd.DataFrame(dict(isin=list('abcdef'), sector=['sector'] * 6,
                             decision_date=['2026-10-03'] * 6, profile_name=['base7500'] * 6,
                             evidence_fraction=[1.] * 6, **{'dual_w0.01': [.9, .8, .7, .69, .2, .1],
                             'signal_invested': [0., 0., -.5, .5, 0., 0.],
                             'sip_invested_0.05': [.9, .8, .675, .715, .2, .1],
                             'sip_risk_confirmed_0.01': [.9, .8, .7, .69, .2, .1]}))


def test_one_replacement_and_stable_boundary_ties():
    blobs, _ = m.frozen_observation(frame(), '2026-10-31T12:00:00Z')
    import json
    overlap = json.loads(blobs['overlap.json'])
    assert overlap['changed_sectors'] == 1 and overlap['shared_slots'] == 2
    assert overlap['rows'][0]['candidate_isins'] == ['a', 'b', 'd']


def test_frozen_audit_never_becomes_fresh_even_on_source_date():
    x = frame()
    _, receipt = m.frozen_observation(x, '2026-10-03T12:00:00Z')
    assert receipt['eligible_for_fresh_holdout'] is False
    assert receipt['fresh_forecasts'] == 0
    x['future_xirr'] = np.inf
    changed, _ = m.frozen_observation(x, '2026-10-03T12:00:00Z')
    baseline, _ = m.frozen_observation(frame(), '2026-10-03T12:00:00Z')
    assert changed == baseline


def test_replay_mismatch_nonfinite_or_duplicates_fail_closed():
    x = frame(); x.loc[0, 'sip_invested_0.05'] += .01
    with pytest.raises(ValueError, match='replay'):
        m.frozen_observation(x, 'now')
    x = frame(); x.loc[0, 'signal_invested'] = np.nan
    with pytest.raises(ValueError, match='Nonfinite'):
        m.frozen_observation(x, 'now')
    x = frame(); x.loc[0, 'isin'] = 'b'
    with pytest.raises(ValueError, match='unique'):
        m.frozen_observation(x, 'now')


def test_small_or_unclassified_groups_not_counted_as_comparable_sectors():
    x = frame(); x.loc[:1, 'sector'] = 'Unclassified'
    blobs, _ = m.frozen_observation(x, 'now')
    import json
    assert json.loads(blobs['overlap.json'])['sectors'] == 0
