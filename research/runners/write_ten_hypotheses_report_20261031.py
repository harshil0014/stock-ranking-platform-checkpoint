"""Compile the research results without selecting on exposed outcomes."""
from pathlib import Path
import json
import pandas as pd
import ten_hypotheses_20261031 as c
ROOT,OUT=c.ROOT,c.OUT

def table(frame):
    def fmt(v):
        if isinstance(v,float):return f'{v:.6f}'
        return str(v).replace('|','/')
    return '| '+' | '.join(map(str,frame.columns))+' |\n| '+' | '.join(['---']*len(frame.columns))+' |\n'+'\n'.join('| '+' | '.join(fmt(v) for v in row)+' |' for row in frame.itertuples(index=False,name=None))

def main():
    noise=pd.read_csv(OUT/'noise_floor.csv');confidence=pd.read_csv(OUT/'confidence_summary.csv');hys=pd.read_csv(OUT/'hysteresis_summary.csv');meta=pd.read_csv(OUT/'meta_summary.csv')
    head=pd.read_csv(OUT/'rank_head_round/summary.csv');kronos=pd.read_csv(OUT/'kronos_rank_head/summary.csv')
    goal=pd.read_csv(OUT/'monotone_round/goal_summary.csv');cal=pd.read_csv(OUT/'monotone_round/goal_calibration.csv');changes=pd.read_csv(OUT/'monotone_round/goal_target_rank_changes.csv')
    lock=json.loads((OUT/'monotone_round/goal_development_lock.json').read_text());selected=lock['selected']
    chosen_head=json.loads((OUT/'rank_head_round/development_lock.json').read_text())['selected']
    def row(frame,period,model):return frame[frame.period.eq(period)&frame.model.eq(model)].iloc[0]
    def delta(frame,model,period,metric,base=c.ANCHOR):return row(frame,period,model)[metric]-row(frame,period,base)[metric]
    floor_ic=noise[noise.period.eq('development')&noise.metric.eq('rank_ic')].familywise_95.max();floor_hit=noise[noise.period.eq('development')&noise.metric.eq('achievement')].familywise_95.max()
    h=hys[hys.selected].set_index('period');g=row(goal,'exposed',selected);a=row(goal,'exposed',c.ANCHOR);b=cal[cal.period.eq('exposed')].set_index('model')
    findings=[
        ('1. Noise floor','Use as a measurement control',f'35 fixed related policies; development 95% lucky-win hurdle {floor_ic:.5f} IC / {100*floor_hit:.3f}pp attainment. Not a universal future threshold.'),
        ('2. Disagreement confidence','Do not activate abstention','Development selected 100% retained coverage; lower disagreement did not improve development pair accuracy.'),
        ('3. Rank hysteresis','Promising UI research pilot',f'Margin .02: exposed Kendall tau {h.loc["exposed","raw_tau"]:.3f} -> {h.loc["exposed","kendall_tau"]:.3f}; observed IC delta {h.loc["exposed","ic_delta"]:+.5f}. Quarterly/monthly, not daily refresh validation.'),
        ('4. Goal probability','Do not replace incumbent',f'Corrected selected {selected}: exposed attainment {100*a.achievement:.2f}% -> {100*g.achievement:.2f}%, selected-asset drawdown {100*a.drawdown:.2f}% -> {100*g.drawdown:.2f}%; Brier {b.loc[selected,"brier"]:.4f} vs climatology {b.loc["climatology","brier"]:.4f}.'),
        ('5. SIP path dependence','Volatility hypothesis not robustly confirmed','Conditional volatility coefficient is uncertain in development; fractional-SIP coefficient is negative there. Recovery-duration association is descriptive and ex-post.'),
        ('6. Meta-labeling','Do not activate gate','Mature out-of-time Top3 logistic meta-labeler selected full coverage on development. No successful abstention policy.'),
        ('7. Volume / filing metadata','No promotion; filing test blocked',f'Volume in original ranking head: IC delta dev {delta(head,"head_volume","development","rank_ic"):+.5f}, exposed {delta(head,"head_volume","exposed","rank_ic"):+.5f}. Historical filing-submission timestamps unavailable.'),
        ('8. Correlation peers','No promotion; gain below noise',f'25 calendar-aligned correlation peers. Original-head IC delta dev {delta(head,"head_peers","development","rank_ic"):+.5f}, exposed {delta(head,"head_peers","exposed","rank_ic"):+.5f}; sector evaluation retained.'),
        ('9. Kronos extractor','Do not add this extractor',f'Matched original-head IC delta dev {delta(kronos,"kronos_head","development","rank_ic","matched_head"):+.5f}, exposed {delta(kronos,"kronos_head","exposed","rank_ic","matched_head"):+.5f}; exposed attainment delta {100*delta(kronos,"kronos_head","exposed","achievement","matched_head"):+.3f}pp. Pretraining contamination risk.'),
        ('10. Historical look-alikes','No promotion; IC fell in both periods',f'50 mature neighbors, PCA8 path embedding, same issuer excluded. Original-head IC delta dev {delta(head,"head_analogs","development","rank_ic"):+.5f}, exposed {delta(head,"head_analogs","exposed","rank_ic"):+.5f}. 250 current-snapshot neighbor examples saved.')]
    findings=pd.DataFrame(findings,columns=['Idea','Decision','Evidence']);findings.to_csv(OUT/'ten_idea_summary.csv',index=False)
    selected_noise=pd.read_csv(OUT/'rank_head_round/selection_noise_floor.csv')
    source=ROOT/'research/reports/ten_hypotheses_20261031.md'
    text=f'''# Ten stock-ranking research pilots — 31 October 2026

The completed pilots support keeping the active champion. Rank hysteresis is a useful UI candidate. Model-confidence abstention and meta-labeling did not earn development selection. New goal-probability forecasts have real target-dependent behavior but poor calibration/risk tradeoffs. The filing-metadata part could not be tested from accessible local files.

The application and incumbent model package were not changed. This report records local retrospective research, not a deployed ranking upgrade.

## Results by requested idea

{table(findings)}

## Data, baseline and evaluation boundaries

Baseline application commit: `a216d6dd0af742b719cbe449ff2b2d2f4ef2ca5d`. Saved original champion plus its approved high-recency and SIP overlays is the anchor. Prepared data has 1,179,002 rows, 44 dates and nine investor profiles. Development is 2020–2023; 2024–2025 was already repeatedly exposed. There is no fresh holdout in this work. Most historical dates are quarterly; 2025 has monthly observations through August. Current artifacts describe the frozen **3 October 2026** snapshot, not today's market.

The recovered Yahoo OHLCV batches cover 4,346 identities. The build produced 132,125 usable stock/date windows, and excluded 622 price-basis disagreements from the new OHLCV feature families. Original model inputs and labels were preserved. Current-survivor identities, retrospective sector mapping, provider revisions and incomplete corporate-action certification limit every result. Outcomes are gross simulated whole-share SIP outcomes; the displayed drawdown statistic is an average of selected stocks' drawdowns, not portfolio drawdown or a realized investor result.

Primary model tables use equal dates and equal sector/profile queries, Top3, at least five usable classified peers, and identical rows across each model comparison. Probabilistic calibration tables are row-weighted on the same predictions. The meta-labeler has usable mature out-of-time training only from 2022 onward, so its development slice is 2022–2023. Missing/Unclassified cohorts are not claimed to have validated predictive ranks.

## Noise floor and confidence

The 35 policies are reconstructed from fixed saved families: original score, nine high adjustments, six continuity/risk complements, fifteen SIP adjustments and four confirmation policies. They are highly related score policies, not 35 independent learners. A centered simultaneous circular calendar-block bootstrap preserves model/date/profile/sector dependence, with 4,000 draws and 365/730-day sensitivity. The development observed best IC gain is only 0.000259, versus a 95% maximum-selection floor near 0.010. The observed best attainment gain is 0.035pp, versus approximately 0.630pp. Such tiny earlier wins do not clear this conditional hurdle.

The exposed period is too short for a two-year-block estimate; that result is explicitly unavailable rather than a false zero uncertainty. Other model families require their own selection-noise calculation. For the corrected five-classifier family, the development attainment floor is about 6.3pp; the selected classifier's roughly 1.04pp development gain does not clear it. Four years of overlapping one-year outcomes still provide few independent temporal blocks, so these are conditional research hurdles, not guarantees.

{table(confidence[['period','retained','pair_accuracy','agreement','selected']])}

Pairs were sampled reproducibly within queries; model votes and stock rank dispersion were computed without outcomes. Development locked full coverage. The more attractive exposed-period selective curve was not used to change that choice.

## Hysteresis

Previous order is retained unless a crossing score gap exceeds the fixed margin. Candidate margins were 0, .0025, .005, .01 and .02. Development chose maximum Kendall stability subject to no more than .001 observed IC loss. Margin .02 won. It is a score margin, not a return threshold or a number of stock ranks.

{table(hys[hys.selected][['period','margin','raw_tau','kendall_tau','ic_delta']])}

The observed IC improvement is below the predictive noise floor and is not claimed as an accuracy gain. This validates an engineering candidate at historical snapshot frequency; daily shadow validation and profile/model-version state handling remain necessary before website activation.

## Goal probability and the validity correction

Labels are `future SIP XIRR >= target CAGR`; these agree with existing zero-shortfall labels on the panel. Each annual base learner uses outcomes ending strictly before January of test-year minus two. The disjoint calibration block starts at that date and includes only outcomes mature before the test-year January. The fixed model has 120 LightGBM trees / 15 leaves. This conservative split gives calibration an independent time block and leaves less recent data for base training than the incumbent ranker.

The initial unconstrained run was preserved and failed probability ordering: harder goals sometimes received greater success probability. A separate `monotone_round` constrains target CAGR downward and analog attainment upward; sigmoid slopes must be nonnegative. A negative fitted calibration slope becomes the optimum constant forecast under that constraint. This is a recorded mathematical-validity correction, not fresh validation or an exposed-period winner search. All five corrected models passed the 10/20/30-percent target-order check on 84,184 matched stock/date cases. Constant forecasts have undefined Spearman correlation; `constant_probability_ic_audit.csv` reports defined coverage and an explicitly disclosed zero-association convention. The raw IC column in the machine-readable classifier summary averages only defined correlations, so use the audit for full-period IC comparisons.

Development selected **{selected}** by goal attainment. Its exposed attainment gain is {100*(g.achievement-a.achievement):.3f}pp, while its average selected-stock drawdown deteriorates by {100*(a.drawdown-g.drawdown):.3f}pp. It fails the calibration/risk case for adoption.

{table(goal[['period','model','achievement','drawdown','selected']])}

{table(cal[['period','model','brier','log_loss','mean_probability','actual_frequency']])}

Climatology uses only the earlier calibration block's hit frequency. Lower Brier/log loss is better; even this simple forecast beats all corrected feature classifiers in the exposed period. Tree constraints enforce target direction but do not establish calibration under a changed market distribution. Target-rank changes are real in the research prototype, not fabricated personalization:

{table(changes)}

## New information inside the original ranking model

These are separate ablations of the existing **25% price ranking head**, using its original 180-tree balanced `rank_xendcg` recipe and strictly mature annual training. The remaining champion components, high overlay and SIP overlay stay fixed. The 70-feature control replays the original head; the volume, correlation-peer, look-alike and combined variants change only input columns. This avoids conflating new information with the classifier objective.

Development selects **{chosen_head}** by IC. All other fixed variants are diagnostics, not exposed-period selection candidates.

{table(head[['period','model','rank_ic','achievement','drawdown','selected']])}

{table(selected_noise)}

Volume features are 5/21-day abnormal volume, high-proximity interaction, volume trend, zero-volume fraction and median traded-value proxy. This is an adaptation of a hypothesis, not a replication of the [high-volume return-premium paper](https://doi.org/10.1111/0022-1082.00349). Daily inputs never extend beyond the decision date.

Peers are the 25 most correlated other stocks, using calendar-aligned daily returns and at least 200 overlapping observations. The features measure peer returns and own lag. 129,118 stock/dates have peer features, including 2,526 Unclassified stock/dates. The benchmark retains its sector evaluation; this does not validate replacing all sector groups or guarantee performance on small/Unclassified groups. It is a simple relation-feature adaptation, not a reproduction of [Hou's information-diffusion study](https://doi.org/10.1093/rfs/hhm003).

Look-alikes use PCA8 learned only from outcome-mature libraries, on 64 samples of normalized 252-observation paths. Fifty cosine neighbors supply matching-profile realized SIP return, attainment, dispersion and distance. Same-issuer matches are excluded. Each donor's outcome ends strictly before the query-year cutoff; overlapping donor paths are not independent observations. The 250 explainable current-snapshot examples use only donor outcomes ending before 3 October 2026 (latest endpoint 31 August 2026). They are examples, not live recommendations.

## Kronos feature extraction

Official [Kronos](https://github.com/shiyu-coder/Kronos) code and pinned mini/tokenizer weight revisions are recorded in `kronos_weight_receipt.json`. A hash-selected, outcome-independent 512-stock pilot yielded 14,723 usable windows. The final and mean hidden states are frozen; PCA16 is fitted only on each fold's training windows. Inputs are the last 252 OHLCV observations, with close times volume as a traded-value proxy. No weights are fine-tuned.

The matched original ranking-head comparison is the relevant feature test:

{table(kronos[['period','model','rank_ic','achievement','drawdown']])}

Kronos loses to its matched head on IC in both periods. The extra classifier-context experiment is also retained. A certified pretraining cutoff was not established; historical temporal contamination is a risk, so these tests cannot certify a clean foundation-model edge. Rejecting this extractor in this pilot does not prove that all price-history information is exhausted.

## SIP paths, metadata and verification

The path regression controls endpoint return with splines, plus sector/date fixed effects, then examines realized volatility, time underwater and recovery duration. It uses the existing base7500 whole-share outcomes and an independent monthly fractional-SIP simulation. Development whole-share volatility coefficient is +.0194 per standard deviation, with a year-cluster wild-bootstrap interval spanning zero; the fractional-SIP coefficient is -.0153 and also uncertain. Recovery duration is associated with SIP outcomes conditional on endpoint, but these are ex-post explanatory variables, not available future trading features. Only four development and two exposed year clusters exist; the intervals do not establish reliable significance.

The original `data/marketdata`, `data/company_facts` and `data/point_in_time` paths cannot be enumerated because their junction targets are unavailable. Recovered metadata contained 132 corporate actions with zero populated broadcast dates. Ex-dates do not establish filing dates. Filing frequency, gaps and lateness require the actual historical submission metadata, covered periods and applicable deadline definitions. No proxy was fabricated; that subtest is blocked.

Seven research unit tests cover bootstrap degeneracy, maximum-selection behavior, ties, hysteresis, metric parity and negative calibration-slope correction. Saved classifiers/calibrators independently replay within 1e-12 on 500 rows per goal round. Training/calibration endpoints and analog donor maturity are audited. The corrected CDF is checked across all matched target profiles. The original ranking-head control checks all annual saved scores. No full application suite or deployment validation is claimed, because application serving code and incumbent runtime are unchanged.

Reproduction uses `PYTHONPATH=src` and the existing CPU `.venv`; GPU extraction uses `.venv-gpu-research-20261011`. Clone the official Kronos code to `work/ten-hypotheses-20261031/Kronos` and check out code revision `67b630e67f6a18c9e9be918d9b4337c960db1e9a` before running its loader. Start with `ten_hypotheses_20261031.py prepare`, then feature build / peers / analogs / path, noise / confidence / hysteresis / meta / goal, the separate monotone wrapper, original-head ablations, and Kronos download / extraction / matched tests. `review_ten_hypotheses_20261031.py` verifies maturity, calibration ordering and serialized replay; this report compiler reads fixed results only. The huge input panels, histories and feature arrays remain local, with source hashes. Compact summaries, protocols, audits and source are suitable for version control.

Method references: [scikit-learn calibration and proper probability scores](https://scikit-learn.org/stable/modules/calibration.html), [LightGBM monotonic constraints](https://lightgbm.readthedocs.io/en/stable/Parameters.html#monotone_constraints). Framework documentation supports implementation choices; it is not evidence of Indian-stock forecasting performance.
'''
    source.write_text(text,encoding='utf-8');(OUT/'REPORT.md').write_text(text,encoding='utf-8')
    print('REPORT',source,flush=True)

if __name__=='__main__':main()
