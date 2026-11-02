# Codebase cleanup â€” 1 November 2026

Removed 12,624 tracked obsolete files (about 1.74 GB of file contents): 12,247 experiment artifacts, 216 standalone runners, 109 reports, seven protocols, 13 tests belonging to retired trials, and old scratch/build helpers. Counts describe this cleanup, not model success rates.

The existing website and ranking source, frozen runtime packages, price/source data, active daily prospective ledger, retained preference results and dependency fixtures are preserved. No ranking model or weights changed. Some older experiment folders and runners remain because retained runtime, tests, ledger or reproducibility contracts reference them. Ignored local data caches and environments were not blindly purged.

The 20% high-recency experiment remains a successful preference-alignment experiment only, not a validated accuracy improvement; it is not deployed. Its known five-year eligibility limitation is retained. The earlier professor preference lens is preserved too.

The complete tracked pre-cleanup state is at tag `research-archive-before-cleanup-20261101` (commit `630d5522`). Restore an individual historical file with `git restore --source research-archive-before-cleanup-20261101 -- <path>`, or browse the tag on GitHub. No Git or prospective-ledger history was rewritten. The running variant registry stays intact; paths to retired evidence resolve against that tag.

All 1,104 retained tests collected. Of 81 targeted checks, 61 passed and 20 website checks failed. The local live-market junction points to a missing external snapshot, and a UI test expects an older JavaScript routing expression. Champion, personalization and ledger checks passed. The full suite was not executed.

Retired specialist-neural trial runners and their three tests were also archived; they imported the research-only Torch environment and were not production checks. Original incomplete collection logs were preserved locally.
