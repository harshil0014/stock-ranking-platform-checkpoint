"""User-selected recency champion; frozen price evidence, live profile inference."""
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock

import lightgbm as lgb
import numpy as np
import pandas as pd

from stock_ranker.runtime import PROJECT_ROOT
from stock_ranker.personalized_product import PersonalizationError, parse_profile, _json_value
from stock_ranker.personalized_peak_product import PeakRankingService
from stock_ranker.sip_profit_signal import adjustments


def recency_adjustment(x):
    groups=[x.sector]  # One complete snapshot/profile per request; filter after scoring.
    valid=(x.evidence_fraction.gt(0)&x.observations.ge(252)&x.history_days.ge(365)
           &x.volume_active_fraction.ge(.8)&x.last_positive_volume_lag_days.between(0,14)
           &x.sector.ne('Unclassified'))
    def rank(col,age=False):
        v=x[col].where(valid & np.isfinite(x[col]))
        if age:v=v.where(v.ge(0))
        return v.groupby(groups).rank(pct=True,ascending=not age)
    age=(rank('days_since_52w_closing_high',True)+rank('days_since_recorded_high',True))/2
    proximity=(rank('distance_from_52w_high')+rank('distance_from_recorded_high'))/2
    h=.60*age+.25*proximity+.15*rank('momentum12_1')
    return .01*(h-.5).where(valid & h.groupby(groups).transform('count').ge(5),0).fillna(0)


class ChampionScorer:
    def __init__(self,package=None):
        self.package=Path(package or os.environ.get('STOCK_RANKER_SECTOR_CHAMPION_RUNTIME',PROJECT_ROOT/'research/runtime/sector-champion-recency'))
        self.manifest=json.loads((self.package/'manifest.json').read_text())
        if self.manifest['model_id']!='sector_champion_recency_20261017':
            raise PersonalizationError('Unexpected sector champion identity')
        for name,digest in self.manifest['files'].items():
            if Path(name).name!=name or sha256((self.package/name).read_bytes()).hexdigest()!=digest:
                raise PersonalizationError('Sector champion integrity check failed: '+name)
        self.frames={n:pd.read_csv(self.package/f'{n}.csv.gz') for n in ['profile_inputs','price_inputs']}
        self.models={n:lgb.Booster(model_file=str(self.package/f'{n}.txt')) for n in ['profile','price']}
        self.sip_enabled=self.manifest.get('sip_weight',0)==.01
        if self.sip_enabled:
            self.sip_profiles=pd.read_csv(self.package/'sip_profiles.csv.gz')
            self.sip_events=pd.read_csv(self.package/'sip_events.csv')
        if any(len(x)!=4436 or x['isin'].duplicated().any() for x in self.frames.values()):
            raise PersonalizationError('Sector champion universe is incomplete')
        if not self.frames['profile_inputs']['isin'].equals(self.frames['price_inputs']['isin']):
            raise PersonalizationError('Sector champion component identities differ')

    def score(self,profile):
        parts={}
        for name in ['profile','price']:
            x=self.frames[name+'_inputs'].copy()
            x['log_amount']=np.log(profile.amount);x['lookback_months']=profile.lookback_months
            x['log_interval']=np.log(profile.interval_days);x['target_cagr']=profile.target_cagr
            model=self.models[name]
            raw=pd.Series(model.predict(x[model.feature_name()].astype('float32'),num_threads=3),index=x.index)
            parts[name]=raw.groupby(x.sector).rank(pct=True).where(x.evidence_fraction.gt(0),.5)
        x=self.frames['price_inputs'].copy()
        x['original_champion_score']=.75*(.8*x.open_model_score+.2*parts['profile'])+.25*parts['price']
        x['recency_adjustment']=recency_adjustment(x)
        x['personalized_score']=x.original_champion_score+x.recency_adjustment
        x['personalized_sector_rank']=x.personalized_score.groupby(x.sector).rank(method='min',ascending=False).astype(int)
        x['personalized_sector_peer_count']=x.groupby('sector')['isin'].transform('size')
        if not np.isfinite(x.personalized_score).all():raise PersonalizationError('Nonfinite champion scores')
        return x

    def add_sip(self,x,profile,evidence):
        x=x.copy();x['recency_champion_score']=x.personalized_score
        x['decision_date']=self.manifest['as_of_date'];x['profile_name']='request'
        x=x.merge(evidence[['isin','professor_whole_share_score','unused_cash_excluded_by_professor','amount_contributed']],on='isin',how='left',validate='one_to_one')
        x['sip_invested_fraction']=1-x.unused_cash_excluded_by_professor/x.amount_contributed.where(x.amount_contributed.gt(0))
        end=pd.Timestamp(self.manifest['as_of_date']);start=end-pd.DateOffset(months=profile.lookback_months)
        events=self.sip_events
        dates=pd.to_datetime(events.event_date)
        blocked=set(events.loc[dates.gt(start)&dates.le(end),'isin'])
        x['sip_action_blocked']=x['isin'].isin(blocked)
        x['sip_profit_adjustment']=.01*adjustments(x)['risk_confirmed']
        x['personalized_score']=x.recency_champion_score+x.sip_profit_adjustment
        x['personalized_sector_rank']=x.personalized_score.groupby(x.sector).rank(method='min',ascending=False).astype(int)
        return x


