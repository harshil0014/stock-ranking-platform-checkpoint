"""Evaluate fixed supplementary models without changing the frozen primary study."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_research.exploratory_benchmark import run_exploratory_benchmark  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("readiness-root", "protocol", "blind-root", "evaluation-root", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        value = run_exploratory_benchmark(
            readiness_root=args.readiness_root, protocol_path=args.protocol,
            blind_root=args.blind_root,
            evaluation_root=args.evaluation_root, output=args.output,
        )
        print(value)
        return 0
    except Exception as exc:
        print(f"exploratory benchmark failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
