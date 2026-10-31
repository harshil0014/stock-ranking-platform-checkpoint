# Review of the proposed checks: results and corrections

1 November 2026. Read-only audit; no new weights, candidates, training, registration or production changes. Descriptive name: **Long-history momentum lens (20%)**; historical model ID remains unchanged.

## Verdict

The criticism is mostly correct. The 20% lens passed only the separately registered retrospective **alignment/IC/selected-stock-drawdown point gate**. The older small-SIP-tilt stream froze a different candidate. Its global-XIRR limit was not part of the new selection gate; applying that investment standard to the 20% lens would reject it. Its development globalTop-20 mean SIP XIRR loss is 2.218 pp, which exceeds a 2 pp limit; that old stream also freezes a different candidate. Do not silently transfer or rewrite either protocol. No performance upgrade or production promotion is justified.

## Exposed results were recorded

| model | period | rank_ic | goal_hit_pct | selected_stock_drawdown_pct | alignment_percentile |
| --- | --- | --- | --- | --- | --- |
| active_champion | development | 0.0165 | 59.7389 | -25.5773 | 65.2637 |
| factor20_fixed | development | 0.0091 | 59.2099 | -25.9979 | 69.7074 |
| active_champion | exposed | 0.1384 | 22.1628 | -30.8544 | 57.6917 |
| factor20_fixed | exposed | 0.1349 | 23.7287 | -32.5238 | 64.5932 |

They are diagnostics only. Development IC falls about 45.2% relatively; describing that as a negligible accuracy cost would be misleading. The absolute loss is 0.00747. Exposed selected-stock drawdown worsens 1.67 pp; the positive exposed global portfolio XIRR difference rests on only 7/12 valid dates.

## The different champion numbers are different supports

| cohort | period | rank_ic | drawdown_pct |
| --- | --- | --- | --- |
| Original broad benchmark: nine profiles | development | 0.0223 | -25.3245 |
| Original broad benchmark: nine profiles | exposed | 0.1554 | -31.3776 |
| Original broad benchmark: base7500 | development | 0.0248 | -25.3049 |
| Original broad benchmark: base7500 | exposed | 0.1535 | -31.2985 |
| Long-history complete-factor: base7500 | development | 0.0165 | -25.5773 |
| Long-history complete-factor: base7500 | exposed | 0.1384 | -30.8544 |

The new table uses one profile, a stricter six-year-boundary/complete-factor universe, additional data guards, and family-wide matched Top-3 outcome availability. It is not the broad nine-profile cohort. The 2,396 eligible issuers are the current snapshot count, not a fixed historical membership list. The raw champion scoring rule is unchanged; its within-sector percentile is recomputed over the shared lens cohort.

## The repeated69.71 is a rounding coincidence

Old October 3 champion3-year-CAGR percentile: **69.709189617829**. New development lens five-factor alignment: **69.707387974798**. Both round 69.71, but they are different quantities. The latter was independently reconciled to the mean of five component summary values, not copied from the former.

## Correlation audit: nominal weights are not independent influence

Spearman correlations are calculated within sector/date on the complete eligible cohort, then equal-sector averages within date and equal-date averages within period. Constant or unsupported pairs are unavailable. These are descriptive dependency measures, not causal attribution.

