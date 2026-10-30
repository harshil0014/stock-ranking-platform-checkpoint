"""Separate, preserved correction for probability-CDF validity failures."""
import os
import ten_hypotheses_20261031 as core

def run():
    original=core.OUT
    core.OUT=original/'monotone_round';core.MONOTONE=True
    core.OUT.mkdir(exist_ok=True)
    core.save('protocol.json',dict(reason='Initial unrestrained classifier violated probability ordering across target thresholds. Separate mathematical-validity correction; initial run preserved.',constraints={'target_cagr':-1,'analog_attainment':1,'sigmoid_calibration_slope':'nonnegative; negative unconstrained optimum becomes constant calibrated frequency'},training='Same folds, 120 trees, 15 leaves, seed, calibration separation, cohorts and development-only selection as initial locked protocol.',fresh_validation=False,no_promotion=True))
    for name in ['panel.pkl.gz','extra_features.pkl.gz','analog_features.pkl.gz']:
        if not (core.OUT/name).exists():os.link(original/name,core.OUT/name)
    core.goal()

if __name__=='__main__':run()
