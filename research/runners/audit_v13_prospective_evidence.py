"""Independent structural/provenance gate before V13 prospective reveal."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import numpy as np
import pandas as pd

OUT = ROOT / "experiments/personalized-v13-20261002/prospective-2025-09-30"
OLD_LEDGER = ROOT / "experiments/personalized-official-action-freeze/build-06/normalized_official_action_ledger.csv.gz"
OLD_SPLIT = ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2/split_ledger.csv"


def sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if (OUT / "outcomes_revealed.csv.gz").exists():
        raise ValueError("pre-reveal audit must precede outcome reveal")
    pre = json.loads((OUT / "pre_reveal_record.json").read_text())
    assert pre["selection_lock_sha256"] == sha(ROOT / "experiments/personalized-v13-20261002/locked_selection.json")
    assert pre["scores_before_reveal_sha256"] == sha(OUT / "scores_before_reveal.csv.gz")
    score = pd.read_csv(OUT / "scores_before_reveal.csv.gz")
    features = pd.read_csv(OUT / "decision_features_without_outcomes.csv.gz",
                           usecols=["isin", "decision_date", "profile_name", "future_xirr", "future_shortfall", "future_drawdown"])
    assert len(score) == len(features) == 30305
    assert not features[["future_xirr", "future_shortfall", "future_drawdown"]].notna().any().any()
    assert not score.duplicated(["isin", "decision_date", "profile_name"]).any()
    assert set(score.decision_date) == {"2025-09-30"}
    assert score.profile_name.nunique() == 9
    assert (score.v13_score - score.champion_score).dropna().le(1e-10).all()

    old_actions = pd.read_csv(OLD_LEDGER, low_memory=False)
    new_actions = pd.read_csv(OUT / "official_actions/normalized_official_action_ledger_through_20260930.csv.gz", low_memory=False)
    pd.testing.assert_frame_equal(old_actions, new_actions.iloc[:len(old_actions)].reset_index(drop=True),
                                  check_dtype=False)
    recent = new_actions.iloc[len(old_actions):]
    assert len(recent) == 4 and recent.event_date.between("2026-09-19", "2026-09-30").all()
    assert recent.mechanics_status.eq("AUTO_MULTIPLIER").all()
    old_splits = pd.read_csv(OLD_SPLIT)
    split = pd.read_csv(OUT / "provider_split_ledger/split_ledger.csv")
    pd.testing.assert_frame_equal(old_splits, split.iloc[:len(old_splits)].reset_index(drop=True), check_dtype=False)
    late_split = split.iloc[len(old_splits):]
    assert len(late_split) == 2 and late_split.event_date.between("2026-09-19", "2026-09-30").all()
    action_keys = set(zip(recent["isin"], recent.event_date, recent.event_type))
    assert set(zip(late_split["isin"], late_split.event_date, ["SPLIT"] * len(late_split))).issubset(action_keys)
    bse = pd.read_csv(OUT / "official_actions/bse_acquisition_audit.csv", dtype={"bse_code": str})
    assert len(bse) == 1861
    failed = bse.loc[bse.status.ne("SUCCESS"), "bse_code"].tolist()
    for row in bse.loc[bse.status.eq("SUCCESS")].itertuples(index=False):
        assert sha(OUT / "official_actions/raw" / f"{row.bse_code}.json") == row.source_sha256
    source = pd.read_csv(OUT / "official_price_sources.csv")
    assert len(source) == 16 and source.day.nunique() == 8
    for row in source.itertuples(index=False):
        assert sha(OUT / "official_prices" / Path(row.source_url).name) == row.source_sha256
    official = pd.read_csv(OUT / "official_prices_mapped.csv.gz")
    assert official.date.nunique() == 8 and not official.duplicated(["isin", "date"]).any()
    assert official.close.gt(0).all()
    split_group = {k: v for k, v in late_split.groupby("isin")}
    errors, verified = [], 0
    for isin, group in official.groupby("isin"):
        ticker = group.ticker.iloc[0]
        path = OUT / "official_execution_overlay" / f"{ticker}.csv"
        if not path.exists():
            continue
        history = pd.read_csv(path)
        if history.date.duplicated().any() or history.date.max() > "2026-09-30" or history.raw_close.le(0).any():
            errors.append((isin, "invalid overlay"))
            continue
        joined = group.merge(history, on="date", validate="one_to_one")
        factors = np.ones(len(joined))
        for event in split_group.get(isin, pd.DataFrame()).itertuples(index=False):
            factors[joined.date.lt(event.event_date).to_numpy()] *= event.split_ratio
        difference = np.abs(joined.raw_close.to_numpy() * factors - joined.close.to_numpy())
        relative = difference / joined.close.to_numpy()
        if len(relative) != len(group) or np.max(relative) > 1e-8:
            errors.append((isin, f"official close mismatch {np.max(relative):.6g}"))
        else:
            verified += len(joined)
    if errors:
        raise ValueError(f"execution overlay official price mismatch: {errors[:5]}")
    summary = {"schema": "v13_prospective_prereveal_integrity_audit_v1",
               "selection_lock_sha256": pre["selection_lock_sha256"],
               "scores_before_reveal_sha256": pre["scores_before_reveal_sha256"],
               "pre_reveal_record_sha256": sha(OUT / "pre_reveal_record.json"),
               "decision_rows": len(score), "profiles": score.profile_name.nunique(),
               "frozen_action_rows_byte_semantics_preserved": len(old_actions),
               "new_official_action_rows": len(recent),
               "frozen_provider_split_rows_preserved": len(old_splits),
               "new_provider_split_rows": len(late_split),
               "bse_action_success": int(bse.status.eq("SUCCESS").sum()),
               "bse_action_failed_codes_quarantined": failed,
               "official_price_files_verified": len(source),
               "execution_price_rows_verified": verified,
               "outcome_values_loaded": False, "outcome_file_exists": False,
               "accepted_data_mutated": False}
    (OUT / "pre_reveal_integrity_audit.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
