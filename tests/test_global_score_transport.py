"""Outcome-free score calibration preserves reference and respects ordering."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
from supplemental_global_specialist_audit_20261011 import transport_scores


def test_transport_identity_sector_isolation_and_candidate_order():
    frame=pd.DataFrame({'sector':['A']*4+['B']*4,
        'anchor':[10.,20.,20.,40.,100.,200.,300.,400.],
        'control':[10.,20.,20.,40.,100.,200.,300.,400.],
        'candidate':[4.,3.,2.,1.,1.,2.,3.,4.],
        'future_xirr':[0.]*8})
    result=transport_scores(frame,['control','candidate'],['sector'],anchor='anchor')
    np.testing.assert_array_equal(result.control,frame.anchor)
    np.testing.assert_array_equal(result.candidate,[40.,20.,20.,10.,100.,200.,300.,400.])
    frame.future_xirr=999
    repeated=transport_scores(frame,['control','candidate'],['sector'],anchor='anchor')
    np.testing.assert_array_equal(result.candidate,repeated.candidate)
