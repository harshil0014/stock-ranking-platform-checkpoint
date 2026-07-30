# Signal evaluation methodology

Signals and labels are matched on observation date and ticker within the
manifest test range. Pearson IC and Spearman Rank IC are computed separately
for each observation date. Spearman uses average ranks. A date is valid only
with the configured minimum (at least two) usable observations and nonconstant
signal and label cross-sections.

The primary ICIR is always unannualized:

```text
ICIR = mean(valid IC) / sample_std(valid IC, ddof=1)
```

Rank ICIR uses the same convention. Daily frequency defaults to an
annualization factor of 252. Any explicit positive factor may be used and is
recorded. Weekly, monthly, irregular, synthetic, and unknown frequencies have
null annualized ICIR values unless a factor is explicitly supplied. A
date-typed column never establishes frequency.

Coverage for each date is usable matched observations divided by label
observations. Missing predictions stay visible through the outer join.
Comparisons require the same evaluation protocol fingerprint: label definition
and fingerprint, chronological boundaries, purge/embargo, frequency, metric
conventions, annualization, minimum observations, and test-universe policy.
Model configurations and model-specific datasets remain independently
fingerprinted and may differ.

Synthetic evaluation output is a contract test, not trained performance,
portfolio performance, investment evidence, or advice.
