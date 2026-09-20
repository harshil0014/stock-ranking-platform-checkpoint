"""Freeze current model challengers before any future outcome is available."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_research.prospective_validation import freeze_prospective_challengers  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, default=ROOT / "data/company_facts")
    parser.add_argument("--history-root", type=Path, default=ROOT / "data/live_market/history_cache")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(freeze_prospective_challengers(
            state_root=args.state_root, history_root=args.history_root,
            output=args.output,
        ))
        return 0
    except Exception as exc:
        print(f"prospective freeze failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
