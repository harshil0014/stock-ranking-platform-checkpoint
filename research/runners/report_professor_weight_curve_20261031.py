"""Publish the honest preference/accuracy frontier and selected operational lens."""
from pathlib import Path
import hashlib,json,zipfile
import numpy as np
import pandas as pd
import professor_weight_curve_20261031 as c
import professor_majority_20261031 as r
from report_professor_majority_20261031 import table,uncertainty,clean_prose,plt


def main():
    r.OUT=c.OUT;r.NAMES=['active_champion']+list(c.SHARES)
    uncertainty()
    decision=json.loads((c.OUT/'decision.json').read_text());chosen=decision['selected_by_development']
    z=pd.read_csv(c.OUT/'summary.csv');current=pd.read_csv(c.OUT/'current_rankings.csv.gz');x=current.loc[current.factor_eligible].copy()
    rows=[]
    for name in r.NAMES[1:]:
        sets={n:x.sort_values(['sector',n,'isin'],ascending=[True,False,True]).groupby('sector').head(3).groupby('sector')['isin'].agg(set) for n in ['active_champion',name]}
        pairs=[(len(a&sets[name][s]),a!=sets[name][s]) for s,a in sets['active_champion'].items()]
        rows.append(dict(model=name,sectors=len(pairs),changed_sectors=sum(a[1] for a in pairs),shared_slots=sum(a[0] for a in pairs),slots=3*len(pairs)))
    overlap=pd.DataFrame(rows);overlap.to_csv(c.OUT/'current_overlap.csv',index=False)
    share=c.SHARES[chosen] if chosen else None
    decision['portfolio_noninferiority']='NOT_ESTABLISHED_FROM_MATCHED_PROXY_COHORTS'
    decision['final_status']='PREFERENCE_LENS_ONLY_NOT_INVESTMENT_REPLACEMENT'
    (c.OUT/'decision.json').write_text(json.dumps(decision,indent=2)+'\n')
    package=dict(model_id='professor_preference20_v1' if chosen=='factor20_fixed' else 'professor_preference_candidate',selected_by_development=chosen,
                 factor_core_share=share,per_factor_share=share/5 if share else None,champion_share=1-share if share else None,
                 factors=r.FACTOR_COLUMNS,entrypoint='stock_research.professor_factor_model.preference_lens(normalized_frame,core_share)',
                 normalization='normalize_factors; within-sector complete feature population before outcomes',input_as_of='2026-10-03',
                 eligible=int(current.factor_eligible.sum()),total=len(current),production_promoted=False,fresh_forecast=False,
                 missing='Unavailable lens; retain champion separately. Do not neutral-fill or redistribute weights.',
                 choice_basis='Exploratory development preference/risk point gate. Exposed diagnostics not used to choose. No statistical or investable superiority claim.',investment_replacement_eligible=False,
                 source_sha256=hashlib.sha256((c.OUT/'scored.pkl.gz').read_bytes()).hexdigest())
    (c.OUT/'model_package.json').write_text(json.dumps(package,indent=2)+'\n')
    show=z[['model','period','alignment','changed','rank_ic','attainment3','drawdown3']].copy()
    for k in ['alignment','changed','attainment3','drawdown3']:show[k]=show[k].map(lambda v:f'{v*100:.2f}%')
    show.rank_ic=show.rank_ic.map(lambda v:f'{v:.4f}')
    ports=pd.read_csv(c.OUT/'portfolio_paired.csv');p=ports.loc[ports.model.eq(chosen)].copy()
    for k in ['xirr_delta','drawdown_delta']:p[k]=p[k].map(lambda v:'unavailable' if pd.isna(v) else f'{v*100:+.2f}pp')
    text='# A substantial professor-factor preference model: completed tests\n\n'
    text+=f'Built and tested seven candidate specifications. **Selected operational preference lens: {chosen or "NONE"}.** Production champion unchanged; no fresh validation.\n\n'
    text+='## Finding\n\nThe first80/90percent majority-factor family failed the fixed development accuracy/risk limits. Its roughly19–20percentile-point alignment gain came with negative development IC and approximately6–7ppworse selected-stock drawdown. Positive Ridge with factor-weight floors did not rescue it. Forcing a majority weight is not supported by these data.\n\n'
    text+='A separate10/20/35/50percent curve was registered after those development findings and before calculating its own outcomes. This follow-up is exploratory overall; all historical periods were already exposed. The original family and its failed selection remain intact. No extra grid expansion or exposed-based retuning followed.\n\n'
    if chosen:
        text+=f'The selected lens allocates **{share*100:.0f}%of the score** to the professor-related factor block and **{(1-share)*100:.0f}%to the existing champion percentile**. Each of the five factor blocks receives **{share/5*100:.0f}%of the final score**. This is a fixed, inspectable score allocation,not a claimed accuracy improvement or causal attribution.\n\n'
    text+='The five blocks are five-completed-year annual-return consistency,3Y CAGR,5Y CAGR,inverse recorded-high age,and historical whole-share SIP profit. The full five-year return block is reconstructed from dated provider Close prices; missing history is not replaced by one-year momentum. No point-in-time fundamental panel was fabricated.\n\n'
    text+='## Matched results\n\nAlignment is intentional preference fit and partly circular,not predictive accuracy. Changed is the mean fraction of sectors whose Top3set differs. DD is average selected-stock drawdown. Same complete-factor stocks and dates for all candidates; these are different support from the earlier75-model report.\n\n'+table(show)+'\n'
    text+='The development rule required >=2percentile-point alignment gain,IC loss<=0.01,drawdown worsening<=2pp,and>=10%changed sector sets. Ten percent did not meet the alignment threshold;35/50percent lost too much ordering accuracy. The20percent model was the only passer. Exposed results are diagnostics,not the selection reason. These point limits are not proof of statistical noninferiority.\n\n'
    text+='**Investment replacement is not established:** the20percent globalTop20portfolio lost2.22ppmean XIRR in development on15/16matched dates,exceeding the earlier shadow plan\'s2pploss limit. Its exposed+9.13ppcame from only7/12dates; that selective result is not promotion evidence. SectorTop3has still fewer valid dates and worse exposed portfolio drawdown. Preference fit does not make this a better investment model.\n\n'
    text+=f'## Frozen current coverage and stock changes\n\n{package["eligible"]}/{package["total"]}issuers have the complete required factor evidence on3October2026. Others retain an explicitly unavailable lens. The production champion continues separately; no complete-market or fresh-current claim.\n\n'+table(overlap)+'\n'
    text+='## Selected-lens portfolio trade-offs\n\nDifferences from champion at25bps each buy/final sale,on paired valid dates. Provider AdjClose fractional-unit SIP proxy,not certified executable whole-share NAV. Missing paths and unresolved actions block the entire observation. Read matched/planned counts; a mean across overlapping cohorts is not a continuous strategy CAGR. These diagnostics cannot overrule the development lock.\n\n'+table(p)+'\n'
    text+='## Implementation and evidence\n\nRuntime function: `stock_research.professor_factor_model.preference_lens`. Use `normalize_factors` on causally prepared complete factor inputs. The exported package fixes weights,eligibility,source date and selection provenance. Cached current rankings are supplied; no model defaults were changed. Seven annual/current positive-Ridge fits were tested for the majority family; the bounded curve requires no new fitting. The model code is a thin open-source pandas/NumPy/scikit-learn adaptation,not a claimed pretrained Indian champion.\n\n'
    text+='`uncertainty.csv` reports4000paired calendar-block resamples at365/730days,per-metric95%simultaneous candidate bounds. Missing temporal support is unavailable. This is not joint coverage across every metric or a fresh holdout. Complete query support,portfolio failures,weights and source hashes are retained.\n\n'
    text+='## Limits\n\nOnly base7500profile and12-month outcomes. Survivor identities,retrospective sectors,provider price revisions,selective complete-history coverage and unresolved corporate-action certification remain. The price/SIP factors overlap and exclude a validated fundamental-screening model. Higher historical-factor alignment does not establish higher future returns. The fresh daily-input pipeline remains unverified. The selected lens is ready for separately registered prospective testing once eligible inputs exist; the old small-SIP-tilt stream is not silently repurposed.\n\n'
    text+='See [majority-family failures](professor_majority_20261031.md), [initial protocol](../protocols/professor_majority_20261031.json), [separate bounded-curve protocol](../protocols/professor_weight_curve_20261031.json), and [Ridge documentation](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html).\n'
    text+='\nThe current Top3counts use50complete-factor sectors,not the previous small-tilt analysis\'s57sector universe. Top3outcome support also differs between separately frozen families because an unknown selected outcome blocks the entire family query; compare within each table. Verification:19relevant tests passed,all seven Ridge fit endpoint cutoffs audited,no production scoring changes.\n'
    figures=c.OUT/'figures';figures.mkdir(exist_ok=True)
    fig,axes=plt.subplots(1,3,figsize=(12,3.8),layout='constrained')
    for period,color in [('development','#2563eb'),('exposed','#b45309')]:
        h=z.loc[z.period.eq(period)].set_index('model');anchor=h.loc['active_champion']
        weights=[0]+[int(w*100) for w in c.SHARES.values()]
        for ax,metric,mult,sign in [(axes[0],'alignment',100,1),(axes[1],'rank_ic',1,1),(axes[2],'drawdown3',100,-1)]:
            values=[0]+[float((h.loc[n,metric]-anchor[metric])*mult*sign) for n in c.SHARES]
            ax.plot(weights,values,marker='o',label=period,color=color)
            ax.axvline(20,color='#6b7280',ls=':',lw=1);ax.grid(alpha=.2);ax.set_xlabel('Explicit factor block weight (%)')
    axes[0].set(title='Preference alignment gain',ylabel='Percentile points');axes[0].axhline(2,color='#9ca3af',ls='--',lw=1)
    axes[1].set(title='Ordering trade-off',ylabel='IC change versus champion');axes[1].axhline(-.01,color='#9ca3af',ls='--',lw=1)
    axes[2].set(title='Selected-stock downside cost',ylabel='Drawdown worsening (pp)');axes[2].axhline(2,color='#9ca3af',ls='--',lw=1)
    axes[0].legend(fontsize=8);fig.suptitle('Preference-weight frontier — 20% is a research lens, not an investment upgrade',fontsize=12)
    fig.savefig(figures/'factor_weight_frontier.png',dpi=160);plt.close(fig)
    text+='\n![Weight frontier](../../experiments/professor-weight-curve-20261031/figures/factor_weight_frontier.png)\n'
    text=clean_prose(text)
    target=r.ROOT/'research/reports/professor_preference_model_20261031.md';target.write_text(text,encoding='utf-8')
    outputs=Path(r'C:\Users\Harshil\Documents\Codex\2026-10-31\you\outputs')
    handoff=text.replace('../../experiments/professor-weight-curve-20261031/figures/factor_weight_frontier.png','Professor-preference-weight-frontier-20261031.png')
    (outputs/'Professor-preference-model-results-20261031.md').write_text(handoff,encoding='utf-8')
    (outputs/'Professor-preference-weight-frontier-20261031.png').write_bytes((figures/'factor_weight_frontier.png').read_bytes())
    (outputs/'Professor-preference-model-package-20261031.json').write_text(json.dumps(package,indent=2)+'\n')
    (outputs/'Professor-preference-current-rankings-20261031.csv.gz').write_bytes((c.OUT/'current_rankings.csv.gz').read_bytes())
    artifacts=[f for f in c.OUT.rglob('*') if f.is_file() and not f.name.endswith('.pkl.gz') and f.name!='evidence_manifest.json']
    (c.OUT/'evidence_manifest.json').write_text(json.dumps({str(f.relative_to(r.ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in artifacts},indent=2)+'\n')
    archive=outputs/'Professor-preference-model-evidence-20261031.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as zf:
        for f in artifacts+[c.OUT/'evidence_manifest.json',target,c.PROTOCOL,r.PROTOCOL,Path(c.__file__),Path(r.__file__),Path(__file__),r.ROOT/'src/stock_research/professor_factor_model.py',r.ROOT/'tests/test_professor_factor_model_20261031.py']:
            zf.write(f,str(f.relative_to(r.ROOT)))
    with zipfile.ZipFile(archive) as zf:assert zf.testzip() is None
    (outputs/'Professor-preference-model-evidence-20261031.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
    print(text[:5600],flush=True)


if __name__=='__main__':main()
