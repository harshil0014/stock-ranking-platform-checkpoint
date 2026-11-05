"""Double-cost actual-open replay of frozen error-correction portfolios."""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[key]='1'
from pathlib import Path
import json,pickle,hashlib
import pandas as pd
import numpy as np
from stock_research.next_open_portfolio import next_open_portfolio
from residual_challengers_20261105 import evaluator
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/champion-rank-correction-20261105'


def main():
    path=ROOT/'research/research_variant_ledger.csv';ledger=pd.read_csv(path)
    key='champion_rank_correction_20261105::cost200_diagnostic'
    if key not in set(ledger.id):
        ledger=pd.concat([ledger,pd.DataFrame([dict(id=key,family='champion_rank_correction_20261105',name='cost200_diagnostic',source='experiments/champion-rank-correction-20261105/cost200_registration.json',category='diagnostic_or_policy_attempt')])],ignore_index=True)
        ledger.to_csv(path,index=False)
    (OUT/'cost200_registration.json').write_text(json.dumps(dict(timing='Post-result sensitivity, before higher-cost outcomes',cost_bps_per_side=200,no_selection_update=True),indent=2),encoding='utf-8')
    x=pd.read_pickle(ROOT/'work/champion-rank-correction-20261105/development_scored.pkl.gz',compression='gzip')
    with (ROOT/'work/new-information-20261101/actual_adjusted_open_close.pkl').open('rb') as f:paths=pickle.load(f)
    actions=pd.read_csv(ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv');actions=actions[actions.status.ne('ALIGNED_MULTIPLIER')]
    helper=evaluator();rows=[];fail=[]
    for date,g in x.groupby('decision_date'):
        end=str((pd.Timestamp(date)+pd.DateOffset(months=12)).date())
        blocked=set(actions.loc[actions.event_date.gt(date)&actions.event_date.le(end),'isin'])
        for name in ['champion','error_corrected_raw','error_corrected_professor']:
            selected=g.sort_values([name,'isin'],ascending=[False,True]).head(20)['isin'].tolist()
            try:
                if set(selected)&blocked:raise ValueError('Unresolved action')
                r=next_open_portfolio([helper.scope_path(paths[i],date,end) for i in selected],np.full(len(selected),1/len(selected)),date,end,7500,30,200)
                rows.append(dict(decision_date=date,model=name,xirr=r['xirr'],drawdown=r['tw_max_drawdown']))
            except (ValueError,KeyError) as e:fail.append(dict(decision_date=date,model=name,reason=str(e)))
    frame=pd.DataFrame(rows);frame.to_csv(OUT/'cost200_portfolios.csv',index=False)
    pd.DataFrame(fail).to_csv(OUT/'cost200_failures.csv',index=False)
    comparisons=[]
    for name in ['error_corrected_raw','error_corrected_professor']:
        a=frame[frame.model.eq(name)].merge(frame[frame.model.eq('champion')],on='decision_date',suffixes=('_new','_old'))
        comparisons.append(dict(model=name,matched_dates=len(a),xirr_delta=(a.xirr_new-a.xirr_old).mean(),drawdown_delta=(a.drawdown_new-a.drawdown_old).mean()))
    pd.DataFrame(comparisons).to_csv(OUT/'cost200_pairs.csv',index=False)
    # Retain all four chronological fold models in a compact usable research bundle.
    import zipfile
    bundle=Path('C:/Users/Harshil/Documents/Codex/2026-10-31/you/outputs/champion_rank_correction_research_bundle_20261105.zip')
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as archive:
        for p in (ROOT/'work/champion-rank-correction-20261105').glob('model_*.txt'):archive.write(p,'models/'+p.name)
        for p in [ROOT/'research/protocols/champion_rank_correction_20261105.md',ROOT/'research/runners/champion_rank_correction_20261105.py',ROOT/'src/stock_research/constrained_selection.py',OUT/'folds.csv']:
            archive.write(p,p.relative_to(ROOT).as_posix())
        archive.writestr('README.txt','Research-only annual rank-error models. Use exact documented within-sector feature percentiles and the existing frozen champion inputs. This bundle is not a standalone website runtime. No current forecast is included. See the report for adaptive-development limits and the separate failed historical transfer test of another policy.\n')
    (OUT/'bundle_receipt.json').write_text(json.dumps(dict(file=str(bundle),sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),bytes=bundle.stat().st_size),indent=2),encoding='utf-8')
    print(pd.DataFrame(comparisons).to_string(index=False),flush=True)


if __name__=='__main__':main()
