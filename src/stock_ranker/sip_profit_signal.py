"""Bounded trailing SIP-profit adjustments; no future outcomes read here."""
import numpy as np

def adjustments(x):
    groups=[x[c] for c in ['decision_date','profile_name','sector']]
    valid=(x.evidence_fraction.gt(0)&x.sector.ne('Unclassified')&~x.sip_action_blocked
           &x.volume_active_fraction.ge(.8)&x.last_positive_volume_lag_days.between(0,14)
           &np.isfinite(x.professor_whole_share_score)&x.professor_whole_share_score.ge(-1))
    profit=x.professor_whole_share_score.where(valid)
    percentile=profit.groupby(groups).rank(pct=True)
    count=profit.groupby(groups).transform('count')
    centered=(percentile-.5).where(valid & count.ge(5),0).fillna(0)
    # Invested fraction in no-carry professor mode; uninvested cash is excluded
    # from its profit denominator, so extreme affordability can mislead.
    reliability=x.sip_invested_fraction.clip(0,1).fillna(0)
    downside=x.downside252.where(valid & np.isfinite(x.downside252)).groupby(groups).rank(pct=True,ascending=False)
    return {'plain':centered,'invested':centered*reliability,
            'risk_confirmed':centered*reliability*downside.fillna(0)}
