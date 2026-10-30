"""Dated activity must replace stale current-export columns."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from io import StringIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research/runners'))
import sector_execution_specialist_20261011 as e


def test_dated_activity_replaces_stale_current_values_and_masks_unusable_rows():
    current = pd.DataFrame(dict(isin=['a','b','c'], decision_date=['2026-10-03']*3,
        evidence_fraction=[1.,0.,1.], log_amount=[9.]*3,
        volume_active_fraction=[np.nan,0.5,0.2]))
    activity = pd.DataFrame(dict(isin=['a','b'], decision_date=['2026-10-03']*2,
        volume_active_fraction=[.98,.8], traded_value=[12.,10.],
        last_positive_volume_lag_days=[1.,2.], last_observed_date=['2026-10-02']*2))
    joined = e.enrich(current, activity)
    assert joined.loc[0,'volume_active_fraction'] == .98
    assert joined.loc[0,'execution_quote_lag'] == 1
    assert joined.loc[0,'log_contribution_to_traded_value'] == -3
    assert joined.loc[1,e.EXTRA].isna().all()
    assert pd.isna(joined.loc[2,'volume_active_fraction'])
    assert joined.loc[2,'activity_available'] == 0
    assert not any(c.endswith(('_x','_y')) for c in joined)
    activity.loc[0,'last_observed_date'] = '2026-10-04'
    with pytest.raises(AssertionError):
        e.enrich(current, activity)


def test_rank_export_requires_lossless_score_parsing():
    scores = pd.Series([.3, np.nextafter(.3, 1.), .3])
    frame = pd.DataFrame({'score':scores, 'rank':scores.rank(method='min',ascending=False)})
    replay = pd.read_csv(StringIO(frame.to_csv(index=False)),float_precision='round_trip')
    np.testing.assert_array_equal(replay.score,frame.score)
    np.testing.assert_array_equal(replay['rank'],replay.score.rank(method='min',ascending=False))


def test_float32_prediction_csv_replay_at_original_precision():
    values=np.random.default_rng(3).random((300,3),dtype=np.float32)
    saved=pd.read_csv(StringIO(pd.DataFrame(values).to_csv(index=False))).to_numpy()
    assert np.max(abs(saved-values))>1e-12
    np.testing.assert_array_equal(saved.astype(values.dtype),values)