| period | cohort | a | b | rho | queries | dates |
| --- | --- | --- | --- | --- | --- | --- |
| current | eligible | champion_percentile | factor20_fixed | 0.9884 | 50 | 1 |
| current | eligible | factor20_fixed | q_annual_consistency | 0.2506 | 50 | 1 |
| current | eligible | factor20_fixed | q_cagr3 | 0.4257 | 50 | 1 |
| current | eligible | factor20_fixed | q_cagr5 | 0.2654 | 50 | 1 |
| current | eligible | factor20_fixed | q_high_recency | 0.3673 | 50 | 1 |
| current | eligible | factor20_fixed | q_sip_profit | 0.4800 | 50 | 1 |
| development | eligible | champion_percentile | factor20_fixed | 0.9892 | 756 | 16 |
| development | eligible | factor20_fixed | q_annual_consistency | 0.3365 | 756 | 16 |
| development | eligible | factor20_fixed | q_cagr3 | 0.2707 | 756 | 16 |
| development | eligible | factor20_fixed | q_cagr5 | 0.3227 | 756 | 16 |
| development | eligible | factor20_fixed | q_high_recency | 0.2985 | 756 | 16 |
| development | eligible | factor20_fixed | q_sip_profit | 0.1961 | 756 | 16 |
| exposed | eligible | champion_percentile | factor20_fixed | 0.9850 | 579 | 12 |
| exposed | eligible | factor20_fixed | q_annual_consistency | 0.0402 | 579 | 12 |
| exposed | eligible | factor20_fixed | q_cagr3 | 0.1139 | 579 | 12 |
| exposed | eligible | factor20_fixed | q_cagr5 | 0.0210 | 579 | 12 |
| exposed | eligible | factor20_fixed | q_high_recency | 0.3478 | 579 | 12 |
| exposed | eligible | factor20_fixed | q_sip_profit | 0.1761 | 579 | 12 |

The full component-pair matrix is in factor_correlations.csv. Annual returns, CAGRs, SIP profit and recency overlap; the existing champion also contains price/high signals.20%is an explicit coefficient budget on normalized blocks, not20%independent information, turnover or predictive influence.

## Price level and cash-denominator audit

| period | cohort | a | b | rho | queries | dates |
| --- | --- | --- | --- | --- | --- | --- |
| current | before_factor_eligibility | full_budget_idle_cash_profit | log_nominal_price | 0.3839 | 53 | 1 |
| current | before_factor_eligibility | sip_invested_fraction | log_nominal_price | -0.9168 | 53 | 1 |
| current | before_factor_eligibility | sip_profit | full_budget_idle_cash_profit | 0.9930 | 53 | 1 |
| current | before_factor_eligibility | sip_profit | log_nominal_price | 0.3797 | 53 | 1 |
| current | before_factor_eligibility | sip_profit | log_provider_close | 0.3797 | 53 | 1 |
| current | eligible_lens | full_budget_idle_cash_profit | log_nominal_price | 0.3607 | 50 | 1 |
| current | eligible_lens | sip_invested_fraction | log_nominal_price | -0.9377 | 50 | 1 |
| current | eligible_lens | sip_profit | full_budget_idle_cash_profit | 0.9975 | 50 | 1 |
| current | eligible_lens | sip_profit | log_nominal_price | 0.3514 | 50 | 1 |
| current | eligible_lens | sip_profit | log_provider_close | 0.3514 | 50 | 1 |
| development | before_factor_eligibility | full_budget_idle_cash_profit | log_nominal_price | 0.1338 | 795 | 16 |
| development | before_factor_eligibility | sip_invested_fraction | log_nominal_price | -0.9250 | 796 | 16 |
| development | before_factor_eligibility | sip_profit | full_budget_idle_cash_profit | 0.9969 | 796 | 16 |
| development | before_factor_eligibility | sip_profit | log_nominal_price | 0.1413 | 795 | 16 |
| development | before_factor_eligibility | sip_profit | log_provider_close | 0.1176 | 795 | 16 |
| development | eligible_lens | full_budget_idle_cash_profit | log_nominal_price | 0.0981 | 756 | 16 |
| development | eligible_lens | sip_invested_fraction | log_nominal_price | -0.9335 | 756 | 16 |
| development | eligible_lens | sip_profit | full_budget_idle_cash_profit | 0.9966 | 756 | 16 |
| development | eligible_lens | sip_profit | log_nominal_price | 0.1070 | 756 | 16 |
| development | eligible_lens | sip_profit | log_provider_close | 0.0931 | 756 | 16 |
| exposed | before_factor_eligibility | full_budget_idle_cash_profit | log_nominal_price | 0.1971 | 627 | 12 |
| exposed | before_factor_eligibility | sip_invested_fraction | log_nominal_price | -0.9312 | 628 | 12 |
| exposed | before_factor_eligibility | sip_profit | full_budget_idle_cash_profit | 0.9949 | 627 | 12 |
| exposed | before_factor_eligibility | sip_profit | log_nominal_price | 0.2184 | 627 | 12 |
| exposed | before_factor_eligibility | sip_profit | log_provider_close | 0.2045 | 627 | 12 |
| exposed | eligible_lens | full_budget_idle_cash_profit | log_nominal_price | 0.1806 | 579 | 12 |
| exposed | eligible_lens | sip_invested_fraction | log_nominal_price | -0.9491 | 579 | 12 |
| exposed | eligible_lens | sip_profit | full_budget_idle_cash_profit | 0.9958 | 579 | 12 |
| exposed | eligible_lens | sip_profit | log_nominal_price | 0.2003 | 579 | 12 |
| exposed | eligible_lens | sip_profit | log_provider_close | 0.1883 | 579 | 12 |

