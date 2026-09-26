#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_research.open_source_rankers import verify_ranker_run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    result = verify_ranker_run(parser.parse_args().run)
    print(f"PASS: {result['selected_system']}; ranker artifacts and immutable boundaries verified")


if __name__ == "__main__":
    main()
