"""Write the frozen 4,549-to-4,436 accepted-universe reconciliation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.universe_reconciliation import reconcile_universes, write_reconciliation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--final", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = reconcile_universes(
        pd.read_csv(args.historical, low_memory=False),
        pd.read_csv(args.final, low_memory=False),
    )
    print(json.dumps(write_reconciliation(result, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
