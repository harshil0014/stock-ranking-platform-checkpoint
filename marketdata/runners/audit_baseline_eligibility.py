"""Write a deterministic Baseline cohort reconciliation from accepted snapshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from stock_ranker.baseline_eligibility_audit import audit_baseline_eligibility  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--earlier-live", type=Path, required=True)
    parser.add_argument("--current-live", type=Path, required=True)
    parser.add_argument("--company-facts", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error(f"output directory already exists: {args.output_dir}")
    detail, summary = audit_baseline_eligibility(
        pd.read_csv(args.earlier_live), pd.read_csv(args.current_live), pd.read_csv(args.company_facts),
    )
    args.output_dir.mkdir(parents=True)
    detail.to_csv(args.output_dir / "baseline_eligibility_reconciliation.csv", index=False, lineterminator="\n", float_format="%.17g")
    (args.output_dir / "baseline_eligibility_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n",
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
