# PIT-Safe Annual-Report Fundamental Validation

## Scope and boundary

This validation is deliberately separate from the frozen 34-security Research V2
mapping. It reviews the 14 direct-disclosure candidates found by the 50-security
coverage probe. It does not change scoring, eligibility, ranking, formulas, the
standalone accounting contract, or any frozen output.

The reproducible method is intentionally small:

1. select the official NSE annual report using its exchange dissemination time;
2. prove exact security identity with ticker, company name, ISIN, URL, and PDF hash;
3. inspect the audited **standalone** statement and formal statutory/key-ratio table;
4. record direct ROCE, direct debt-equity, and current/prior reported profit with
   page, label, unit, formula wording, period, and warning;
5. validate every record against the cached report hash, page, and text anchors;
6. calculate YoY profit growth only with the already accepted
   `current_reported_profit / prior_reported_profit - 1` convention; and
7. emit review candidates, never an automatic production promotion.

No OCR-derived number is accepted without page review. No missing ratio is derived
from raw accounts, and no ROA/ROE/ROIC/net-debt proxy is substituted. Management
adjustments are not used when a formal statutory ratio is available.

## Result

All 14 reports were attempted. Thirteen contain a complete direct-disclosure record.
Twelve also pass the existing nonnegative debt-equity numeric rule. `IDEA` has a
complete direct record but negative debt-equity and therefore remains unusable under
unchanged V2 eligibility. `POWERINDIA` reports debt-equity as dashes; the validation
does not reinterpret those dashes as numeric zero and leaves the record unresolved.

Important disclosed comparability facts remain visible: `BOSCHLTD` has an alternate
management ROCE excluding exceptional items, while the formal statutory ratio
includes them; the statutory value is selected under the existing policy.
`AMBUJACEM` supplies a restated prior comparator. Several issuers report exceptional
or discontinued-operation effects; reported profit is retained without normalization.

This is strong evidence that deterministic extraction plus human review is accurate
enough for a staged scale-up. It is not evidence for unattended bulk acceptance:
the source tables vary substantially, extraction can lose spacing, and issuer ratio
definitions differ. In the original unbiased 50-security probe, 12 newly usable
records correspond to 24% of the sample. Scaling should proceed in audited batches,
with hash/page/anchor verification and a second reviewer for conflicts, before any
separate production-mapping change. The likely benefit is meaningful expansion—not
complete coverage—and conventional ROCE will remain absent or unsuitable for some
financial companies.

## Reproduction

With the ignored probe evidence present:

```powershell
.\.venv\Scripts\python.exe marketdata\runners\validate_pit_annual_reports.py
```

The output directory is ignored and contains only reviewed candidates and a summary.
It never rewrites `nse_annual_report_research_v2_mapping.json`.
