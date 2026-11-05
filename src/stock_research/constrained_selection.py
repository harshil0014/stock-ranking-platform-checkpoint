"""Select a Top3 set with lower bounds on each professor-factor sum."""
import warnings
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp


def select_three(objective, factors, champion, risk=None):
    objective = np.asarray(objective, dtype=float)
    factors = np.asarray(factors, dtype=float)
    champion = np.asarray(champion, dtype=int)
    if objective.ndim != 1 or factors.shape != (len(objective), 5):
        raise ValueError('Expected one objective and five factors per stock')
    if len(champion) != 3 or len(set(champion)) != 3:
        raise ValueError('Expected three distinct champion indices')
    if not np.isfinite(objective).all() or not np.isfinite(factors).all():
        raise ValueError('Unknown objective or factor cannot enter optimization')
    lower = factors[champion].sum(axis=0)
    matrix = np.vstack([np.ones(len(objective)), factors.T])
    bounds_lower = np.r_[3., lower]
    if risk is not None:
        risk = np.asarray(risk, dtype=float)
        if risk.shape != objective.shape or not np.isfinite(risk).all():
            raise ValueError('Expected finite historical risk per stock')
        matrix = np.vstack([matrix, -risk])
        bounds_lower = np.r_[bounds_lower, -risk[champion].sum()]
    constraint = LinearConstraint(matrix, bounds_lower,
                                  np.r_[3., np.full(len(bounds_lower)-1, np.inf)])
    # SciPy forwards threads to HiGHS, though it is not in SciPy's public option list.
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='Unrecognized options detected.*', category=RuntimeWarning)
        result = milp(-objective - 1e-10*np.arange(len(objective), 0, -1),
                      integrality=np.ones(len(objective)), bounds=Bounds(0, 1),
                      constraints=constraint,
                      options={'threads': 1, 'time_limit': 1., 'mip_rel_gap': 0.})
    selected = np.flatnonzero(result.x > .5) if result.success else champion
    difference = factors[selected].sum(axis=0) - lower
    valid = len(selected) == 3 and (difference >= -1e-7).all()
    if risk is not None:
        valid = valid and risk[selected].sum() <= risk[champion].sum() + 1e-7
    if not valid:
        selected = champion
        difference = np.zeros(5)
    order = sorted(selected, key=lambda i: (-objective[i], i))
    remaining = sorted(set(range(len(objective))) - set(order), key=lambda i: (-objective[i], i))
    score = np.empty(len(objective))
    values = np.sort(objective)[::-1]
    for i in range(1, len(values)):
        if values[i] >= values[i-1]:
            values[i] = np.nextafter(values[i-1], -np.inf)
    score[order + remaining] = values
    return score, dict(optimal=bool(result.success and valid), status=int(result.status),
                       selected=list(map(int, selected)), factor_sum_differences=difference.tolist(),
                       historical_risk_sum_delta=None if risk is None else float(risk[selected].sum()-risk[champion].sum()))
