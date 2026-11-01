# New information: bounded high-variance pilots

Frozen before new candidate outcome inspection, 2026-11-01. Research only. No
champion/lens weight changes, trades, published recommendations, or ledger changes.

1. Execution repair: actual provider Open multiplied by Adj Close / Close. Never
   substitute a close for an open. Every contribution executes strictly after its
   scheduled date; deposits remain cash until execution. Seven calendar-day
   maximum execution/mark gap. Fractional units, 25 bp each buy and terminal sale.
   Replay frozen champion and factor20_fixed on the existing complete-factor
   cohort, global top20 and equal-sector top3. Keep legacy tables unchanged;
   compare on matched valid dates and report all failed observations. No selection
   from corrected portfolio results. Provider adjustment and survivor limitations
   remain. A correction may increase or decrease returns.
2. Delivery pilot: require official historical delivery fields with same-session
   ISIN mapping, at least 500 matched stocks/date, 8 development and 4 diagnostic
   exposed dates. Lag source sessions at least one day. One fixed Ridge alpha10
   delivery-augmented head versus price/volume control; no hyperparameter search.
   Target: next-open to 21st-session close, explicitly a different short-term
   task from 12-month SIP. Development delta IC must beat both 0.0101349 and the
   paired 365-day block-bootstrap hurdle; exposed is a locked diagnostic, never
   a tuning set. Acquisition timebox: one serial direct attempt per selected
   source plus one browser fallback. If acquisition/identity coverage fails,
   BLOCK rather than substitute volume or fabricate delivery/circuit/pledge data.
3. Filing pilot: up to six timestamped public filings; issuer identifiers
   redacted. One installed llama3.2:3b model, fixed prompt/seed/temperature0,
   CPU-only, one thread in the existing governed job. At most 10 minutes of
   inference. Extract explicit auditor resignation/appointment, unrelated
   resignation, or unknown with an exact supporting substring. Compare to fixed
   regex on source-reviewed factual labels. Labels are not independent human
   adjudication. Any unsupported assertion fails that case. Must strictly beat
   regex factual accuracy to retain the LLM; a tie drops it. No investment-alpha
   claim: dated pledges and mature prospective loser labels are unavailable.
   Record actual first observation separately from exchange time; never backfill.

CPU hard cap12.5%, one worker/thread, 4s active/2s rest. No GPU inference. Other
ideas (tail radar, global-model replacement, regime switch, real money) are not
silently promoted by this experiment. Historical PIT membership and executable
price history are still prerequisites for the proposed old-regime tests.
