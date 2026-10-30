"""Read-only V17 refined website adapter. No research runner imports or fitting."""
from collections import OrderedDict
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from time import perf_counter

import numpy as np
import pandas as pd

from stock_ranker.personalized_product import (
    PersonalizedRankingService, PersonalizationError, DOMAINS, _json_value,
)
from stock_ranker.runtime import PROJECT_ROOT
from stock_research.personalized_official_actions import OfficialActionHistoryBook
from stock_research.personalized_executable_tournament import rank_executable

POS = 'enhanced_carry_xirr_score enhanced_goal_score cash_utilization target_attainment historical_target_frequency_score strict_cagr_1y cagr_3y observed_cagr_5y strict_cagr_7y strict_cagr_10y momentum_6m distance_from_recorded_high distance_from_52w_high recovery_from_worst_trough distance_from_1y_low price_drawdown full_history_max_drawdown'.split()
NEG = 'unaffordable_rate target_shortfall old_high_depth underwater_depth realized_volatility_1y downside_volatility_1y downside_frequency_1y'.split()
CONTEXT = 'lookback_months frequency_days target_cagr amount_per_contribution target_to_contributed'.split()

def anchor(reference, values):
    arr = np.sort(pd.Series(reference).dropna().to_numpy())
    values = np.asarray(values)
    result = np.full(values.shape,.5) if not len(arr) else np.clip(
        (np.searchsorted(arr,values,'left')+np.searchsorted(arr,values,'right')+1)/(2*len(arr)),0,1)
    return np.where(pd.isna(values),np.nan,result)

def normalize(frame):
    x = frame.copy()
    for col in POS+NEG:
        x['q_'+col] = x.groupby(['decision_date','profile_name'])[col].rank(pct=True,ascending=col in POS).fillna(.5).astype('float32')
    for col in CONTEXT:
        values = x[col].astype(float)
        if col=='amount_per_contribution': values=np.log1p(values)/12
        elif col=='lookback_months': values=values/60
        elif col=='frequency_days': values=values/90
        elif col=='target_to_contributed': values=values/2
        x['u_'+col]=values.fillna(0).astype('float32')
    for out,col in zip(['market_growth','market_volatility','market_ath_depth','market_momentum'],
                       ['strict_cagr_1y','realized_volatility_1y','distance_from_recorded_high','momentum_6m']):
        x[out]=x.groupby('decision_date')[col].transform('median').fillna(0).astype('float32')
    return x

