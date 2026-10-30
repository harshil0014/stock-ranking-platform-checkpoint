"""Global Top1/3/20/100 diagnostics; never used to reselect sector finalists."""
import json
import sys
import numpy as np
import pandas as pd
from scipy.stats import rankdata
import sector_specialist_combinations_20261011 as c


def transport_scores(frame,names,group_keys,anchor=c.ANCHOR):
    """Empirical quantile mapping to each reference sector's score scale.

    No outcomes enter the transform. Candidate ties use average ranks; their
    interpolation can change marginal masses, so exact mass preservation is
    not claimed when ties differ. A reference-score control is an identity.
    """
    output=frame.copy()
    scores=frame[names].to_numpy();reference=frame[anchor].to_numpy()
    mapped=np.empty_like(scores)
    for ids in frame.groupby(group_keys,sort=False).indices.values():
        assert np.isfinite(scores[ids]).all() and np.isfinite(reference[ids]).all()
        target=np.sort(reference[ids]);ranks=rankdata(scores[ids],axis=0)-1
        for j in range(len(names)):
            mapped[ids,j]=np.interp(ranks[:,j],np.arange(len(ids)),target)
    output[names]=mapped
    return output


def main(kind,transport=False):
    p = c.p
    folder = {'specialist':'sector-specialist-ensemble-20261011',
              'neural':'sector-tabm-continuation-20261011',
              'execution':'sector-execution-specialist-20261011'}[kind]
    out = p.ROOT / 'experiments' / folder
    target = out / ('supplemental_global_transport' if transport else 'supplemental_global')
    target.mkdir(exist_ok=True)
    lock = json.loads((out / 'locked_finalists.json').read_text())
    names = lock['finalists']
    protocol = dict(finalists=names, selection_changed=False,
        selection_sha256=c.s.digest(out/'locked_finalists.json'),
        scope='Global ordering of the actual saved sector-trained scores. Sector percentile targets are not a calibration of cross-sector expected returns. This audit measures that limitation; it does not silently introduce a different global model.',
        top_ns=[1,3,20,100], reference=c.ANCHOR,
        cohorts=['common','expanded'], return_treatments=['raw','capped'],
        fresh_validation=False, mean_xirr_selection_weight=0,
        snapshot='2026-10-03', timing='Supplemental audit after locked finalist selection; no ranking adjustment from these outcomes.')
    if transport:
        protocol.update(scope='Outcome-free empirical quantile calibration within date/profile/sector: map each learned candidate rank to the reference sector score quantile. Preserve reference cross-sector score scale while testing candidate within-sector ordering. Candidate ties average ranks; duplicated reference scores can retain ties.',
            adaptation='Monotonic empirical distribution mapping, analogous to uniform quantile transform followed by inverse reference transform. No learned financial-factor percentages or company-specific exceptions.',
            hypothesis='Direct sector percentile sorting damages global selection by changing cross-sector scale. This is an adaptive follow-up after viewing execution global diagnostics, with all dates still exposed.',
            source='https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.QuantileTransformer.html')
    protocol_path = target/'protocol.json'
    if protocol_path.exists():
        assert json.loads(protocol_path.read_text()) == protocol
    else:
        protocol_path.write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    x = c.h.load()
    prefix = 'predictions' if kind == 'execution' else 'combined'
    score = pd.concat([pd.read_csv(out/f'{prefix}_{y}.csv.gz',usecols=p.KEYS+names) for y in range(2020,2026)],ignore_index=True)
    x = x.merge(score,on=p.KEYS,validate='one_to_one')
    assert len(x) == 797443
    if transport:
        x=transport_scores(x,names,['decision_date','profile_name','sector'])
    summaries=[]
    for scope in ['common','expanded']:
        z = x[x.sector_incumbent.notna()].copy() if scope=='common' else x.copy()
        # Keep genuine classifications in the saved base panel; change grouping only here.
        z['sector']='All sectors'
        for capped in [False,True]:
            path=target/f'queries_{scope}_{capped}.csv.gz'
            if path.exists():
                q=pd.read_csv(path)
            else:
                zz=z.copy()
                if capped:
                    zz.future_xirr=zz.future_xirr.clip(-1,1)
                q=p.metrics(zz,[c.ANCHOR]+names,top_ns=(1,3,20,100))
                q.to_csv(path,index=False)
            assert set(q.model)==set([c.ANCHOR]+names)
            assert set(q.top_n)=={1,3,20,100}
            summary=q.groupby(['model','period','profile','top_n'])[p.METRICS].mean().reset_index()
            summary['scope']=scope
            summary['return_treatment']='capped' if capped else 'raw'
            summaries.append(summary)
            print('GLOBAL',kind,scope,capped,flush=True)
    summary=pd.concat(summaries,ignore_index=True)
    summary.to_csv(target/'profile_metrics.csv',index=False)
    idx=summary.set_index(['model','period','profile','top_n','scope','return_treatment'])[p.METRICS]
    deltas=[]
    for name in names:
        d=idx.loc[name]-idx.loc[c.ANCHOR]
        d.shortfall=-d.shortfall
        d=d.reset_index();d['model']=name;deltas.append(d)
    pd.concat(deltas).to_csv(target/'oriented_differences.csv',index=False)
    current=pd.read_csv(out/'all_4436_financial_evidence.csv',float_precision='round_trip')
    assert len(current)==4436 and current['isin'].is_unique
    if transport:
        current=transport_scores(current,names,['sector'])
    records=[]
    for name in [c.ANCHOR]+names:
        ordered=current.sort_values('isin',kind='stable').sort_values(name,ascending=False,kind='stable').copy()
        ordered['global_position']=np.arange(1,len(ordered)+1)
        ordered['global_score_rank']=ordered[name].rank(method='min',ascending=False)
        ordered['evaluated_model']=name
        ordered['evaluated_score']=ordered[name]
        records.append(ordered)
    ranks=pd.concat(records,ignore_index=True)
    ranks.to_csv(target/'all_current_global_rankings.csv.gz',index=False)
    for n in [1,3,20,100]:
        ranks[ranks.global_position.le(n)].to_csv(target/f'current_global_top{n}.csv',index=False)
    (target/'verification.json').write_text(json.dumps(dict(historical_rows=len(x),current_rows=len(current),models=len(names)+1,profiles=int(summary.profile.nunique()),top_ns=sorted(summary.top_n.unique().tolist()),selection_unchanged=c.s.digest(out/'locked_finalists.json')==protocol['selection_sha256'],fresh_validation=False),indent=2),encoding='utf-8')


if __name__=='__main__':
    main(sys.argv[1],len(sys.argv)>2 and sys.argv[2]=='transport')
