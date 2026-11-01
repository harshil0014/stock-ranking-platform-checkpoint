# Pre-outcome implementation correction

The initial governed worker was paused during ADV20 cache preparation, then its
own verified supervisor was stopped before any fit or candidate metric output.
Its pause evidence and partial log remain local. No outcome was inspected.

Review found that a naive implementation would choose the timing quartile after
excluding future action/price failures. Corrected this before scoring: compute
dip membership from the prefix alone; select the overlay before future outcome
availability filters; keep missing/blocked outcomes unknown and invalidate the
corresponding date/scope comparison. Never backfill overlay slots from survivors.
As-of data failures quarantine the whole date. The existing source-panel
outcome-availability conditioning remains an explicit retrospective limitation.
No threshold, feature, weight, cost, year, or adoption rule was changed.
