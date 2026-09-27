# Personalized sector ranking

The active Personalized product uses the frozen `d4995807163bef1ec4b297179e6c54a59c71f390` 67% Goal / 33% LightGBM LambdaRank champion. Sector ranks are a view of its existing final overall order. No sector data enters the champion prediction or blend.

## Rank contract

For each supported profile, the service first obtains the champion's overall score and unique overall rank. Within each canonical product sector, it orders only genuine Personalized rows by that overall rank and assigns consecutive `personalized_sector_rank` values from 1. `personalized_sector_peer_count` counts only genuine Personalized securities in that sector. `sector_security_count` counts all accepted product securities in the sector, including fallbacks. Search and sector filtering only change displayed rows; ranks and peer counts remain fixed for the full profile and product universe.

Every row exposes `sector`, classification source, method, and confidence. The API retains `baseline_rank` for compatibility and adds the explicit `baseline_sector_rank` and `baseline_score`. A Baseline sector rank is a separate Complete Universe rank and must never be read as a Personalized position. Fallback rows have `personalized_available=false`, `result_type=PRODUCT_FALLBACK`, and null Personalized overall rank, sector rank, and score. They retain their sector, Baseline sector rank and score, blocker, and the count of genuine Personalized sector peers.

An execution row with no complete champion score is explicitly labelled `PERSONALIZED_SCORE_UNAVAILABLE`; its underlying execution status remains in `execution_status`. A security outside the frozen lookback cohort is labelled `OUTSIDE_FROZEN_LOOKBACK_COHORT`. Neither receives a Personalized position.

## Classification evidence

The accepted product has 4,436 distinct ISINs and tickers, each with a nonblank sector. There are 58 sectors. The product's accepted Screener market-wide export provides 4,305 observed sector assignments by exact ISIN. The completion layer assigns 131 sectors without an observed product sector: 28 moderate confidence, 82 low confidence, and 21 very low confidence. The completion method is recorded per row. These 131 assignments should not be presented as verified observed taxonomy. The 21 very-low-confidence rows use a disclosed `Diversified` fallback because no sufficiently precise accepted taxonomy signal was found. Ten of them do have a broad Yahoo-derived sector, which does not identify a unique product sector, so the completion layer does not silently promote it. Official, secondary, Yahoo, prospectus, and other company evidence remains available in the company facts and provenance views; it is not used to replace the 4,305 accepted exact-ISIN Screener sectors.

## Verification

`research/runners/audit_personalized_sectors.py` independently reads the completion sector and raw champion results, then checks every returned identity, sector, genuine rank, fallback, peer count, Baseline rank, score, and global rank continuity. It runs nine profiles spanning contribution amount, 12/36/60-month lookback, 7/30/90-day contribution intervals, and 10/20/30% target CAGR at the supported 12-month horizon. It verifies all nine frozen reference profiles directly against the sealed champion. The existing product acceptance runner exercises 162 profiles, deterministic repeats, sequential changes, concurrency, and invalid inputs. The browser runner checks visible columns, Inspect, alias search, sector filtering, fallbacks, profile changes, narrow layout, and browser errors.

Across the nine independent profiles, the oracle checks 39,924 memberships, 27,392 genuine sector positions, and 12,532 fallbacks, with no discrepancy. The default profile yields 3,265 genuine results and 1,171 fallbacks. At the same default settings, changing amount to ₹1,000 produces 3,260 genuine results and to ₹50,000 produces 3,264. A 12-month lookback produces 3,747; 60 months produces 2,866. A seven-day interval produces 1,197 because its denser execution schedule exposes more missing execution dates; 90 days produces 3,263. Changing target CAGR to 10% or 30% keeps availability at 3,265 while changing the Goal component and ordering. These counts come from the current frozen evidence and can change only with a different accepted data state or supported profile.

The independent audit also compares the current default-profile result to a previously recorded Sir 14-security global order in `compare_sir_14_current_reference.py`. This is descriptive agreement only. The attached copy of OK Strategy v4.3 has 14 explicit SIP rank formulas but no cached SIP rank or SIP profit/loss values. Its cached CAGR fields can be compared as separate evidence, not as the missing SIP rank. The workbook is dated 2026-08-21; the current product prediction is as of 2026-09-18. Only 12 of the 14 identities have genuine Personalized output under the default profile. The two fallbacks remain in the product and are excluded from Personalized rank agreement.

On those 12 comparable identities, the previously recorded Sir order and Personalized overall order agree on 45/66 pairs (68.18%), with Spearman 0.497 and 3/5 top-five overlap. The only Sir sector with at least two genuinely Personalized members is Electrical Equipment; its three pairwise comparisons all agree. The 3-year and 5-year CAGR caches on the SIP worksheet each cover 11 genuine names; their pairwise agreements with Personalized are 26/55 and 30/55 respectively. These CAGR columns have different meaning from the champion score, and the workbook contains no usable SIP rank cache in this copy. The 14 requested identities, positions, and reasons for fallback are recorded row by row in the audit JSON.

| Workbook cached field | Comparable genuine names | Pairwise agreement | Spearman |
| --- | ---: | ---: | ---: |
| SIP 3-year CAGR | 11 | 26/55 | 0.009 |
| SIP 5-year CAGR | 11 | 30/55 | 0.209 |
| SIP 10-year CAGR | 9 | 23/36 | 0.400 |
| CAGR-sheet 1-year CAGR | 5 | 7/10 | 0.500 |
| CAGR-sheet 3-year CAGR | 5 | 2/10 | -0.700 |
| CAGR-sheet 5-year CAGR | 5 | 7/10 | 0.400 |
| CAGR-sheet 10-year CAGR | 5 | 6/10 | 0.300 |

Top-five overlap for five-name comparisons is omitted because it is mechanically 100%. These field comparisons are diagnostic, not targets for the champion.

Machine-readable results are in `data/analysis/personalized_sector_audit_20260927.json`, `data/analysis/personalized_sector_browser_20260927.json`, and `data/analysis/personalized_sector_runtime_provenance_20260927.json`.

The runtime pack remains the original audited 98,546,546-byte artifact with SHA-256 `515eac8ffc555a571406a4a41f9d931a016cb6280871a3d89f59846d2692ed0c`. The versioned specification and strict single-hash loader match main. Sector ranking does not change the pack, frozen model, or historical evidence. The `_calculate` AST is identical to main. Each of the nine complete sector-audit response row fingerprints is identical to the earlier sector run, and all nine frozen champion profiles reproduce their sealed outputs to at most `7.11e-15`. The original pack is mounted outside Git; this task does not deploy.
