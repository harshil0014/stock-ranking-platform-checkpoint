"""Read-only analyst review of the frozen Closing High default shortlist."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research/reports/top100-human-review-20261004'
RANKS=ROOT/'experiments/v17-peak-confirmation-20261004/current_rankings.csv.gz'
FACTS=ROOT/'experiments/current-data-recovery-20261003/current_company_facts_recovered_v7_full_yahoo.csv.gz'

# Analyst-written questions/judgments. These are not fitted labels or a new score.
NOTES='''MWL|Challenge placement|A recent high supports a trend shortlist, but number one needs stronger evidence: modest scale, reported debt/equity 0.79, cash conversion 0.48 and promoter pledge 22.85%. Check working capital and historical trading lots.
ANANDRATHI|Valuation sensitive|High reported ROCE supports business quality; a 78.89x P/E makes number two dependent on sustained earnings growth. Capital-market sensitivity and promoter pledge deserve attention.
BSE-543373|Verify before use|Number three combines debt/equity 2.38 with negative operating cash flow. Recent price strength does not resolve financing and working-capital risk; verify trade-to-trade execution.
LAURUSLABS|Valuation sensitive|Strong cash conversion and recent high are coherent, but 95.06x P/E demands a successful earnings and capacity ramp. Review capital expenditure and concentration with other pharma names.
DIVISLAB|Valuation sensitive|Zero reported debt and cash conversion around one support inclusion; 81.85x P/E leaves substantial valuation risk even with low downside volatility.
BSE-543953|Verify before use|ROCE 34.79% and P/E 18.09x look attractive on the snapshot, but negative operating cash flow and SME-series evidence require inventory and lot-size checks before treating rank six as investable.
IPCALAB|Plausible candidate|P/E 35.67x, debt/equity 0.10 and cash conversion 0.97 make its high-ranking trend more financially coherent than many expensive peers. Regulatory and integration evidence still needs checking.
SJS|Plausible candidate|ROCE 28.58%, low debt and cash conversion 1.32 support the shortlist. Its 15.69% distance below ATH and limited model history temper confidence in exact rank eight.
BSE-540718|Verify before use|Very low measured downside volatility is not business safety. P/E 245.92x, negative cash flow, an old textile classification and changed business identity require reconciliation before accepting rank nine.
SHYAMMETL|Plausible candidate|Low reported debt and cash conversion 1.89 support inclusion; ROCE 13.01% and metal-cycle exposure argue against interpreting its recent high as a durable quality ranking.
SHRIPISTON|Plausible candidate|ROCE 20.78% and cash conversion 1.11 support its position; assess debt/equity 0.68 and the relevance of older auto-component history to the current business mix.
STEELCAS|Plausible candidate|ROCE 32.30%, zero reported debt and cash conversion near one support the breakout. Model history is under five years, so longer operating history must be reconciled separately.
APOLLOHOSP|Valuation sensitive|Recent strength and cash conversion 1.53 support a hospital candidate. P/E 59.37x and debt/equity 0.90 require a capacity-ramp and financing review.
KINGFA|Cash-flow review|ROCE 23.20% and very low debt support the fresh high; cash conversion 0.36 is the main challenge. Verify receivables and inventory before treating the breakout as fully confirmed.
PTCIL|Challenge placement|P/E 269.82x, ROCE 8.43% and negative operating cash flow make rank fifteen a future-execution bet. Aerospace investment can explain weak current ratios but cannot make valuation risk disappear.
NAVINFLUOR|Valuation sensitive|Cash conversion 1.38 and ROCE 20.96% support the recovery. At 53.17x P/E, commissioning and earnings delivery matter more than a 22-day-old high alone.
YATHARTH|Short-history review|Only 37.82 months of model history and ROCE 12.37% limit confidence in exact rank seventeen. P/E 52.07x and promoter pledge 9.59% merit expansion and financing checks.
RRKABEL|Short-history review|ROCE 28.10% supports the business case, but 36.37 months of history barely covers the selected lookback. P/E 44.01x and cash conversion 0.59 warrant a working-capital review.
FEDERALBNK|Plausible candidate|A long price record and moderate P/E support consideration. Evaluate capital adequacy, asset quality and credit costs; industrial debt/equity and ROCE cutoffs are unsuitable for this bank.
TMB|Short-history review|P/E 9.62x offers a different valuation profile from much of the Top20, but model history is under five years. Bank-specific asset quality and capital measures are needed, not a generic negative-CFO veto.
CRAFTSMAN|Valuation sensitive|P/E 62.90x with ROCE 13.91% and debt/equity 1.11 makes its place dependent on integration and capital returns. Cash conversion 1.36 is a useful counterweight.
TITAN|Valuation sensitive|Price strength and positive cash conversion fit the shortlist, but P/E 73.85x and debt/equity 1.95 need business-specific inventory/funding analysis rather than a low-volatility quality assumption.
NUVAMA|Verify before use|Reported promoter pledge 62.80% and only 36.17 months of model history are material review points. Its financial-services balance sheet makes generic CFO/debt filters misleading.
AETHER|Valuation sensitive|P/E 87.95x alongside ROCE 11.92% and cash conversion 0.63 makes this a demanding earnings-ramp case. A six-day-old high is insufficient confirmation of operating returns.
RAMRAT|Cash-flow review|A fresh high and ROCE 23.58% support momentum, while negative CFO and debt/equity 1.17 raise working-capital and funding questions.
SANSERA|Valuation sensitive|P/E 69.47x versus ROCE 13.69% requires strong future delivery. Low debt and cash conversion around one support keeping it under review rather than rejecting solely on valuation.
GLENMARK|Plausible candidate|P/E 21.50x, high reported ROCE and positive cash conversion look coherent. Check whether earnings and capital-return figures include disposals or other nonrecurring effects.
TORNTPHARM|Valuation sensitive|P/E 82.52x and debt/equity 1.79 merit acquisition and funding scrutiny even though price momentum and operating cash conversion are supportive.
GHCLTEXTIL|Short-history review|Low P/E 11.81x is offset by ROCE 5.75% and cash conversion 0.07. A roughly 40-month record and demerger context call for operating-history reconciliation.
PAYTM|Challenge placement|P/E 136.87x, ROCE 4.96% and negative operating cash flow mean recovery momentum is not yet equivalent to durable earning power. Inspect profitability quality and the lifetime-high definition.
RADICO|Valuation sensitive|ROCE 24.15% and positive cash conversion support quality, but 81.93x P/E leaves little room for weaker growth. Verify normalized earnings and sector-specific policy sensitivity.
WELCORP|Plausible candidate|P/E 27.58x, ROCE 22.89% and cash conversion 1.99 align better with the price signal. Check order conversion and metal-cycle dependence; professor-list agreement is descriptive evidence only.
SWARAJ|Verify before use|Moderate P/E does not settle negative CFO, debt/equity 0.96 and BE-series execution questions. Verify current board status and historical lot requirements instead of using a blanket SME label.
BSE-543920|Verify before use|P/E 52.25x and negative CFO require order-to-cash review. Recent mainboard migration means current and historical execution rules must be treated separately.
PRUDENT|Valuation sensitive|ROCE 37.48%, low debt and cash conversion 0.98 make it a coherent candidate. P/E 54.52x and exposure to capital-market flows remain relevant risks.
ALIVUS|Plausible candidate|P/E 26.74x, ROCE 23.79%, low debt and cash conversion 1.03 support inclusion. Trace the name change and ensure history belongs to the same economic business.
AARTIPHARM|Short-history review|Only 44.02 months of model history and ROCE 10.70% temper the near-ATH signal. Positive cash conversion helps; promoter pledge 11.08% and expansion returns deserve review.
PRIVISCL|Plausible candidate|ROCE 22.30% and cash conversion 1.68 support its position. Debt/equity 0.72 and chemicals-cycle exposure matter even with an ATH gap of only 4.47%.
AUBANK|Plausible candidate|Recent price recovery merits review, but bank asset quality, funding and credit costs are the appropriate tests. Do not penalize bank leverage using an industrial threshold.
MARICO|Valuation sensitive|ROCE 47.05% and cash conversion 1.19 support a quality interpretation. P/E 54.41x means business durability and expected returns still need separate judgments.
JSWSTEEL|Cycle review|P/E 24.94x and a recent high can conceal cyclical earnings risk. ROCE 10.96%, debt/equity 0.99 and reported pledge 11.60% warrant balance-sheet and cycle review.
SANGAMIND|Cycle review|Positive cash conversion supports the fresh high; ROCE 10.67% and debt/equity 1.14 leave textile-cycle and funding sensitivity.
INDOBORAX|Verify before use|The snapshot reports 100% of promoter holdings pledged. Verify acquisition-financing documents and pledge terms; zero company debt is not proof of zero promoter-level risk.
ABSLAMC|Plausible candidate|ROCE 32.23%, low debt and P/E 30x support the shortlist. Earnings sensitivity to flows and market levels must be considered alongside its 100-day ATH age.
VIJAYA|Valuation sensitive|Positive cash conversion and ROCE 20.53% support the diagnostics franchise; P/E 78.79x requires strong volume and expansion economics.
VISHNU|Plausible candidate|P/E 30.52x and positive cash conversion broadly fit the trend. Check chemical-cycle margins and debt/equity 0.49 before assigning durable-quality status.
ACUTAAS|Valuation sensitive|ROCE 31.56% and low debt are supportive, but P/E 69.45x needs sustained earnings delivery. Check identity continuity after the name change and overlapping pharma exposure.
GRASIM|Challenge placement|ROCE 8.01%, debt/equity 2.20 and negative CFO complicate this momentum selection. Conglomerate structure and expansion spending need segment-level interpretation.
AJANTPHARM|Plausible candidate|High ROCE and low debt support inclusion; cash conversion 0.47 and promoter pledge 22.53% are concrete checks that the price score does not settle.
DYNAMATECH|Valuation sensitive|P/E 140.12x with ROCE 10.21% is a demanding valuation despite a fresh high. Positive cash flow helps, but execution and capital returns need independent confirmation.
JSWINFRA|Short-history review|At 35.94 months, model history is slightly shorter than the 36-month user lookback. Review terminal assumptions and port expansion economics before accepting apparent precision.
MINDACORP|Plausible candidate|Positive cash conversion 1.90 supports the signal; ROCE 12.67% versus P/E 40.87x calls for evidence of improving capital returns.
GRANULES|Plausible candidate|P/E 33.35x and cash conversion 1.31 broadly support inclusion. Regulatory execution and product margins remain outside the observed high-price score.
BSE-539546|Verify before use|Changed name/business, P/E 83.35x, ROCE 5.52% and negative CFO require fresh economic-history analysis. A decade of ticker prices is not a decade of the current business.
BSE-531676|Verify before use|P/E 331.84x, ROCE 8.48% and XT-series evidence need identity, financial and execution checks. Long price history should not automatically confer high economic confidence.
BSE-538546|Execution review|P/E 17.91x, ROCE 34.40% and low debt are supportive. Small reported market capitalization makes spread, depth and trade-size evidence important despite passing volume screens.
AUROPHARMA|Plausible candidate|Moderate P/E 25.40x and cash conversion 1.55 support inclusion; promoter pledge 13.75% and regulatory/manufacturing risks remain relevant.
STYLAMIND|Plausible candidate|ROCE 26.58%, low debt and cash conversion 1.22 make a coherent financial cross-check. Exact rank still depends strongly on the recent-high preference.
RATNAVEER|Short-history review|A new high after 36.67 months of model history is not broad-cycle evidence. Negative CFO and ROCE 12.29% merit working-capital review.
KIMS|Valuation sensitive|P/E 154.56x, ROCE 9.50% and debt/equity 1.89 are substantial challenges. Expansion can explain weak current returns but must be verified rather than excused by momentum.
LLOYDSME|Short-history review|Only 38.51 months of usable model history for a mining/metals name is a coverage limitation, not company age. Debt/equity 1.49 makes cycle and capex scrutiny necessary.
SUNPHARMA|Plausible candidate|P/E 34.81x, low debt and cash conversion near one fit a more balanced shortlist candidate. Check pharma concentration and product/regulatory exposure.
SONACOMS|Valuation sensitive|P/E 63.48x with ROCE 15.11% requires sustained growth. Low debt supports resilience but does not prove valuation protection.
AVALON|Valuation sensitive|P/E 108.95x, cash conversion 0.51 and only 41.46 months of history make this a growth-execution case with high model downside volatility.
BSE-539682|Verify before use|A recent business transformation means historical price continuity overstates continuity of the present operating business. Reconcile predecessor history and the current software classification.
WELSPUNLIV|Valuation sensitive|P/E 68.74x versus ROCE 6.26% makes the fresh high financially demanding. High reported cash conversion can reflect working-capital release and needs normalization.
NRBBEARING|Plausible candidate|ROCE 18.41% and cash conversion 1.64 support the new high; promoter pledge 14.99% remains a financing review item.
ADANIPORTS|Plausible candidate|P/E 29.67x and cash conversion 1.57 support a trend candidate. Evaluate concession, acquisition, group and financing exposure separately from smooth price behavior.
SHRIRAMFIN|Plausible candidate|Use credit costs, asset quality and capital adequacy to assess this lender. Its negative CFO and debt/equity are not directly comparable with manufacturers.
NITINSPIN|Cycle review|P/E 16.98x and cash conversion 2.31 provide support, but ROCE 12.21% and textile-cycle sensitivity limit a simple quality interpretation.
BOSCHLTD|Valuation sensitive|Strong balance-sheet indicators support inclusion, while P/E 58.79x requires growth and capital-allocation scrutiny despite lower measured downside volatility.
MANORAMA|Plausible candidate|ROCE 35.41% and cash conversion 1.11 support the financial case. Check whether the roughly 51-month model record and P/E 48.32x capture enough operating cycles.
PHOENIXLTD|Valuation sensitive|Cash conversion 1.95 supports the operating picture; P/E 50.48x should be supplemented by asset values, occupancy and project-level capital returns.
KPIL|Plausible candidate|P/E 21.28x and cash conversion 1.57 support inclusion. Contractor receivables, order execution and promoter pledge 24.55% require review.
ABCAPITAL|Sector-specific review|A financial conglomerate needs segment-specific valuation and capital adequacy. Generic negative CFO and leverage screens would be misleading.
VTL|Cycle review|Moderate P/E and positive cash conversion support consideration, while ROCE 8.55% signals the need to evaluate textile-cycle returns through a full cycle.
BSE-543616|Verify before use|Moderate P/E and ROCE support further work, but SME-series evidence, limited price history and cash conversion 0.25 make trading lots and receivables necessary checks.
CAPLIPOINT|Plausible candidate|P/E 29.48x, ROCE 24.24% and low debt support inclusion. Product/geographic concentration and cash conversion below one still warrant review.
SOLARINDS|Valuation sensitive|ROCE 38.08% supports operating quality, but P/E 87.40x and cash conversion 0.36 make growth expectations and working capital material.
MAYURUNIQ|Plausible candidate|P/E 15.62x, ROCE 24.47% and very low debt provide a financial counterweight to its weaker ATH proximity. Investigate why cheaper profitable names fall below expensive recent breakouts.
CCL|Plausible candidate|Positive cash conversion 2.21 supports the signal; debt/equity 0.56 and commodity/input sensitivity still need consideration.
NEULANDLAB|Valuation sensitive|ROCE 26.47% and cash conversion 0.96 support its position. P/E 58.47x makes earnings durability and customer/product concentration important.
MEDANTA|Short-history review|A roughly 46-month record with P/E 66.59x requires expansion-ramp evidence. Positive cash conversion supports inclusion but does not establish mature-cycle resilience.
SGIL|Challenge placement|Missing P/E, debt/equity 2.25, ROCE 9.24% and high measured downside volatility justify a loss/funding review before accepting the near-high signal.
SPORTKING|Cycle review|P/E 15.86x and strong cash conversion support consideration; the model has only 49.25 months of history and textile-cycle risk remains.
APLAPOLLO|Plausible candidate|ROCE 31.75%, low debt and cash conversion 1.74 support inclusion despite the Top100's oldest ATH at 232 days. A near-old-high recovery should not be dismissed mechanically.
MANGLMCEM|Cycle review|P/E 21.10x is reasonable within this shortlist, but ROCE 10.99%, debt/equity 0.91 and cash conversion 0.63 call for cement-cycle review.
SYRMA|Valuation sensitive|P/E 78.31x, ROCE 16.78% and a roughly 49-month model history make the new high dependent on growth execution and working capital.
LUMAXTECH|Plausible candidate|ROCE 21.19% and cash conversion 1.62 support professor/model overlap. Debt/equity 1.02 and relatively high downside volatility justify a more cautious placement than profit sorting alone.
NESTLEIND|Valuation sensitive|ROCE 84.14%, low debt and strong cash conversion support business quality; P/E 69.65x still demands a valuation judgment independent of price strength.
HINDALCO|Cycle review|P/E 10.36x gives valuation contrast to the shortlist, while debt/equity 0.73 and cash conversion 0.61 require cycle, project and capital-allocation analysis.
ENDURANCE|Plausible candidate|Positive cash conversion 1.98, moderate debt and long history support inclusion. Auto-cycle and customer exposure need separate assessment.
MCX|Valuation sensitive|High reported ROCE and cash conversion support franchise economics, but P/E 52.51x requires normalized transaction volumes and operating earnings.
VSSL|Plausible candidate|Low reported debt, P/E 26.32x and cash conversion 0.88 broadly fit the trend. Steel-cycle earnings and customer concentration remain the relevant operating checks.
MANAPPURAM|Sector-specific review|Assess gold-loan and other credit exposures, asset quality and capital adequacy. Negative cash flow alone is not a valid lender exclusion.
BHEL|Valuation sensitive|P/E 59.31x versus ROCE 9.14% requires evidence that orders convert to profitable cash flows. A recent high cannot independently validate a turnaround.
BHARATFORG|Valuation sensitive|P/E 88.95x and ROCE 12.61% are demanding despite positive cash conversion. Review segment returns and the effect of expansion or weak-cycle earnings.
ZYDUSWELL|Valuation sensitive|P/E 79x with ROCE 4.91% is a major valuation/earnings-quality question. A relatively smooth chart does not resolve weak current capital returns.
TI|Cash-flow review|Negative CFO, debt/equity 0.77 and promoter pledge 12.40% challenge the recent-high selection. Review transaction/integration and working-capital effects.
COFORGE|Plausible candidate|P/E 40.97x, ROCE 23.50%, low debt and cash conversion 1.05 broadly support inclusion. Delivery and client concentration risks remain outside price confirmation.'''

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    ranks=pd.read_csv(RANKS,low_memory=False)
    base=ranks[ranks.profile_name.eq('base7500')].copy()
    facts=pd.read_csv(FACTS,low_memory=False)
    cols=['isin','product_sector','product_industry','series','primary_exchange','listing_date','trade_date',
          'screener_market_cap_crore','screener_pe_ratio','screener_roce_pct','screener_debt_to_equity',
          'screener_cash_conversion_quality','screener_operating_cash_flow_crore','screener_profit_after_tax_crore',
          'screener_pledged_pct','screener_source_observed_at','screener_fresh_export_observed_at',
          'screener_last_annual_result_date','product_classification_source']
    base=base.merge(facts[cols],on='isin',validate='one_to_one')
    top=base[base.new_rank.le(100)].sort_values('new_rank').copy()
    notes=pd.DataFrame([line.split('|',2) for line in NOTES.splitlines()],columns=['ticker','analyst_assessment','analyst_note'])
    assert len(notes)==100 and not notes.ticker.duplicated().any()
    top=top.merge(notes,on='ticker',validate='one_to_one')
    assert len(top)==100 and top.analyst_note.notna().all()
    financial=top.product_sector.isin(['Banks','Finance','Capital Markets','Financial Technology (Fintech)'])
    flags={
      'pe_above_60':top.screener_pe_ratio.gt(60),
      'negative_cfo_nonfinancial':top.screener_operating_cash_flow_crore.lt(0)&~financial,
      'debt_equity_above_1_nonfinancial':top.screener_debt_to_equity.gt(1)&~financial,
      'pledge_above_20':top.screener_pledged_pct.gt(20),
      'model_history_under_60_months':top.history_months.lt(60),
      'model_history_under_36_months':top.history_months.lt(36),
      'bse_M_series_in_snapshot':top.primary_exchange.eq('BSE')&top.series.eq('M'),
      'recent_7day_high':top.days_since_recorded_high.le(7),
      'downside_volatility_above_30pct':top.downside_volatility_1y.gt(.30),
    }
    for key,values in flags.items():top[key]=values
    top['review_flags']=top.apply(lambda row:'; '.join(key for key in flags if row[key]),axis=1)
    top['review_basis']='Snapshot desktop review; financial fields are source observations, not independently audited accounts'
    keep=['new_rank','ticker','company','isin','product_sector','series','analyst_assessment','analyst_note','review_flags',
          'days_since_recorded_high','distance_from_recorded_high','days_since_52w_closing_high','history_months',
          'evidence_confidence','downside_volatility_1y','volume_active_fraction','median_daily_value',
          'winner_rank','priority_rank','new_score']+[c for c in cols if c not in ['isin','product_sector','series']]
    top[keep].to_csv(OUT/'top100_stock_by_stock_review.csv',index=False,encoding='utf-8-sig')
    sector=[]
    eligible=base[base.activity_eligible]
    for name,g in top.groupby('product_sector'):
        sector.append({'sector':name,'top20_count':int(g.new_rank.le(20).sum()),'top100_count':len(g),
                       'eligible_universe_count':int(eligible.product_sector.eq(name).sum()),
                       'top100_share':len(g)/100,'eligible_share':float(eligible.product_sector.eq(name).mean())})
    sectors=pd.DataFrame(sector).sort_values('top100_count',ascending=False)
    sectors['representation_ratio']=sectors.top100_share/sectors.eligible_share
    sectors.to_csv(OUT/'sector_concentration.csv',index=False)
    summary={'snapshot':'2026-10-03','review_date':'2026-10-04','profile':'base7500','top100_rows':len(top),
             'eligible_universe':len(eligible),'flag_counts':{key:int(val.sum()) for key,val in flags.items()},
             'assessment_counts':top.analyst_assessment.value_counts().to_dict(),
             'median_pe':float(top.screener_pe_ratio.median()),'pe_available':int(top.screener_pe_ratio.notna().sum()),
             'healthcare_combined':int(top.product_sector.isin(['Healthcare Services','Pharmaceuticals & Biotechnology']).sum()),
             'oldest_top100_ath_days':float(top.days_since_recorded_high.max()),
             'flag_interpretation':'Attention thresholds chosen for this review, not validated exclusion rules or a new ranking.',
             'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [RANKS,FACTS]}}
    (OUT/'top100_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    lines=['# Every Top100 stock reviewed','',
      'Default profile: Rs7,500 every 30 days, 36-month lookback. Ranking snapshot 3 October 2026; review 4 October 2026.',
      'These are analyst judgments about ranking plausibility and next diligence questions, not return predictions or replacement ranks. All 100 received a snapshot financial, history and trading review. Targeted primary-source investigation is in company_due_diligence.md; it is not claimed for every row. Ratios below come from the frozen Screener-derived fields and can differ in date, basis and quality. Bank/finance cash flow and leverage are not judged with industrial cutoffs.',
      '', '| Rank | Stock | Assessment | Analyst reasoning |','|---:|---|---|---|']
    for r in top.itertuples():lines.append(f'| {r.new_rank:.0f} | {r.ticker} | {r.analyst_assessment} | {r.analyst_note} |')
    (OUT/'top100_stock_by_stock_review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':run()
