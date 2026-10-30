# Extra high-age weight: agreement with professor-style ranking

Development-selected candidate: `near_high_age_0.001`. Website unchanged.

Same 3,164 matched stocks across 53 sectors; finite professor-style SIP profit, no action block, known sector and at least five peers. Sector statistics receive equal weight. Fixed ISIN tie-breaking for Top 5. The excluded 1,272 names are not assigned invented professor ranks.

This uses the preserved professor-style SIP profit calculation, not a fresh calculation from the original Excel/Google Finance sheet. Similarity is not investment accuracy or future performance. Rankings use the frozen October 3 snapshot and default profile.

| Variant | Spearman | Kendall | Top 5 overlap | Change in Spearman |
|---|---:|---:|---:|---:|
| current_champion | 0.467385107 | 0.348502406 | 33.58491% | +0.000000000 |
| dual_age_0.001 | 0.468721435 | 0.349675202 | 33.58491% | +0.001336328 |
| dual_age_0.002 | 0.469033898 | 0.350167626 | 33.58491% | +0.001648791 |
| dual_age_0.004 | 0.469355168 | 0.350497784 | 33.58491% | +0.001970062 |
| dual_age_0.008 | 0.470448772 | 0.351250153 | 33.58491% | +0.003063665 |
| near_high_age_0.001 | 0.467440874 | 0.348566538 | 33.58491% | +0.000055767 |
| near_high_age_0.002 | 0.468030335 | 0.349189861 | 33.58491% | +0.000645228 |
| near_high_age_0.004 | 0.468164419 | 0.349356289 | 33.58491% | +0.000779313 |
| near_high_age_0.008 | 0.468492942 | 0.349608277 | 33.58491% | +0.001107835 |
| recorded_age_0.001 | 0.468232748 | 0.349288100 | 33.58491% | +0.000847642 |
| recorded_age_0.002 | 0.468912900 | 0.350041510 | 33.58491% | +0.001527793 |
| recorded_age_0.004 | 0.469074766 | 0.350003640 | 33.58491% | +0.001689659 |
| recorded_age_0.008 | 0.469389800 | 0.350050566 | 33.58491% | +0.002004694 |
| rolling_age_0.001 | 0.468803880 | 0.349799610 | 33.58491% | +0.001418774 |
| rolling_age_0.002 | 0.468821954 | 0.349826973 | 33.58491% | +0.001436848 |
| rolling_age_0.004 | 0.469451251 | 0.350328748 | 33.58491% | +0.002066145 |
| rolling_age_0.008 | 0.470532475 | 0.351221673 | 33.58491% | +0.003147368 |

Selected candidate sector correlation changes: {'improved': 6, 'unchanged': 45, 'worsened': 2}.

Baseline correlation and 89/265 Top 5 shared slots reproduce the earlier audit. All 16 variants are shown descriptively; none is newly selected using this comparison. Five-stock sectors necessarily have 100% Top 5 overlap.

Source SHA256: ca5e4983d49be0f14fa67efce9bee57cc1f8832c5ccd144f6de04879bdcb4277
