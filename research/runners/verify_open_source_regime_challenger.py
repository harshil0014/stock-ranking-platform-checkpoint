#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_research.open_source_regimes import verify_regime_run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    result = verify_regime_run(args.run)
    print(f"PASS: {result['selection_rule_winner']} research result; immutable boundaries verified")


if __name__ == "__main__":
    main()