class V17RankingService(PersonalizedRankingService):
    def __init__(self, package=None):
        self.package=Path(package or os.environ.get('STOCK_RANKER_V17_RUNTIME',PROJECT_ROOT/'research/runtime/personalized-v17'))
        manifest=json.loads((self.package/'manifest.json').read_text(encoding='utf-8'))
        if manifest.get('model_id')!='personalized_v17_refined':
            raise PersonalizationError('Unexpected V17 runtime identity')
        for name,digest in manifest['files'].items():
            path=self.package/name
            if path.parent!=self.package or sha256(path.read_bytes()).hexdigest()!=digest:
                raise PersonalizationError('V17 runtime integrity check failed: '+name)
        self.manifest=manifest
        self.definition=json.loads((self.package/'definition.json').read_text())
        self.current=pd.read_csv(self.package/'current.csv.gz',low_memory=False)
        self.facts=pd.read_csv(self.package/'facts.csv.gz',low_memory=False)
        # Unknown classification is a display group, never an inferred model input.
        self.facts['product_sector']=self.facts.product_sector.fillna('Unclassified').replace(r'^\s*$','Unclassified',regex=True)
        if len(self.facts)!=4436 or self.facts['isin'].duplicated().any():
            raise PersonalizationError('V17 universe is incomplete or ambiguous')
        self.reference=pd.read_csv(self.package/'reference.csv.gz',low_memory=False)
        self.float_features=list(dict.fromkeys(self.definition['features']['raw']+['evidence_confidence']))
        self.reference[self.float_features]=self.reference[self.float_features].astype('float32')
        self.reference=normalize(self.reference)
        self.models={}
        self.book=None
        self.product_loader=lambda:self.facts.copy()
        self.cache=OrderedDict(); self.cache_size=12; self.lock=RLock()

    def metadata(self):
        return {'available':True,'status':'PERSONALIZED V17 REFINED','model_id':'personalized_v17_refined',
            'model_name':'Personalized V17','as_of_date':self.manifest['as_of_date'],
            'action_checked_through':self.manifest['action_checked_through'],'domains':DOMAINS,
            'defaults':{'amount':7500,'lookback_months':36,'interval_days':30,'target_cagr_percent':20,'horizon_months':12},
            'scientific_boundary':'V17 refined uses a fixed 3 October 2026 data snapshot. Custom profiles recompute contributions and scores with the frozen model.'}

    def _frozen_profile_name(self,profile):
        x=self.current
        found=x[(x.amount_per_contribution==profile.amount)&(x.lookback_months==profile.lookback_months)&
                (x.frequency_days==profile.interval_days)&(x.horizon_months==profile.horizon_months)&
                np.isclose(x.target_cagr,profile.target_cagr,rtol=0,atol=1e-8)].profile_name.unique()
        return str(found[0]) if len(found)==1 else None

    def _model(self,name):
        if name not in self.models:
            from lightgbm import Booster
            self.models[name]=Booster(model_file=str(self.package/(name+'.txt')))
        return self.models[name]

    def predict(self,name,x):
        m=self._model(name)
        mask=x.champion_score.notna()
        out=pd.Series(np.nan,index=x.index)
        if mask.any(): out.loc[mask]=m.predict(x.loc[mask,m.feature_name()],num_threads=4)
        return out

    def score(self,x,reference):
        """Exact refined architecture, with original empirical-CDF anchors."""
        def prediction(name): return anchor(self.predict(name,reference),self.predict(name,x))
        mono=prediction('monotone')
        partner=prediction('partner'+str(int(x.lookback_months.iloc[0])))
        confidence=x.evidence_confidence
        result=x.champion_score*(1-.3*confidence)+.3*confidence*(mono+partner)/2
        look=int(x.lookback_months.iloc[0])
        if look==36:
            result=result*(1-.1*confidence)+.1*confidence*prediction('regime')
        elif look==60:
            bag=pd.DataFrame([prediction('bag'+str(seed)) for seed in range(20261003,20261010)]).mean(axis=0).to_numpy()
            result=x.champion_score*(1-.35*confidence)+.35*confidence*(mono+bag)/2
        return result

    def _load_book(self):
        if self.book is not None: return self.book
        book=OfficialActionHistoryBook.__new__(OfficialActionHistoryBook)
        book.arrays={};book.cache={};book._window_cache={}
        with np.load(self.package/'history.npz',allow_pickle=False) as data:
            offsets=data['offsets']; arrays=[data['dates'].astype('datetime64[D]')]+[data[n] for n in ['raw','adjusted','nominal','factor']]
            for i,identity in enumerate(data['identities'].astype(str)):
                book.arrays[identity]=tuple(a[int(offsets[i]):int(offsets[i+1])] for a in arrays)
            book.errors=json.loads(data['errors_json'].tobytes().decode())
        actions=pd.read_csv(self.package/'actions.csv.gz',low_memory=False)
        actions['event_date']=pd.to_datetime(actions.event_date)
        book.actions={i:g for i,g in actions.groupby('isin')}
        book.resulting_terms=pd.read_csv(self.package/'terms.csv')
        self.book=book
        return book

    def _calculate(self,profile,*,use_stored_frozen_profile=True):
        start=perf_counter()
        name=self._frozen_profile_name(profile)
        if name and use_stored_frozen_profile:
            x=self.current[self.current.profile_name.eq(name)].copy()
        else:
            # Reuse immutable stock evidence, never another profile's execution values.
            name=name or {12:'lookback12',36:'base7500',60:'lookback60'}[profile.lookback_months]
            book=self._load_book()
            evidence=pd.DataFrame({'isin':self.facts['isin'],'global_existing_score':np.nan})
            execution=rank_executable(book,profile,self.manifest['as_of_date'],evidence)
            offsets=sorted(set(np.linspace(0,profile.lookback_months-profile.horizon_months,4).astype(int)))
            sf=pd.concat([book.simulate(profile,pd.Timestamp(self.manifest['as_of_date'])-pd.DateOffset(months=int(n)),
                months=profile.horizon_months,mode='enhanced_carry',include_journal=False).set_index('isin').target_shortfall.rename(str(n)) for n in offsets],axis=1).reindex(execution['isin'])
            confidence=sf.notna().mean(axis=1).to_numpy()
            prior=float((-execution.enhanced_goal_score).median())
            partial=execution.status.eq('AVAILABLE')&execution.enhanced_carry_xirr_score.notna()&execution.enhanced_goal_score.isna()&(confidence>0)
            recovered=-(sf.pow(2).mean(axis=1).to_numpy()*confidence+prior*(1-confidence))
            execution.loc[partial,'enhanced_goal_score']=recovered[partial]
            template=self.current[self.current.profile_name.eq(name)].copy().set_index('isin')
            for col in execution:
                if col not in ['isin','cagr_3y','cagr_5y']:
                    template[col]=execution.set_index('isin')[col].reindex(template.index)
            x=template.reset_index()
            x['lookback_months']=profile.lookback_months;x['horizon_months']=profile.horizon_months
            x['frequency_days']=profile.interval_days;x['target_cagr']=profile.target_cagr
            x['price_to_contribution']=x.terminal_price/x.amount_per_contribution.where(x.amount_per_contribution>0)
            x['target_to_contributed']=x.target_wealth/x.amount_contributed.where(x.amount_contributed>0)
            x[self.float_features]=x[self.float_features].astype('float32')
            x=normalize(x)
            ref=self.reference[self.reference.profile_name.eq(name)]
            valid=x.enhanced_carry_xirr_score.notna()&x.enhanced_goal_score.notna()
            x['champion_raw_model']=np.nan
            model=self._model('champion')
            x.loc[valid,'champion_raw_model']=model.predict(x.loc[valid,model.feature_name()],num_threads=4)
            x['champion_score']=.67*anchor(ref.enhanced_goal_score,x.enhanced_goal_score)+.33*anchor(ref.champion_raw_model,x.champion_raw_model)
            for col in POS+NEG:
                values=anchor(ref[col],x[col]);n=ref[col].notna().sum()
                x['q_'+col]=np.where(x[col].isna(),.5,values if col in POS else np.minimum(1,1-values+1/max(n,1))).astype('float32')
            x['winner_score']=self.score(x,ref)
            ranked=x.dropna(subset=['winner_score']).sort_values(['winner_score','isin'],ascending=[False,True])
            x['winner_rank']=pd.Series(np.arange(1,len(ranked)+1),index=ranked.index)
            book.cache.clear();book._window_cache.clear()
        x['personalized_score']=x.winner_score;x['personalized_rank']=x.winner_rank
        return x,perf_counter()-start

    def rank(self,payload,*,securities=None):
        with self.lock:
            result=super().rank(payload,securities=securities)
            evidence=self.current[self.current.profile_name.eq('base7500')].set_index('isin')
            for row in result['rows']:
                for col in ['evidence_confidence','distance_from_recorded_high','days_since_recorded_high','current_drawdown_duration_days']:
                    row[col]=_json_value(evidence.loc[row['isin'],col]) if row['isin'] in evidence.index else None
                if row['personalized_available']: row['result_type']='PERSONALIZED_V17'
                elif row['blocker']=='The frozen champion did not produce all score components for this profile.':
                    row['blocker']='V17 lacks sufficient usable history or execution evidence for this profile.'
            result['evaluation_mode']='V17_SNAPSHOT_PROFILE' if result['evaluation_mode']=='SEALED_EXACT_PROFILE_ARTIFACT' else 'V17_FROZEN_MODEL_RECOMPUTATION'
            return result

_SERVICE=None
_LOCK=RLock()
def service():
    global _SERVICE
    with _LOCK:
        if _SERVICE is None: _SERVICE=V17RankingService()
        return _SERVICE

def v17_metadata():
    try: return service().metadata()
    except (OSError,ValueError,ImportError) as exc:
        return {'available':False,'status':'V17 RUNTIME UNAVAILABLE','error':str(exc)}

def v17_rank(payload):
    if not isinstance(payload,dict): raise PersonalizationError('Request must be an object')
    securities=payload.get('securities')
    if securities is not None and (not isinstance(securities,list) or len(securities)>100):
        raise PersonalizationError('securities must be a list of at most 100 identifiers')
    return service().rank(payload.get('profile',payload),securities=securities)