The SIP factor is profit divided by actual invested capital, excluding unused cash. The audit compares it with log reconstructed nominal price and log provider split-adjusted Close. The zero-interest full-budget diagnostic equals stored profit times invested fraction; it retains unused cash without reinvesting it and is not XIRR. The>=50%investment-utilisation guard attenuates extreme unaffordability but cannot establish absence of price-level bias. Correlations do not identify a causal rounding effect. No score was changed to use this diagnostic.

## Missing history stays unavailable

| reason | count |
| --- | --- |
| missing_one_or_more_required_price_features | 1747 |
| missing_five_annual_returns | 1747 |
| missing_5-year_CAGR | 1652 |
| missing_SIP_profit | 1151 |
| known_SIP_action_block | 61 |
| investment_fraction_below_half_or_unknown | 1082 |
| inactive_or_missing_volume | 644 |
| stale_or_missing_positive_volume | 365 |
| unclassified | 132 |
| total_unavailable | 2040 |

Reason counts overlap. Missing price features combine insufficient history and known invalid adjustment windows; they do not all imply a recent IPO. Five completed annual returns need six year-end boundaries. No neutral imputation or per-stock weight redistribution is used. Other stocks retain the separate champion rank. Long-history survivors are a selected population; within-cohort comparison does not remove survivorship bias.

## Historical cutoffs: verified narrowly, not certified PIT

Independently replayed **56**historical feature cases across 28 decision dates, checking all five annual returns, 3-year/5-year CAGR and recorded-high age. Maximum difference from stored features: **0.0**. Replacing all later prices with an extreme value changed none of these features. Thus they were not calculated once from October 3 and pasted into historical rows.

Trailing SIP comes from dated archived simulations; the earlier full-source as-of audit is included in audit_receipt.json. We did not independently rebuild every historical SIP purchase here. Provider-price vintages, retrospective sectors and announcement-known corporate-action state are not independently point-in-time certified. Price-prefix correctness alone does not prove an investable historical pipeline.

## Additional execution-timing boundary

The price-feature function includes an observed close on the decision date. The existing fractional portfolio proxy starts its contribution schedule on that date and uses the first price on or after it, so it permits buying the same close on trading dates. There is no demonstrated forecast-issuance time that would make that fill executable. This is a code-path finding, not a measured estimate of the resulting bias. A fresh pipeline must enforce a first executable fill after forecast issuance; reproducing the old batch formula alone is insufficient. Historical results remain research proxies. Archived-date parity must also pin that date's model weights, preprocessor and universe. Applying current 2026 weights to 2020 inputs cannot be expected to reproduce an archived 2020 annual-fold model.

## What to take from the recommendations

Keep the current weights frozen and the production champion unchanged. Do not start a fresh holdout clock or silently replace the already registered small-tilt stream. A verified daily-input manifest, adjustment guards and archived-date end-to-end score parity are required before eligible shadow forecasts. Daily market prices need trading-session freshness;sector classifications and fundamental filings need their own availability/version policies rather than a blanket daily rule.

A98%coverage threshold is a design choice, not a number validated by these results;it cannot be silently applied to this 54%-coverage long-history lens. Keep one primary prospective comparison once inputs exist and report dependence/multiplicity. Running a scheduler off the laptop may be sensible, but it requires an actual host, credentials, resource budget and parity-tested implementation;no cloud deployment or spend was authorised by the pasted advice. No fresh pipeline or scheduler was created by this audit.