class SectorChampionService(PeakRankingService):
    def __init__(self,package=None,champion_package=None):
        super().__init__(package)
        self.scorer=ChampionScorer(champion_package)

    def metadata(self):
        result=super().metadata()
        result.update(model_id='sector_champion_recency_20261017',model_name='Sector Champion',
          status='SECTOR CHAMPION',model_revision='dual_w0.01_20261017',ranking_scope='WITHIN_SECTOR',
          sector_weights={'recency_adjustment_strength':.01,'recency':.60,'proximity':.25,'momentum':.15},
          profile_affects_ranking=False,
          scientific_boundary='User-selected champion with accepted historical tradeoffs. Fixed 3 October 2026 price evidence. Frozen models learned no profile-parameter splits: profile fields affect execution and goal calculations, not stock order. Added signal: 60% high recency, 25% proximity, 15% momentum, at 0.01 strength. Not a 60% total-model weight or fresh validation.')
        if self.scorer.sip_enabled:
            result.update(model_revision='dual_w0.01_sip_risk_confirmed0.01_20261017',profile_affects_ranking=True,
                scientific_boundary='Fixed 3 October 2026 snapshot. Original champion plus unchanged high-recency adjustment and 0.01 downside/affordability-adjusted trailing SIP-profit signal. Amount, interval and lookback can change SIP rankings; target affects goal calculations. User accepted historical tradeoffs; no fresh validation.')
            result['sector_weights']['sip_profit_adjustment_strength']=.01
        return result

    def rank(self,payload,*,securities=None):
        profile=parse_profile(payload)
        with self.lock:
            # Reuse existing execution simulation, validation and identity aliases.
            result=super().rank(payload,securities=securities)
            scores=self.scorer.score(profile)
            if self.scorer.sip_enabled:
                name=self._frozen_profile_name(profile)
                if name:
                    evidence=self.scorer.sip_profiles[self.scorer.sip_profiles.profile_name.eq(name)]
                else:
                    evidence=self._load_book().simulate(profile,self.manifest['as_of_date'],mode='professor',include_journal=False).rename(columns={'profit_loss_pct':'professor_whole_share_score'})
                scores=self.scorer.add_sip(scores,profile,evidence)
            scores=scores.set_index('isin')
            if set(scores.index)!={r['isin'] for r in result['rows']}:
                raise PersonalizationError('Champion and website universes differ')
            for row in result['rows']:
                s=scores.loc[row['isin']]
                row['execution_available']=row['execution_status']=='AVAILABLE' and row['execution_count'] is not None
                row['execution_blocker']=row['blocker']
                row.update(personalized_available=True,result_type='SECTOR_CHAMPION',personalized_rank=None,
                           sector=s.sector,sector_security_count=int(s.personalized_sector_peer_count),
                           evidence_confidence=float(s.evidence_fraction),sector_scoring_fallback=bool(s.evidence_fraction<=0))
                for col in ['personalized_score','personalized_sector_rank','personalized_sector_peer_count',
                            'original_champion_score','recency_adjustment','days_since_recorded_high',
                            'days_since_52w_closing_high','distance_from_recorded_high']:
                    row[col]=_json_value(s[col])
                if self.scorer.sip_enabled:
                    for col in ['recency_champion_score','professor_whole_share_score','sip_profit_adjustment','sip_action_blocked']:
                        row[col]=_json_value(s[col])
                if s.evidence_fraction<=0:
                    row['result_type']='SECTOR_CHAMPION_EVIDENCE_FALLBACK'
                    row['blocker']='Limited price evidence: inherited component fallback; ranking does not establish trading eligibility.'
            result['rows'].sort(key=lambda r:(r['sector'],r['personalized_sector_rank'],r['isin']))
            result.update(profile=asdict(profile),personalized_count=len(scores),fallback_count=0,
                evidence_fallback_count=int(scores.evidence_fraction.le(0).sum()),
                sector_count=int(scores.sector.nunique()),evaluation_mode='FROZEN_CHAMPION_WITH_PROFILE_EXECUTION',
                sector_scoring_note='All 4,436 securities ranked within frozen sectors. Equal scores share a rank. Unclassified is a display group. Price-evidence fallbacks are labelled.',
                execution_boundary='Ranking coverage is separate from execution eligibility. SIP execution details use your submitted fields; a ranking is not a fill guarantee.')
            json.dumps(result,allow_nan=False)
            return result


_SERVICE=None
_LOCK=RLock()
def service():
    global _SERVICE
    with _LOCK:
        if _SERVICE is None:_SERVICE=SectorChampionService()
        return _SERVICE

def champion_metadata():
    try:return service().metadata()
    except (OSError,ValueError,ImportError) as exc:
        return {'available':False,'status':'CHAMPION RUNTIME UNAVAILABLE','error':str(exc)}

def champion_rank(payload):
    if not isinstance(payload,dict):raise PersonalizationError('Request must be an object')
    securities=payload.get('securities')
    if securities is not None and (not isinstance(securities,list) or len(securities)>100):
        raise PersonalizationError('securities must be a list of at most 100 identifiers')
    return service().rank(payload.get('profile',payload),securities=securities)
