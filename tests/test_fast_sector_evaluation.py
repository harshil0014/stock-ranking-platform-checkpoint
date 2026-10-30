"""Guard equivalence of the batched evaluator on ties and incomplete cohorts."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
from fast_sector_evaluation_20261008 import evaluate
from full_coverage_challenger_20261008 import evaluate as reference

def test_batched_metrics_match_reference_with_ties_missing_outcomes_and_screening():
    rows=[]
    for sector in ['A','B','Unclassified']:
        for i in range(12):
            rows.append(dict(isin=f'{sector}{i:02}',sector=sector,decision_date='2024-03-31',period='exposed',
                sector_incumbent=i/12 if i<8 else np.nan,test=i%3,second=12-i,
                future_xirr=np.nan if i==0 else (i-4)/10,future_drawdown=-i/20,future_shortfall=max(0,(6-i)/20)))
    x=pd.DataFrame(rows).sample(frac=1,random_state=19)
    pd.testing.assert_frame_equal(evaluate(x,['test','second'],(1,3,5)),reference(x,['test','second'],(1,3,5)),atol=1e-14,rtol=1e-14)
