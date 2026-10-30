"""User-authorized net-benefit review; preserve original strict-gate experiment."""
import json
import pandas as pd
import numpy as np
import champion_peer_context_20261017 as r

OUT=r.OUT/'tradeoff_review'
WEIGHTS={'rank_ic':.40,'ndcg':.25,'achievement':.15,'shortfall':.10,'drawdown':.10}

def protocol():
    OUT.mkdir(exist_ok=True)
    doc={'reason':'User explicitly permits tradeoffs on 2026-10-17; original strict gate retained as diagnostic.',
      'scope':'Damp the locked peer-risk patch within the existing R component; no new estimator or product.',
      'strengths':[.25,.5,1.0], 'weights':WEIGHTS,
      'utility':'Equal-sector/profile expanded capped Top3 mean directional changes; each metric divided by .01. These are explicit engineering preference weights, not learned truths. XIRR selection weight zero.',
      'selection':'Development-only utility; positive development and recent utility with recent aggregate drawdown and achievement degradation each <=1 percentage point. Report raw/common sensitivities and sector dispersion.',
      'sensitivity':'Ranking-only and equal-five-metric utilities; require positive recent utility under both too.',
      'fresh_validation':False}
    f=OUT/'protocol.json'
    if f.exists():assert json.loads(f.read_text())==doc
    else:f.write_text(json.dumps(doc,indent=2))

def evaluate(ref,stage):
    years=range(2020,2024) if stage=='development' else range(2024,2026)
    scores=pd.concat([pd.read_csv(r.OUT/f'predictions_{y}.csv.gz') for y in years],ignore_index=True)
    z=ref.merge(scores[r.p.KEYS+['peer_risk']],on=r.p.KEYS,validate='one_to_one')
    names=[]
    for strength in [.25,.5,1.]:
        name=f'peer_risk_strength{strength}';names.append(name)
        z[name]=z[r.ANCHOR]+strength*(z.peer_risk-z[r.ANCHOR])
    records=[];allq=[]
    for scope in ['expanded','common']:
        base=z if scope=='expanded' else z[z.sector_incumbent.notna()]
        for bounded in ['capped','raw']:
            x=base.copy()
            if bounded=='capped':x.future_xirr=x.future_xirr.clip(-1,1)
            q=r.p.metrics(x,[r.ANCHOR]+names,top_ns=(1,3,5));q['scope']=scope;q['treatment']=bounded;allq.append(q)
            s=q.groupby(['model','top_n','sector','profile'])[r.p.METRICS].mean().groupby(['model','top_n']).mean()
            for name in names:
                for k in [1,3,5]:
                    delta=s.loc[(name,k)]-s.loc[(r.ANCHOR,k)];delta.shortfall=-delta.shortfall
                    d=delta.to_dict(); utility=sum(d[c]*w/.01 for c,w in WEIGHTS.items())
                    records.append(dict(stage=stage,model=name,scope=scope,treatment=bounded,top_n=k,utility=utility,ranking_utility=(d['rank_ic']+d['ndcg'])/.02,equal_utility=sum(d[c] for c in WEIGHTS)/.05,**d))
    pd.concat(allq).to_csv(OUT/f'queries_{stage}.csv.gz',index=False)
    result=pd.DataFrame(records);result.to_csv(OUT/f'deltas_{stage}.csv',index=False);return result

def main():
    protocol(); ref=r.load_reference();dev=evaluate(ref,'development')
    chosen=dev[dev.scope.eq('expanded')&dev.treatment.eq('capped')&dev.top_n.eq(3)].sort_values(['utility','model'],ascending=[False,True]).iloc[0]
    (OUT/'lock.json').write_text(json.dumps(chosen.to_dict(),indent=2))
    recent=evaluate(ref,'recent'); row=recent[recent.model.eq(chosen.model)&recent.scope.eq('expanded')&recent.treatment.eq('capped')&recent.top_n.eq(3)].iloc[0]
    accepted=bool(chosen.utility>0 and row.utility>0 and row.ranking_utility>0 and row.equal_utility>0 and row.drawdown>=-.01 and row.achievement>=-.01)
    decision={'selected':chosen.model,'accept_research_patch':accepted,'development':chosen.to_dict(),'recent':row.to_dict(),'fresh_validation':False,'website_changed':False}
    (OUT/'decision.json').write_text(json.dumps(decision,indent=2));print(json.dumps(decision,indent=2),flush=True)

if __name__=='__main__':
    import sys
    if '--protocol' in sys.argv:protocol()
    else:main()
