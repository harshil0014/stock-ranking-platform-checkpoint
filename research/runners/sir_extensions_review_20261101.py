"""Integrity checks, scientific plots and report for the fixed extension round."""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[key]='1'
from pathlib import Path
import ast,datetime,hashlib,json,shutil,sys
import numpy as np
import pandas as pd
from stock_research.sir_ladder import LEVELS,ALLOTMENTS
from sir_extensions_20261101 import winmean
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'work/sir-extensions-20261101';OUT=ROOT/'experiments/sir-extensions-20261101'


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()


def table(x):
    return '| '+' | '.join(map(str,x.columns))+' |\n| '+' | '.join(['---']*len(x.columns))+' |\n'+''.join('| '+' | '.join(map(str,r))+' |\n' for r in x.itertuples(index=False,name=None))


def pct(x,cols):
    x=x.copy()
    for c in cols:x[c]=(x[c]*100).map(lambda v:f'{v:.3f}')
    return x


def plots():
    sys.path.append(str(ROOT/'work/round2-plot-deps'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    d=pd.read_csv(OUT/'dose_year_deciles.csv');tail=pd.read_csv(OUT/'tail_date_concentration.csv');l=pd.read_csv(OUT/'ladder_year_results.csv')
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(15,10),layout='constrained')
    colors={2021:'#0072B2',2022:'#D55E00',2023:'#009E73'}
    for year in [2021,2022,2023]:
        z=d[d.year.eq(year)]
        axes[0,0].plot(z.decile,z.xirr*100,marker='o',label=str(year),color=colors[year])
        axes[0,1].plot(z.decile,z.drawdown*100,marker='o',label=str(year),color=colors[year])
    axes[0,0].set(title='Professor composite: forward SIP XIRR',xlabel='Composite decile (10 = highest)',ylabel='Mean corrected 12-month XIRR (%)',xticks=range(1,11))
    axes[0,1].set(title='Professor composite: forward drawdown',xlabel='Composite decile (10 = highest)',ylabel='Mean cashflow-adjusted drawdown (%)',xticks=range(1,11))
    axes[0,0].legend(ncol=3);axes[0,1].legend(ncol=3)
    ax=axes[1,0];positions=np.arange(len(tail));values=tail.portfolio_xirr_delta.to_numpy()*100
    ax.bar(positions,values,color=np.where(values>0,'#0072B2','#D55E00'))
    ax.set_ylim(min(float(values.min())*1.15,-10),max(float(values.max())*1.25,10))
    ax.axhline(0,color='black',lw=.8);ax.set_xticks(positions,tail.decision_date.str[:7],rotation=60,ha='right',fontsize=8)
    ax.set(title='Tail hunter: paired portfolio XIRR differences',ylabel='Tail75 minus champion (pp)')
    best=int(np.argmax(values));ax.annotate(f'{tail.decision_date.iloc[best]}\n{values[best]:+.1f} pp',(best,values[best]),xytext=(0,8),textcoords='offset points',ha='center',fontsize=9)
    ax=axes[1,1]
    for rate,color in [(0,'#0072B2'),(.04,'#D55E00')]:
        z=l[l.liquidity_scope.eq('all')&l.cash_rate.eq(rate)]
        ax.plot(z.year,z.delta*100,marker='o',label=f'Cash yield {rate:.0%} scenario',color=color)
    ax.axhline(0,color='black',lw=.8);ax.set(title='Static fixed-anchor ladder versus funded SIP',xlabel='Entry year',ylabel='Budget-level XIRR difference (pp)',xticks=range(2020,2024));ax.legend(fontsize=9)
    fig.suptitle('Development diagnostics — exposed period unopened',fontsize=16)
    path=ROOT/'research/reports/sir_extensions_20261101.png';fig.savefig(path,dpi=150);plt.close(fig)
    return path


def main():
    checks=[]
    def check(name,value):
        checks.append(dict(check=name,passed=bool(value)))
        if not value:raise AssertionError(name)
    proto=ROOT/'research/protocols/sir_extensions_20261101.md'
    check('frozen protocol unchanged',sha(proto)==json.loads((OUT/'protocol_receipt.json').read_text())['sha256'])
    registry=ROOT/'research/research_variant_ledger.csv';count=json.loads((OUT/'variant_count.json').read_text());ledger=pd.read_csv(registry)
    check('registry unique IDs',not ledger.id.duplicated().any())
    check('documented count and ledger hash',len(ledger)==count['documented_attempts'] and sha(registry)==count['ledger_sha256'])
    tail=json.loads((OUT/'tail_concentration.json').read_text());t=pd.read_csv(OUT/'tail_date_concentration.csv')
    old=pd.read_csv(ROOT/'experiments/professor-frontier-20261101/development_portfolio_pairs.csv')
    expected=float(old.loc[old.model.eq('tail75')&old.policy.eq('global_top20'),'xirr_delta'].iloc[0])
    check('tail mean reproduces previous14date comparison',len(t)==14 and abs(t.portfolio_xirr_delta.mean()-expected)<1e-9)
    check('tail median and winsorized mean reproduce',np.isclose(t.portfolio_xirr_delta.median(),tail['median']) and np.isclose(winmean(t.portfolio_xirr_delta),tail['winsorized_mean']))
    check('tail leave-one-date-out reproduces',np.isclose(min(t.portfolio_xirr_delta.drop(i).mean() for i in t.index),tail['lodo_min']))
    config=json.loads((ROOT/'research/protocols/personalized_official_action_tournament_v1.json').read_text())['profiles']
    for name in ['target10','target30']:
        check('corrected profile mechanics '+name,all(config[name][k]==config['base7500'][k] for k in ['amount','interval_days','lookback_months','horizon_months']))
    p=pd.read_csv(OUT/'corrected_profile_goal_dates.csv')
    check('primary corrected profiles limited to equivalent mechanics',set(p.profile_name)=={'target10','base7500','target30'})
    check('profile outcomes matched dates for both models',p.groupby(['profile_name','decision_date']).model.nunique().eq(2).all())
    legacy=pd.read_csv(OUT/'legacy_nine_profile_dates.csv');check('all9legacy profiles covered',set(legacy.profile_name)==set(config))
    source=ROOT/'research/reports/top100-human-review-20261004/professor_formula_evidence.json';audit=json.loads(source.read_text())['Buying (MultiStock - New Alloc)']
    check('allotments agree with preserved formula audit',np.allclose([float(audit[c]['value']) for c in ['I1','K1','O1','S1','W1','AA1','AE1']],ALLOTMENTS))
    check('dip levels agree with preserved formula audit',np.allclose([-float(audit[c]['value']) for c in ['H3','J3','N3','R3','V3','Z3','AD3']],LEVELS))
    l=pd.read_csv(OUT/'ladder_date_results.csv');ly=pd.read_csv(OUT/'ladder_year_results.csv');lr=pd.read_csv(OUT/'ladder_robustness.csv')
    check('ladder rates fixed at0and4percent',set(l.cash_rate)=={0.,.04})
    check('ladder observations are unique',not l.duplicated(['decision_date','cash_rate','liquidity_scope']).any())
    check('ladder deployment fraction within budget',l.budget_deployed.between(0,1+1e-10).all())
    check('ladder stock fractions valid',l.never_fill_share.between(0,1).all() and l.five_plus_below_cost_share.between(0,1).all())
    check('ladder every scenario has all4development years',ly.groupby(['liquidity_scope','cash_rate']).year.nunique().eq(4).all())
    check('ladder no year with fewer than2dates',ly.dates.ge(2).all())
    folds=pd.read_csv(OUT/'ath_count_folds.csv');check('ATH head labels strictly mature',all(r.latest_training_label<f'{r.year}-01-01' for r in folds.itertuples()))
    coverage=pd.read_csv(OUT/'feature_coverage.csv');check('observed quote feature coverage accounted',coverage.available_ath.eq(coverage.rows).all() and coverage.available_adv20.eq(coverage.rows).all())
    files=[WORK/'low-load-tests.log'];check('16focused tests passed','16 passed' in files[0].read_text())
    # Raw panel and selections stay local. Record their hashes without publishing identities.
    cachefiles=list(WORK.glob('*.pkl*'))
    (OUT/'private_cache_inventory.json').write_text(json.dumps([dict(path=v.relative_to(ROOT).as_posix(),sha256=sha(v),bytes=v.stat().st_size) for v in sorted(cachefiles)],indent=2))
    inputs=[source,ROOT/'experiments/champion-sip-profit-20261017/historical_scores.csv.gz',ROOT/'experiments/personalized-deep-history-20261002/real-panel-v12/deep_panel.csv.gz',ROOT/'work/professor-frontier-20261101/corrected_panel.pkl.gz',ROOT/'work/professor-frontier-20261101/development_scored.pkl.gz']
    (OUT/'input_receipts.json').write_text(json.dumps([dict(path=v.relative_to(ROOT).as_posix(),sha256=sha(v)) for v in inputs],indent=2))
    goal=json.loads((OUT/'goal_profile_gate.json').read_text());dose=json.loads((OUT/'dose_gate.json').read_text());gate=json.loads((OUT/'gate_rule_result.json').read_text());ath=json.loads((OUT/'ath_count_gate.json').read_text());ladder=json.loads((OUT/'ladder_gate.json').read_text())
    (OUT/'integrity_checks.json').write_text(json.dumps(dict(all_passed=True,checks=checks),indent=2))
    (OUT/'test_receipt.json').write_text(json.dumps(dict(passed=True,tests=16,external_ci=False,log_sha256=sha(files[0])),indent=2))
    annual=pd.read_csv(OUT/'corrected_profile_goal_years.csv');annual=pct(annual,['delta'])
    contrasts=pct(pd.read_csv(OUT/'dose_fixed_contrasts.csv'),['middle_minus_top','middle_minus_low','middle_dd_minus_top'])
    ladder_view=pct(lr[['liquidity_scope','cash_rate','dates','mean','median','winsorized_mean','lodo_min','mean_dd_delta','pass_fixed_rule']],['mean','median','winsorized_mean','lodo_min','mean_dd_delta'])
    deployment=l[l.liquidity_scope.eq('all')].groupby('cash_rate')[['budget_deployed','never_fill_share','five_plus_below_cost_share']].mean().reset_index()
    deployment=pct(deployment,['budget_deployed','never_fill_share','five_plus_below_cost_share'])
    legacy_pivot=legacy.pivot(index=['profile_name','decision_date'],columns='model',values='attainment').dropna().reset_index();legacy_pivot['delta']=legacy_pivot.tail75-legacy_pivot.champion
    legacy_summary=legacy_pivot.groupby('profile_name').agg(valid_dates=('decision_date','size'),legacy_hit_delta=('delta','mean')).reset_index();legacy_summary=pct(legacy_summary,['legacy_hit_delta'])
    tails=pd.read_csv(OUT/'tail_selected_stock_distribution.csv');tails=pct(tails,['mean','median'])
    inactive=bool(l.included_stocks.eq(20).all())
    fig=plots()
    decisions=pd.DataFrame([
        ['Tail concentration','Not confirmed','Negative median, winsorized and worst exclusion means'],
        ['30% target','Not confirmed',f"Positive high-target increment in {goal['positive_high_target_years']}/3 years"],
        ['Composite sweet spot','Not confirmed',f"Fixed shape qualifies in {dose['qualifying_years']}/3 years"],
        ['CAGR/recent-high gate','Not confirmed',f"IC delta {gate['ic_delta']:+.5f}; portfolio drawdown delta {100*gate['portfolio_dd_delta']:+.3f}pp"],
        ['Static fixed-anchor ladder','Not confirmed','Lower pooled budget XIRR; yearly-sign rule fails'],
        ['ATH-cross increment','Not confirmed',f"IC increment {ath['mean']:+.6f}; hurdle {ath['required_increment']:.6f}"]],columns=['test','decision','reason'])
    decisions.to_csv(OUT/'decisions.csv',index=False)
    report=f'''# Sir-framework extensions and tail concentration audit

All five fixed extension tests remain **not confirmed** under their registered
rules. This means the candidates did not earn adoption; it does not refute the
general hypotheses. The earlier quarterly timing sign flips are likewise weak
evidence with roughly four dates per year, and were not tests of a daily ladder.
Exposed-period performance remains unopened. Champion, model weights and both
prospective-ledger streams are unchanged.

{table(decisions)}

![Reviewed development plots](sir_extensions_20261101.png)

## 1. The tail gain is concentrated

Reconstructed the exact previous 14 matched portfolio dates, with original
100bp-per-side cashflows. The XIRR mean agrees with the published comparison to
less than1e-9. Equal-weighted stock terminal wealth reproduces the two portfolio
XIRRs, allowing security deletions without incorrectly adding individual XIRRs.

| Paired portfolio XIRR statistic | Tail75 minus champion, pp |
| --- | ---: |
| Mean | {tail['mean']*100:.3f} |
| Median date | {tail['median']*100:.3f} |
| 10%-per-tail winsorized date mean | {tail['winsorized_mean']*100:.3f} |
| Worst leave-one-date-out mean | {tail['lodo_min']*100:.3f} |
| Worst leave-one-security-out mean | {tail['leave_one_security_out_min']*100:.3f} |
| 365-day block lower95% bound | {tail['low95']*100:.3f} |
| 365-day block upper95% bound | {tail['high95']*100:.3f} |

The best date is **{tail['best_date']}**, not a2020entry. It contributes
**{tail['best_date_share_of_net']*100:.1f}%** of the net sum of date-level XIRR
increments. The largest single-security contribution is
**{tail['best_stock_terminal_share']*100:.1f}%** of net additive terminal-wealth
gain. Shares exceed100% because other contributions offset them negatively.
The stock share is NOT an additive attribution of XIRR. Every security deletion
replaces its allocation with idle cash in both strategies, with no replacement
stock or reweighting. There were {tail['security_count']} distinct securities in
the union. Identities stay local.

Distribution of selected individual-stock XIRRs, including repeated cohort
observations (different from portfolio XIRR):

{table(tails)}

The original positive mean therefore does not pass the concentration screen.
Its nominal centered block-bootstrap p is {tail['nominal_p']:.4f}; the documented
attempt adjustment below gives {tail['documented_adjusted_p']:.3f}. None is fresh validation.

## 2. Running variant count

The persistent [research variant ledger](../research_variant_ledger.csv) now has
**{count['documented_attempts']} documented scoped attempts**: {count['configuration_records']}
configuration records plus {count['new_round_records']} questions/policy scenarios
registered for this round. It includes preserved120-configuration ATH refinement,
the75-policy benchmark and other catalogued tournaments and factor families.
It is not a count of299independent models. Cross-round aliases and repeated
evaluations are retained conservatively; annual fits and seeds are not each a
new strategy. Older manual/adaptive work is not exhaustively catalogued, so the
total is incomplete. New IDs append to the ledger rather than erase failed trials.

We report a nominal block-bootstrap p and min(1,p×documented attempts). This only
adjusts within the documented history; it does not repair adaptive research or
certify an all-history false-positive rate. Both the tail gain and ATH increment
have documented-adjusted p=1. No development win is promoted on this evidence.

## 3. Thirty-percent goal and the saved nine profiles

The primary corrected-label test covers target10, base7500(target20) and target30.
They share amount, contribution schedule, lookback and horizon. We use the frozen
base7500tail order and archived profile-specific champion score order, on the
same feature cohort. These archived raw profile scores differ from the normalized
champion reference used in the earlier concentration table, so their headline
results should not be directly equated. GlobalTop20 selections precede outcome
filtering; any unknown selected label blocks the date for both.

Annual Top20 attainment differences, tail minus profile champion, in pp:

{table(annual)}

At the30%goal, the increment is positive in only **{goal['positive_high_target_years']}
of2021/22/23**, short of the required two. The pooled2021–23high-target difference
is **{goal['pooled_high_target_delta']*100:+.3f}pp**. Each reported primary year has
at least two valid dates; coverage CSVs retain unknown scores/outcomes.
Changing a goal threshold can change a hit statistic without changing a single
rank. This frozen tail model is not a newly learned goal-conditional ranker, and
this test does not establish genuine target-dependent personalization.

All nine saved profiles were also checked as a **legacy cross-profile transfer
diagnostic**. Their old whole-share/same-close outcomes are not corrected next-open
evidence; amount, lookback and weekly/quarterly settings were not relabeled with
base7500outcomes. Pooled legacy hit differences in pp, with valid dates:

{table(legacy_summary)}

No high-target model was fitted or selected after these results.

## 4. Dose response: no confirmed middle band

Composite = equal mean of the five original professor-factor percentiles.
Global deciles are assigned from features before filtering future outcomes, with
deterministic ISIN tie breaks. Outcomes are corrected12-month SIP XIRR and
cashflow-adjusted stock drawdown. The chart displays2021–23;2020is context.
The one fixed sweet-spot hypothesis was deciles6–9 beating both decile10 and
deciles1–5, without worse drawdown than10. No alternative band was selected.

Return and drawdown contrasts in pp:

{table(contrasts)}

The middle beats the highest decile in2021and2023, but trails the lower five
deciles in all three primary years. The complete fixed shape qualifies in
**{dose['qualifying_years']}/3years**. This does not justify inverting the score or
choosing another interval after inspecting the curve.

## 5. Sir factors as a gate

Require3Yand5YCAGR of at least10%, plus a recorded high within365days, then keep
champion order inside passers. For the same-universe IC diagnostic, passers sort
ahead of nonpassers while each group's internal champion order is unchanged.
Simply reporting conditional IC inside the gate would be a tautological ordering
comparison, so it is not presented as a new ranker win.

Mean IC increment is **{gate['ic_delta']:+.5f}**, worse than the allowed-0.01.
On **{gate['matched_dates']}** matched globalTop20 actual SIP portfolio dates,
drawdown delta is **{gate['portfolio_dd_delta']*100:+.3f}pp** (negative means worse).
Average selected-sector-Top3stock drawdown delta is
**{gate['selected_stock_dd_delta']*100:+.3f}pp**. Both parts of the gate rule fail.

## 6. User-approved static fixed-anchor ladder

**Static fixed-anchor ladder, not the daily-reset ladder.** CapitalINR90,000is
available upfront to both policies. Stocks are the same gated-championTop20,
with equal initial capital allocations, and no replacement names. Anchor each
stock to its split-adjusted provider recorded closing high through entry; freeze
that anchor. Trigger once at closes10/15/20/25/30/35/40%below it, spending
10/5/20/10/30/15/10%of original principal at the following observed open. A stock
already below levels at entry queues those tranches for the first following open.
There is no stop-loss, anchor reset, or use of future highs.

The comparator deploys the same upfront budget in12equal real-calendar-month SIP
installments over12months. Both pay100bp per buy/sell, retain unused cash and
use identical cash treatment. Budget XIRR has the full original capital in the
denominator. Cash earns either0%or a **fixed4%annual scenario**, compounded by
actual days. The latter is an assumption, not an observed liquid-fund history,
fund recommendation or guaranteed yield. Price-only Open/Close paths omit
dividends and tax symmetrically; fractional shares keep this a research proxy.

The tranche percentages and levels match the preserved workbook formula audit.
The exported sixth-tranche quantity formula references blankA2instead of its
allocation cell; this proxy follows the user's explicitly approved15%allocation,
not that exported zero. The original attachment paths are unavailable; the
preserved audit and the user's exact approved rules supply the specification.
Unresolved action windows block the whole original portfolio and stay blocked
in every cash/liquidity scope. Unknown opens, zero-volume execution or >7day gaps
are not silently converted to idle-cash successes.

Ladder-minus-funded-SIP differences in pp,16valid dates per scenario:

{table(ladder_view)}

Positive drawdown delta means less loss. Ladder mean budget XIRR trails SIP at
both cash yields, although drawdown improves. It beats SIP in2021but not2020,
2022or2023. The registered requirement was a positive sign in every development
year, plus positive winsorized and leave-one-date-out means, so it is not confirmed.

Budget deployment and stock-ladder diagnostics (percent):

{table(deployment)}

The last column counts ladders with five or more filled tranches whose final
liquidation proceeds are below their cumulative purchase outlay, including fees.
No-fill and trap shares use repeated stock/cohort ladder observations; deployment
uses total portfolio budget.
Lowest-liquidity removal keeps excluded allocations as cash in BOTH policies.
**{'No selected stock was in the bottom ADV20 quintile, so the exclusion removed zero names. Its identical results are not an independent liquidity stress.' if inactive else 'The exclusion retained original memberships and held removed weights as cash; no new stock filled a slot.'}**

## 7. ATH-cross count beyond existing high features

The old price head already has high_hits: a fraction of local rolling-window
records, including equal highs. The new input counts strict new recorded
lifetime closing highs during the last365calendar days, excludes the first
history observation and equal highs, and uses only the prefix through the date.
It is not copied backward from the workbook's current count.

Fixed Ridge(alpha10) baseline includes the five Sir percentiles, three price/risk
inputs, recorded high proximity/recency, and the existing high_hits. The challenger
adds only the count percentile. Eight annual fits, no tuning, corrected labels
mature strictly before January1. Mean sector/date IC:

| Metric | Value |
| --- | ---: |
| Baseline IC | {ath['baseline_ic']:.6f} |
| Count-augmented IC | {ath['augmented_ic']:.6f} |
| Increment | {ath['mean']:+.6f} |
| Required increment | {ath['required_increment']:.6f} |
| Positive2021–23years | {ath['positive_2021_23_years']}/3 |
| Increment lower95% block bound | {ath['low95']:.6f} |
| Increment upper95% block bound | {ath['high95']:.6f} |

The increment is below the registered head-family floor. Its nominal p is
{ath['nominal_p']:.4f}; documented-attempt-adjusted p is
{ath['documented_adjusted_p']:.3f}. This specific incremental model remains unconfirmed.

## Verification and remaining limits

**16local tests and{len(checks)}integrity checks passed.** Tests include next-open
timing, exact monetary allocations, cash funding, never-filled ladders, no anchor
reset, unknown execution and prefix-only ATH counts. This is local validation,
not external CI or independent financial verification.

Two implementation/data issues were corrected with failed logs retained: a
duplicated profile-name column during a join, and nonpriced padding rows in cached
provider frames. Finite positive closing quotes define observed sessions; missing
opens/volume were preserved, not imputed, and execution gaps still block. The
original unfiltered cache and pre-correction coverage remain local. No threshold,
weight or trading rule was tuned from those errors. Added profile-date coverage
receipts and a pooled-date aggregation check do not alter any pass decision.

Current-survivor identities, retrospective sectors, provider adjustment vintages,
available-history rather than certified IPO-to-date ATHs, sparse overlapping
12-month cohorts and reused development dates remain material limitations.
The source quote venue is not independently certified executable NSE/BSE liquidity.
Corporate-action guards are not price repairs. No real order, stock recommendation,
model promotion or holdout evaluation occurred. One research worker/thread,
CPUcap12.5%,4seconds active/2seconds rest,no GPU; original ledger automation intact.
'''
    # Only repair fixed prose spacing; numbers and tables retain explicit units.
    replacements={'than1e-9':'than 1e-9','not a2020entry':'not a 2020 entry','exceed100%':'exceed 100%',
        'preserved120-configuration':'preserved 120-configuration','the75-policy':'the 75-policy','of299independent':'of 299 independent',
        'base7500(target20)':'base7500 (target20)','base7500tail':'base7500 tail','GlobalTop20':'Global Top-20','At the30%goal':'At the 30% goal',
        'of2021/22/23':'of 2021/22/23','pooled2021–23high-target':'pooled 2021–23 high-target','base7500outcomes':'base7500 outcomes',
        'corrected12-month':'corrected 12-month','displays2021–23;2020is':'displays 2021–23; 2020 is',
        'deciles6–9':'deciles 6–9','decile10':'decile 10','deciles1–5':'deciles 1–5','than10':'than 10',
        'in2021and2023':'in 2021 and 2023','/3years':'/3 years','Require3Yand5YCAGR':'Require 3Y and 5Y CAGR',
        'least10%':'least 10%','within365days':'within 365 days','allowed-0.01':'allowed -0.01','globalTop20':'global Top-20',
        'selected-sector-Top3stock':'selected sector Top-3 stock','CapitalINR90,000is':'Capital INR 90,000 is',
        'gated-championTop20':'gated-champion Top-20','closes10/15':'closes 10/15','10/5/20/10/30/15/10%of':'10/5/20/10/30/15/10% of',
        '40%below':'40% below','in12equal':'in 12 equal','over12months':'over 12 months','pay100bp':'pay 100bp','either0%or':'either 0% or',
        'fixed4%annual':'fixed 4% annual','blankA2instead':'blank A2 instead','approved15%allocation':'approved 15% allocation',
        '>7day':'over 7-day','pp,16valid':'pp, 16 valid','in2021but not2020':'in 2021 but not 2020','2022or2023':'2022 or 2023',
        'last365calendar':'last 365 calendar','Ridge(alpha10)':'Ridge(alpha=10)','before January1':'before January 1',
        'Positive2021–23years':'Positive 2021–23 years','lower95%':'lower 95%','upper95%':'upper 95%',
        '**16local':'**16 local','and'+str(len(checks))+'integrity':'and '+str(len(checks))+' integrity',
        'CPUcap12.5%,4seconds':'CPU cap 12.5%, 4 seconds','active/2seconds rest,no':'active/2 seconds rest, no'}
    for a,b in replacements.items():report=report.replace(a,b)
    path=ROOT/'research/reports/sir_extensions_20261101.md';path.write_text(report,encoding='utf-8',newline='\n')
    output=Path(r'C:\Users\Harshil\Documents\Codex\2026-10-31\you\outputs');shutil.copyfile(path,output/path.name);shutil.copyfile(fig,output/fig.name)
    authored=[ROOT/'src/stock_research/sir_ladder.py',ROOT/'tests/test_sir_ladder_20261101.py',ROOT/'research/runners/sir_extensions_20261101.py',Path(__file__)]
    for p in authored:ast.parse(p.read_text(encoding='utf-8'))
    logs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in WORK.glob('*.log') if p.name!='low-load-review.log']
    (OUT/'log_inventory.json').write_text(json.dumps(logs,indent=2))
    files=authored+[proto,registry,path,fig]+sorted(p for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json')
    manifest=dict(created_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(set(files))])
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2));shutil.copyfile(OUT/'manifest.json',output/'sir_extensions_20261101_manifest.json')
    print('REVIEW',len(checks),'checks;16tests; report and plots written',flush=True)


if __name__=='__main__':main()
