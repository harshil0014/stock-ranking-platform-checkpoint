r"""Run the safe Upstox Research V2 probe against the accepted company-fact state.

This is the convenience entry point for the live machine. It resolves and
hash-validates ``data/company_facts/accepted_state.json`` through the existing
company-fact loader, then invokes the candidate-only Upstox acquisition runner.
No accepted state is modified.

The only credential is ``UPSTOX_ACCESS_TOKEN`` in the local environment.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_ranker.company_facts import (  # noqa: E402
    load_company_fact_snapshot,
    resolve_company_fact_snapshot,
)


def resolve_inputs(state_root: Path) -> tuple[Path, str]:
    snapshot = resolve_company_fact_snapshot(state_root.resolve())
    loaded = load_company_fact_snapshot(snapshot)
    trade_date = str(loaded.manifest.get("trade_date") or "").strip()
    if not trade_date:
        raise ValueError("accepted company-fact snapshot has no trade_date")
    csv_path = snapshot / "company_facts.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)
    return csv_path, trade_date


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a candidate-only Upstox fundamentals probe on the accepted company-fact state."
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=ROOT / "data" / "company_facts",
        help="Company-fact state root containing accepted_state.json.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--basis", choices=("standalone", "consolidated"), default="standalone"
    )
    parser.add_argument("--sleep-seconds", type=float, default=1.1)
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    try:
        company_facts, trade_date = resolve_inputs(args.state_root)
    except Exception as exc:
        print(f"Accepted company-fact state validation failed: {exc}", file=sys.stderr)
        return 2

    output = (
        args.output.resolve()
        if args.output is not None
        else (ROOT / "data" / "point_in_time" / f"upstox_v2_probe_{trade_date.replace('-', '')}").resolve()
    )
    runner = ROOT / "marketdata" / "runners" / "acquire_upstox_v2_candidates.py"
    command = [
        sys.executable,
        str(runner),
        "--company-facts",
        str(company_facts),
        "--output",
        str(output),
        "--basis",
        args.basis,
        "--sleep-seconds",
        str(args.sleep_seconds),
    ]
    if args.all:
        command.append("--all")
    else:
        command.extend(["--limit", str(args.limit)])
    if output.exists():
        command.append("--resume")

    print(json.dumps({
        "accepted_company_facts": str(company_facts),
        "accepted_trade_date": trade_date,
        "output": str(output),
        "mode": "ALL_NON_V2" if args.all else f"PROBE_{args.limit}",
        "accepted_state_will_be_modified": False,
    }, indent=2, sort_keys=True))
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
