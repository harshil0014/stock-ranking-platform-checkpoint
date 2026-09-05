"""Prepare exact checklist and official-clock evidence for a targeted Screener ZIP."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.targeted_screener_rescue import (  # noqa: E402
    merge_official_clock_evidence, targeted_checklist,
)
from stock_ranker.screener_historical_fundamentals import sha256_file  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--identity-source", type=Path, required=True)
    parser.add_argument("--base-availability", type=Path, required=True)
    parser.add_argument("--annual-metadata-root", type=Path, required=True)
    parser.add_argument("--rescue-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError(f"output directory already exists: {args.output}")
    targets = pd.read_csv(args.targets, dtype=str, keep_default_na=False)
    checklist, workbook_audit = targeted_checklist(targets, args.archive)
    availability, clock_audit = merge_official_clock_evidence(
        targets, pd.read_csv(args.base_availability, dtype=str, keep_default_na=False),
        args.annual_metadata_root, args.rescue_root,
    )
    identities = pd.read_csv(args.identity_source, dtype=str, keep_default_na=False)
    identities = identities.loc[
        identities["reference_nse_code"].isin(targets["ticker"]),
        ["reference_nse_code", "isin", "company"],
    ].rename(columns={"reference_nse_code": "ticker"})
    if len(identities.drop_duplicates("ticker")) != len(targets):
        raise ValueError("identity source does not contain every exact target")
    acquisition_queue = targets[["ticker", "isin", "company", "historical_dates_helped"]].copy()
    acquisition_queue["acquisition_status"] = "TARGETED_WORKBOOK_SUPPLIED_CLOCK_VALIDATED_PER_PERIOD"
    args.output.mkdir(parents=True)
    for name, frame in {
        "targeted_checklist.csv": checklist,
        "workbook_identity_audit.csv": workbook_audit,
        "targeted_identity_master.csv": identities,
        "targeted_acquisition_queue.csv": acquisition_queue,
        "augmented_official_availability.csv": availability,
        "official_clock_evidence_audit.csv": clock_audit,
    }.items():
        frame.to_csv(args.output / name, index=False, encoding="utf-8", lineterminator="\n")
    summary = {
        "archive_sha256": sha256_file(args.archive), "attempted_workbooks": len(checklist),
        "exact_identity_matches": int(workbook_audit["identity_status"].eq("EXACT_LEGAL_NAME_MATCH").sum()),
        "explicit_target_clock_evidence_rows": len(clock_audit),
    }
    (args.output / "preparation_summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
