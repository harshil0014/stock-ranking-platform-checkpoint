"""Closing-high confirmation ranking on the sealed V17 runtime snapshot."""
import json
from threading import RLock

import numpy as np
import pandas as pd

from stock_ranker.personalized_product import PersonalizationError, _json_value
from stock_ranker.personalized_v17_product import V17RankingService
from stock_ranker.closing_high_review import high_component, review_stock
from stock_ranker.sector_scoring import components as sector_components, score as sector_score


class PeakRankingService(V17RankingService):
    def __init__(self, package=None, *, sector_tuned=True, sector_review=True):
        super().__init__(package)
        self.sector_tuned=sector_tuned
        if sector_tuned:
            if 'sector_selection.json' not in self.manifest['files']:
                raise PersonalizationError('Sector model selection evidence is missing')
            self.sector_selection=json.loads((self.package/'sector_selection.json').read_text())
        self.sector_reviews={}
        if sector_tuned and sector_review and 'sector_review.json' in self.manifest['files']:
            receipt=json.loads((self.package/'sector_review.json').read_text())
            self.sector_reviews={r['isin']:r for r in receipt['entries']}
            for identity,entry in self.sector_reviews.items():
                mask=self.facts['isin'].eq(identity)
                if mask.sum()!=1 or self.facts.loc[mask,'product_sector'].iloc[0]!=entry['previous_sector']:
                    raise PersonalizationError('Sector review no longer matches the frozen classification')
                self.facts.loc[mask,'product_sector']=entry['sector']
        required={'peak_features.csv.gz','peak_selection.json','peak_review.csv',
                  'peak_current.csv.gz','peak_features_reviewed.csv.gz','peak_history.npz',
                  'peak_actions.csv.gz','history_validation.json'}
        if not required.issubset(self.manifest['files']):
            raise PersonalizationError('Closing-high runtime evidence is missing')
        selected=json.loads((self.package/'peak_selection.json').read_text())['winner']
        if (selected['name']!='downside_h0.3_q0.1' or selected['high']!=.3
                or selected['weight']!=.1 or selected['family']!='downside'):
            raise PersonalizationError('Unexpected closing-high model selection')
        features=pd.read_csv(self.package/'peak_features_reviewed.csv.gz',low_memory=False)
        self.current=pd.read_csv(self.package/'peak_current.csv.gz',low_memory=False)
        if self.current.duplicated(['isin','profile_name']).any():
            raise PersonalizationError('Reviewed current evidence has duplicate identities')
        self.history_validation={r['isin']:r for r in json.loads((self.package/'history_validation.json').read_text())}
        self.peak_features=features.loc[features.decision_date.eq(self.manifest['as_of_date'])].set_index('isin')
        if self.peak_features.index.has_duplicates:
            raise PersonalizationError('Closing-high evidence has duplicate identities')
        self.review_receipts=pd.read_csv(self.package/'peak_review.csv').set_index('ticker')
        if self.review_receipts.index.has_duplicates:
            raise PersonalizationError('Duplicate company review evidence')

    def metadata(self):
        result=super().metadata()
        result.update(status='CLOSING HIGH REVIEWED',model_id='closing_high_reviewed',
                      model_name='Closing High',
                      scientific_boundary='Fixed 3 October 2026 snapshot. 30% closing-high weight with continuous recovery credit near the high. Unverified SME lots excluded. Financial concerns are review flags; historical comparisons are exploratory.',
                      model_revision='recovery_20261004',recovery_band_percent=5)
        if self.sector_tuned:
            result.update(model_id='closing_high_sector',model_name='Sector Closing High',status='SECTOR CLOSING HIGH',
                model_revision='sector_20261005',ranking_scope='WITHIN_SECTOR',
                sector_weights=self.sector_selection['winner'],
                scientific_boundary='Fixed 3 October 2026 snapshot. Sector-relative scoring with 50% closing-high strength. Historical tests use current sector classifications and previously researched dates; early-period return tradeoff remains.')
        return result

    def _load_book(self):
        if self.book is not None:return self.book
        book=super()._load_book()
        with np.load(self.package/'peak_history.npz',allow_pickle=False) as data:
            offsets=data['offsets']
            arrays=[data['dates'].astype('datetime64[D]')]+[data[n] for n in ['raw','adjusted','nominal','factor']]
            for i,identity in enumerate(data['identities'].astype(str)):
                book.arrays[identity]=tuple(a[int(offsets[i]):int(offsets[i+1])] for a in arrays)
                book.errors.pop(identity,None)
        actions=pd.read_csv(self.package/'peak_actions.csv.gz',low_memory=False)
        actions['event_date']=pd.to_datetime(actions.event_date)
        book.actions={identity:g for identity,g in actions.groupby('isin')}
        return book

    def _calculate(self,profile,*,use_stored_frozen_profile=True):
        x,seconds=super()._calculate(profile,use_stored_frozen_profile=use_stored_frozen_profile)
        x=x.copy()
        needed=['high52_freshness','momentum_12_1','volume_active_fraction','traded_value',
                'observations_1y','quote_freshness','last_positive_volume_lag_days']
        static=self.peak_features.reindex(x['isin'])[needed]
        for col in needed:x[col]=static[col].to_numpy()
        age=x.days_since_recorded_high.clip(lower=0)
        high=high_component(age,x.distance_from_recorded_high,x.high52_freshness)
        momentum=x.momentum_12_1.rank(pct=True).fillna(.5)
        downside=x.downside_volatility_1y.rank(pct=True,ascending=False).fillna(.5)
        eligible=(x.volume_active_fraction.ge(.8)&np.expm1(x.traded_value).ge(100*profile.amount)
                  &x.observations_1y.ge(120)&x.quote_freshness.ge(30/37)
                  &x.last_positive_volume_lag_days.le(7)&high.notna()&x.winner_score.notna())
        facts=self.facts.set_index('isin')
        reviews=[review_stock(facts.loc[r.isin],r._asdict(),
                 self.review_receipts.loc[r.ticker] if r.ticker in self.review_receipts.index else None)
                 for r in x.itertuples()]
        sme=pd.Series([r['sme_lot_unverified'] for r in reviews],index=x.index)
        eligible &= ~sme
        sector_unverified=x['isin'].isin(self.sector_reviews)
        eligible &= ~sector_unverified
        score=(.5*x.winner_score+.3*high+.1*momentum+.1*downside).where(eligible)
        x['v17_score']=x.winner_score
        x['closing_high_component']=high
        x['momentum_component']=momentum
        x['downside_confirmation']=downside
        x['activity_eligible']=eligible
        if self.sector_tuned:
            # The previous score is retained for sparse/unclassified peer groups.
            x['current_score']=score
            x['repair_score']=x.v17_score
            x['sector']=facts.product_sector.reindex(x['isin']).to_numpy()
            x['profile_name']='active_profile'
            x['decision_date']=self.manifest['as_of_date']
            x=sector_components(x)
            score=sector_score(x,self.sector_selection['winner'])
        x['activity_filter_reason']=np.select([
            sme,x.v17_score.isna(),high.isna()|x.volume_active_fraction.isna()|x.traded_value.isna(),
            x.observations_1y.lt(120),x.quote_freshness.lt(30/37)|x.last_positive_volume_lag_days.gt(7)|x.last_positive_volume_lag_days.isna(),
            x.volume_active_fraction.lt(.8),np.expm1(x.traded_value).lt(100*profile.amount)],
            ['SME_LOT_SIZE_UNVERIFIED','BASELINE_UNAVAILABLE','ACTIVITY_OR_HIGH_UNVERIFIED','LESS_THAN_120_OBSERVATIONS',
            'NO_RECENT_QUOTE_OR_REPORTED_TRADE','INFREQUENT_REPORTED_TRADING','INSUFFICIENT_REPORTED_TRADED_VALUE'],default='ELIGIBLE')
        x.loc[sector_unverified,'activity_filter_reason']='SECTOR_CLASSIFICATION_UNVERIFIED'
        x['winner_score']=score
        ranked=x.dropna(subset=['winner_score']).sort_values(['winner_score','isin'],ascending=[False,True])
        x['winner_rank']=pd.Series(np.arange(1,len(ranked)+1),index=ranked.index)
        x['personalized_score']=x.winner_score
        x['personalized_rank']=x.winner_rank
        x['reason']=x.get('reason',pd.Series(None,index=x.index))
        excluded=x.winner_score.isna()&x.v17_score.notna()
        x.loc[excluded,'reason']='Closing-high activity screen: '+x.loc[excluded,'activity_filter_reason'].astype(str)
        return x,seconds

    def rank(self,payload,*,securities=None):
        result=super().rank(payload,securities=securities)
        evidence=self.current[self.current.profile_name.eq('base7500')].set_index('isin')
        facts=self.facts.set_index('isin')
        for row in result['rows']:
            fact=facts.loc[row['isin']]
            ev=evidence.loc[row['isin']]
            receipt=self.review_receipts.loc[row['ticker']] if row['ticker'] in self.review_receipts.index else None
            row.update(review_stock(fact,ev,receipt))
            if row['isin'] in self.history_validation:
                checked=self.history_validation[row['isin']]
                row['history_scope']='BSE series from '+checked['usable_start']+'; earlier corporate actions not certified'
                row['history_provider_symbol']=checked['provider_symbol']
            for col in ['history_months','terminal_price_date']:
                row[col]=_json_value(ev.get(col))
            row['financial_observed_at']=_json_value(fact.get('screener_source_observed_at'))
            row['financial_period']=_json_value(fact.get('screener_last_annual_result_date'))
            row['financial_review']={k:_json_value(fact.get('screener_'+k)) for k in
                ['pe_ratio','roce_pct','debt_to_equity','operating_cash_flow_crore','pledged_pct']}
            row['lot_metadata_date']=_json_value(fact.get('trade_date'))
            if row['sme_lot_unverified']:
                row['blocker']='SME lot size is unverified for this snapshot; a whole-share simulation cannot establish affordability.'
                for col in ['xirr','target_attainment','target_shortfall','shares_bought','execution_count',
                            'amount_invested','residual_cash','cash_utilization','unaffordable_rate']:
                    row[col]=None
            if row['personalized_available']:row['result_type']='CLOSING_HIGH_REVIEWED'
        top=[r for r in result['rows'] if r['personalized_available'] and r['personalized_rank']<=100]
        counts=pd.Series([r['sector'] for r in top]).value_counts()
        result['top100_sector_concentration']=[{'sector':sector,'count':int(n),'share':int(n)/len(top)} for sector,n in counts.items()]
        result['review_flagged_top100']=sum(bool(r['review_flags']) for r in top)
        result['execution_boundary']='Research ranking; reported volume is not a fill guarantee. Historical SIP uses whole shares and lacks dated lot-size verification.'
        result['evaluation_mode']=result['evaluation_mode'].replace('V17_','CLOSING_HIGH_')
        if self.sector_tuned:
            result.pop('top100_sector_concentration',None)
            result.pop('review_flagged_top100',None)
            for row in result['rows']:
                if row['isin'] in self.sector_reviews:
                    receipt=self.sector_reviews[row['isin']]
                    row['sector_classification_confidence']='UNVERIFIED_REVIEW'
                    row['blocker']=receipt['reason']
                    row['sector_review_source']=receipt['source_url']
                    if receipt['reason'] not in row['review_flags']:row['review_flags'].append(receipt['reason'])
                row['sector_scoring_fallback']=(row['sector']=='Unclassified' or row['personalized_sector_peer_count']<5)
                if row['personalized_available']:row['result_type']='CLOSING_HIGH_SECTOR'
            result['rows'].sort(key=lambda r:(r['sector'],r['personalized_sector_rank'] is None,
                                             r['personalized_sector_rank'] or 10**9,r['isin']))
            result['ranking_scope']='WITHIN_SECTOR'
            result['sector_scoring_note']='Scores compare stocks within their sector. Groups with fewer than five eligible peers and unclassified stocks retain the prior reviewed score.'
        return result


_SERVICE=None
_LOCK=RLock()
def service():
    global _SERVICE
    with _LOCK:
        if _SERVICE is None:_SERVICE=PeakRankingService()
        return _SERVICE

def peak_metadata():
    try:return service().metadata()
    except (OSError,ValueError,ImportError,PersonalizationError) as exc:
        return {'available':False,'status':'CLOSING HIGH RUNTIME UNAVAILABLE','error':str(exc)}

def peak_rank(payload):
    if not isinstance(payload,dict):raise PersonalizationError('Request must be an object')
    securities=payload.get('securities')
    if securities is not None and (not isinstance(securities,list) or len(securities)>100):
        raise PersonalizationError('securities must be a list of at most 100 identifiers')
    return service().rank(payload.get('profile',payload),securities=securities)
