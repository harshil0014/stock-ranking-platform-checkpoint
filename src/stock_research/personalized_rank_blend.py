"""Nonnegative rank ensemble trained only on matured historical goal outcomes."""
import numpy as np
import pandas as pd
from scipy.optimize import nnls

COMPONENTS=['enhanced_goal_score','global_existing_score','enhanced_carry_xirr_score']

def fit_matured_rank_blend(training, target):
    output=target.copy();output['learned_rank_blend_score']=np.nan;audits=[]
    for day, rows in output.groupby('decision_date'):
        mature=training.loc[pd.to_datetime(training.endpoint).lt(pd.Timestamp(day))].dropna(subset=COMPONENTS+['future_shortfall'])
        if mature.empty:
            raise ValueError('No matured complete labels for learned ensemble')
        x=mature.groupby(['decision_date','profile_name'])[COMPONENTS].rank(pct=True)
        y=(-mature.future_shortfall).groupby([mature.decision_date,mature.profile_name]).rank(pct=True)
        weights,_=nnls(x.to_numpy(),y.to_numpy())
        if weights.sum()<=0:weights=np.ones(len(COMPONENTS))
        weights/=weights.sum()
        ranks=rows.groupby('profile_name')[COMPONENTS].rank(pct=True)
        scores=ranks.to_numpy()@weights
        output.loc[rows.index,'learned_rank_blend_score']=np.where(ranks.notna().all(axis=1),scores,np.nan)
        audits.append({'decision_date':str(day),'latest_training_endpoint':str(mature.endpoint.max()),'training_rows':len(mature),'weights':dict(zip(COMPONENTS,weights.tolist())),'target':'Within-date/profile percentile of negative future goal shortfall','training':'Original training panel only; no target-date outcome used'})
    return output,audits
