"""Verify the post-reveal September price repair before sensitivity rerun."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import numpy as np
import pandas as pd
from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot

BASE = ROOT / "experiments/personalized-v13-20261002/prospective-2025-09-30"
REPAIR = BASE / "post_reveal_price_repair_20260901_18"


def sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def missing_weekly(path: Path, scheduled: np.ndarray) -> bool:
    if not path.exists():
        return True
    frame = pd.read_csv(path, usecols=["date"])
    dates = pd.to_datetime(frame.date).to_numpy(dtype="datetime64[D]")
    buy = np.searchsorted(dates, scheduled)
    valid = buy < len(dates)
    if not valid.all():
        return True
    return bool(((dates[buy] - scheduled).astype(int) > 7).any())


def main() -> None:
    summary = json.loads((REPAIR / "summary.json").read_text())
    assert summary["first_reveal_sha256"] == sha(BASE / "evaluation_record.json")
    assert summary["locked_scores_sha256"] == sha(BASE / "scores_before_reveal.csv.gz")
    sources = pd.read_csv(REPAIR / "official_price_sources.csv")
    assert len(sources) == 26 and sources.day.nunique() == 13
    for row in sources.itertuples(index=False):
        assert sha(REPAIR / "official_prices" / Path(row.source_url).name) == row.source_sha256
    scores = pd.read_csv(BASE / "scores_before_reveal.csv.gz", usecols=["isin", "profile_name"])
    weekly_ids = set(scores.loc[scores.profile_name.eq("weekly"), "isin"])
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    lookup = facts.drop_duplicates("isin").set_index("isin").ticker.to_dict()
    scheduled = pd.date_range("2025-09-30", "2026-09-29", freq="7D").to_numpy(dtype="datetime64[D]")
    before = after = 0
    for identity in weekly_ids:
        ticker = lookup.get(identity)
        if not isinstance(ticker, str):
            continue
        old = BASE / "official_execution_overlay" / f"{ticker}.csv"
        new = REPAIR / "history_overlay" / f"{ticker}.csv"
        before += missing_weekly(old, scheduled)
        after += missing_weekly(new if new.exists() else old, scheduled)
    if after >= before:
        raise ValueError("weekly structural gap did not improve")
    result = {"schema": "v13_post_reveal_price_repair_audit_v1",
              "first_reveal_sha256": summary["first_reveal_sha256"],
              "locked_scores_sha256": summary["locked_scores_sha256"],
              "official_source_files_verified": len(sources),
              "weekly_decision_identities": len(weekly_ids),
              "weekly_date_gap_identities_before": int(before),
              "weekly_date_gap_identities_after": int(after),
              "outcome_metrics_used_for_repair": False,
              "first_reveal_overwritten": False,
              "post_reveal_sensitivity_only": True}
    (REPAIR / "structural_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
