from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.pit_annual_report_packets import build_annual_report_review_packets  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build strict annual-report evidence review packets.")
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--acquisition-root", type=Path, required=True)
    parser.add_argument("--audit-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError(f"output already exists: {args.output}")
        args.output.mkdir(parents=True)
        cohort = pd.read_csv(args.cohort, low_memory=False)
        matrix, packets, summary = build_annual_report_review_packets(
            cohort, args.acquisition_root, args.audit_root,
        )
        matrix.to_csv(args.output / "review_queue.csv", index=False, encoding="utf-8", lineterminator="\n")
        (args.output / "review_packets.json").write_text(
            json.dumps(packets, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n",
        )
        (args.output / "review_packet_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n",
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"annual-report review packet build failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
