"""Default-profile within-sector diagnostic using current product classifications.

Retrospective classification, not point-in-time sector validation. No fitting.
"""
from pathlib import Path
import sys,json
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from stock_research.personalized_validation import ranking_metrics

OUT=ROOT/'research/reports/sector-priority-audit-20261005'
KEYS=['isin','decision_date','profile_name']
METRICS=['median_xirr_top20','mean_asset_drawdown_top20','target_achievement_top20',
         'target_shortfall_top20','ndcg20','rank_ic','pairwise_accuracy']

def run():
    OUT.mkdir(exist_ok=True)
    facts=pd.read_csv(ROOT/'research/runtime/personalized-v17/facts.csv.gz',
                      usecols=['isin','product_sector'])
    assert facts['isin'].is_unique
    facts.product_sector=facts.product_sector.fillna('Unclassified').replace(r'^\s*$','Unclassified',regex=True)
    rows=[];coverage=[]
    for period in ['early','development','exposed']:
        folder=ROOT/'experiments'
        current=pd.read_csv(folder/f'closing-high-recovery-20261004/{period}_scores.csv.gz',
                            usecols=KEYS+['recovery_score'])
        previous=pd.read_csv(folder/f'v17-refinement-20261004/{period}_refined_scores.csv.gz')
        f=current.merge(previous,on=KEYS,validate='one_to_one')
        for path,col,name in [
            (f'v17-peak-activity-20261004/priority_{period}_scores.csv.gz','priority_score','priority_score'),
            (f'v17-peak-confirmation-20261004/{period}_scores.csv.gz','new_score','confirmation_score')]:
            x=pd.read_csv(folder/path,usecols=KEYS+[col]).rename(columns={col:name})
            f=f.merge(x,on=KEYS,validate='one_to_one')
        f=f.loc[f.profile_name.eq('base7500')].merge(facts,on='isin',validate='many_to_one')
        assert f.product_sector.notna().all()
        for (day,sector),g in f.groupby(['decision_date','product_sector']):
            columns=['recovery_score','champion_score','v17_score','repair_score','priority_score','confirmation_score']
            common=g.dropna(subset=columns+['future_xirr','future_drawdown','future_shortfall'])
            eligible=sector!='Unclassified' and len(common)>=5
            coverage.append({'period':period,'decision_date':day,'sector':sector,'rows':len(g),
                             'common_n':len(common),'evaluated':eligible})
            if not eligible:continue
            a=ranking_metrics(common,'recovery_score',top_n=3)
            for name,col in [('Original Personalized','champion_score'),('V17','v17_score'),
                             ('V17 refined','repair_score'),('Closing High priority','priority_score'),
                             ('Closing High confirmation','confirmation_score')]:
                b=ranking_metrics(common,col,top_n=3)
                row={'opponent':name,'period':period,'decision_date':day,'sector':sector,'common_n':len(common)}
                for m in METRICS:
                    key=m.replace('top20','top3').replace('ndcg20','ndcg3')
                    row.update({key+'_current':a[m],key+'_opponent':b[m],key+'_delta':a[m]-b[m]})
                rows.append(row)
        print('Finished',period,flush=True)
    q=pd.DataFrame(rows)
    assert not q.duplicated(['opponent','period','decision_date','sector']).any()
    q.to_csv(OUT/'sector_date_comparisons.csv',index=False)
    pd.DataFrame(coverage).to_csv(OUT/'sector_coverage.csv',index=False)
    columns=[c for c in q if c.endswith(('_current','_opponent','_delta'))]
    # First average dates within each sector, then sectors equally. Large sectors do not dominate.
    by_sector=q.groupby(['opponent','period','sector'])[columns].mean()
    by_sector.to_csv(OUT/'sector_period_metrics.csv')
    summary=by_sector.groupby(['opponent','period']).mean()
    summary['sectors']=by_sector.groupby(['opponent','period']).size()
    summary.to_csv(OUT/'equal_sector_summary.csv')
    metadata={'profile':'base7500','sector_mapping':'current runtime product_sector; NOT point-in-time',
              'minimum_peers':5,'top_n':3,'aggregation':'dates within sector, then sectors equally',
              'dates':q.decision_date.nunique(),'sectors':q.sector.nunique(),'paired_sector_dates':len(q),
              'scoring_changed':False,'unknown_and_small_groups_excluded':True,
              'same_population_all_six_scores':True}
    (OUT/'protocol.json').write_text(json.dumps(metadata,indent=2))
    print(summary[['median_xirr_top3_current','median_xirr_top3_opponent','sectors']].to_string())

if __name__=='__main__':run()
