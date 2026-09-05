# Baseline eligibility reconciliation

The counts **499** and **1,237** are not before/after measurements of one
eligibility contract. They are two explicitly different product views:

- The live bundle's 499 rows are the strict official NSE Indices-classified
  cohort. Its historical adapter retains the accepted terminal-price check of
  ₹0.05 absolute or 0.01% relative difference from the official NSE close.
- The current company-facts/product view has 1,237 eligible rows. It retains
  the strict 499 and adds exact-identity securities under Product
  Classification v1. Its separately documented continuity check is 2%.

The rebuilt company-facts snapshot did not remove 738 securities. All 499
strict rows occur in the 1,237 product rows; the other 738 belong only to the
expanded product cohort (669 exact-identity secondary classifications and 69
official classifications).

There was a separate real change inside the strict cohort between the accepted
19 August and 21 August snapshots: 568 became 499. Seventy securities failed
the unchanged `CURRENT_PRICE_MISMATCH` gate and CARTRADE became eligible. This
is a quality-gate result, not a ranking-formula change. It must not be described
as the product cohort falling from 1,237 to 499. The reconciliation runner
emits the full security-level list and reason counts from accepted artifacts.

One mismatch is intentionally conspicuous: Yahoo's TDPOWERSYS adjusted value
was exactly half the official NSE close. The issuer's [official NSE filing](https://nsearchives.nseindia.com/corporate/TDPOWERSYS_14052026190258_Final_For_Upload-SG.pdf)
records a 1:2 subdivision from one ₹2 share into two ₹1 shares. That evidence
explains a corporate-action timing/basis discontinuity; it does not authorize
silently doubling a provider observation. The strict row therefore remains
excluded while the exact-identity product continuity route handles its own
versioned evidence policy.

No Baseline formula or eligibility threshold is changed by this audit.
