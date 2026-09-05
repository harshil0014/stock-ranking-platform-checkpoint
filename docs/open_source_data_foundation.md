# Open-source data foundation audit

Audit date: 22 August 2026. Every repository below was inspected in an
isolated temporary directory; none was added as Git history or a runtime
dependency. Source facts remain subject to their upstream-provider terms even
when acquisition code itself is open source.

| Project | Audited revision | Licence | Decision |
|---|---|---|---|
| [yahoo-finance2](https://github.com/gadicc/node-yahoo-finance2) | `38207d42590f027222a6cecfb2cf487d68365474` | MIT | Reusable design reference. Its maintained fundamentals time-series surface confirms modern Yahoo financial/balance/cash-flow modules; the project keeps Python/yfinance isolated to acquisition instead. |
| [nse-xbrl](https://github.com/ShantanuAnant/nse-xbrl) | inspected 22 Aug 2026 | MIT | Reusable parser/taxonomy reference. The product uses a taxonomy-tolerant local parser and does not adopt its transport blindly. |
| [nse-historical-membership](https://github.com/aditya-jha/nse-historical-membership) | `0e9f58c4d457faf0e7ad3db4f4c1449e697e23e0` | MIT code; CC BY 4.0 data | Accepted attribution-preserving historical shareholding facts derived from official NSE XBRLs. |
| [indian-market-data-endpoints](https://github.com/satwikbasu/indian-market-data-endpoints) | `6dee32037ef086b3de5357e9435f8c585b6858dd` | MIT | Endpoint reconnaissance reference only; official exchange responses remain the evidence. |
| [financeindia](https://github.com/cansarigol/financeindia) | `d4d94f0c460121c9ad9d36296646e9647812ac61` | MIT | Strong maintained acquisition reference; evaluate its Rust/Python boundary separately before adding a dependency. |
| [jugaad-data](https://github.com/jugaad-py/jugaad-data) | `e11a88171ca55ffd4682ad795f1f8f93e6e1ef73` | nonstandard `LICENSE.YOLO.md` | Study only. Do not copy until licence and upstream terms receive explicit review. |
| [nsepython](https://github.com/aeron7/nsepython) | `a81bfcb08e28d48ec9e4b2feb1aa27f5c343aa36` | GPL-3.0 | Study only; copying would impose incompatible distribution obligations on the current unlicensed project. |
| [FTC Screener](https://github.com/Vedanto28/ftc-screener) | `1d1371a364f5263303c56c09252cc8524ca86e5a` | no licence found | Study only. Copyright defaults apply, and its Yahoo quote-summary financial modules are less current than maintained fundamentals-time-series interfaces. |

The implementation therefore reuses no unlicensed source code. Provider SDKs
remain outside the lightweight product environment. Product code accepts only
canonical CSV/JSON artifacts that pass exact ISIN/exchange/symbol checks,
numeric semantics, hashes, and freshness rules.

## Screener boundary

Screener is a UI and field-coverage benchmark, not a provider. Its current
terms grant personal, non-commercial transitory viewing and prohibit copying
or public display of its materials. Its robots policy disallows automated
query/pagination and source-quarter routes. Consequently the runtime policy is
`POLICY_DISABLED`: no crawling, no hidden endpoint calls, no copied statements,
and no production dependency. A user-supplied export can be compared only when
its source date and permitted use are recorded.

## Independent-source hierarchy

1. NSE/BSE/SEBI/depository/MCA evidence defines identity, exchange facts,
   filings, actions and classifications.
2. Issuer annual reports and accepted XBRL/PDF extraction define audited
   accounting evidence with period and standalone/consolidated basis.
3. Identity-validated Yahoo observations provide secondary current reference
   fields and provider-adjusted history. They never override official facts or
   enter strict Research V2.
4. Paid data remains optional future fallback only after coverage and licence
   trials. No broker account, private key, or paid subscription is required.

This removes a single-source dependency without pretending that wrappers of
the same Yahoo endpoints are independent providers.

## Real parser and provider benchmarks

The audited `nse-xbrl` approach was first executed against all 49 previously
accepted NSE Integrated Filing XML documents. The generalized production
parser then normalized 4,015 official XBRLs across INDAS, banking, NBFC and
insurance families into 1,582,209 retained numeric facts for 2,269 issuers;
five downloads/parses remained explicit failures. This independently confirms
the usefulness of the permissive parsing approach. The repository's existing
point-in-time filing selection and audited standalone contract remain in place
because a parser's ability to read facts does not establish comparable basis,
definition, filing revision, or Research V2 eligibility.

Modern yfinance 1.5.1 was tested against live Indian securities. It returned
current profile, valuation, annual/quarterly income, balance-sheet, cash-flow,
actions and holder data through current interfaces. This replaced the stale
Yahoo quote-summary statement approach studied in FTC Screener. In the initial
346-security benchmark, 340 exact identities were accepted and six rejected.
The audit found that five rejections were caused by a local mapping-precedence
defect (a BSE professor symbol superseding a canonical NSE symbol), not by
provider absence. The general rule was corrected and a fresh run accepted
345/346; the one remaining BSE mapping returned no identity and was not
substituted.

Modern `yahoo-finance2` 4.0.2 was also executed independently through its CLI,
not merely inspected. `fundamentalsTimeSeries` with `annual` / `financials`
returned RELIANCE annual records for 2024, 2025 and 2026 with populated
revenue, EBITDA, EBIT, net income, EPS and share counts. That corroborated the
current Yahoo time-series route and the yfinance statement results. It did not
justify adding Node to the product: both clients depend on Yahoo, so a second
wrapper would add operational complexity without independent-source
resilience. The audited source remains a useful MIT reference and future
cross-client diagnostic.

An additional negative identity test proved why response presence is not
coverage: converting a missing provider symbol to the string `nan` reached an
unrelated NYSE equity named `NAN`. Exact symbol, expected exchange, `EQUITY`
type and canonical mapping are now mandatory before any returned fact is
accepted.
