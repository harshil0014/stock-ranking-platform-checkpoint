from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from marketdata.runners.acquire_nse_annual_reports import _fetch  # noqa: E402
from stock_ranker.identity_continuity import (  # noqa: E402
    NAME_HISTORY_URL,
    SYMBOL_HISTORY_URL,
    build_identity_continuity,
    parse_nse_name_history,
    parse_nse_symbol_history,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )


def _accepted_company_facts() -> Path:
    state = json.loads((ROOT / "data/company_facts/accepted_state.json").read_text(encoding="utf-8"))
    return ROOT / "data/company_facts" / state["snapshot_path"] / "company_facts.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire official NSE identity-continuity evidence.")
    parser.add_argument("--company-facts", type=Path, default=None)
    parser.add_argument("--corporate-actions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError(f"output already exists: {args.output}")
        args.output.mkdir(parents=True)
        symbol_bytes = _fetch(SYMBOL_HISTORY_URL, accept="text/csv,*/*", max_bytes=10_000_000)
        name_bytes = _fetch(NAME_HISTORY_URL, accept="text/csv,*/*", max_bytes=10_000_000)
        (args.output / "symbolchange.csv").write_bytes(symbol_bytes)
        (args.output / "namechange.csv").write_bytes(name_bytes)
        facts = pd.read_csv(args.company_facts or _accepted_company_facts(), low_memory=False)
        actions = pd.read_csv(args.corporate_actions, low_memory=False) if args.corporate_actions else None
        continuity, summary = build_identity_continuity(
            facts, parse_nse_symbol_history(symbol_bytes), parse_nse_name_history(name_bytes), actions,
            symbol_source_sha256=sha256(symbol_bytes).hexdigest(),
            name_source_sha256=sha256(name_bytes).hexdigest(),
        )
        continuity.to_csv(
            args.output / "identity_continuity.csv", index=False,
            encoding="utf-8", lineterminator="\n",
        )
        summary.update({
            "schema_version": "official_nse_identity_continuity_v1",
            "symbol_history_url": SYMBOL_HISTORY_URL,
            "name_history_url": NAME_HISTORY_URL,
            "symbol_source_sha256": sha256(symbol_bytes).hexdigest(),
            "name_source_sha256": sha256(name_bytes).hexdigest(),
        })
        _write_json(args.output / "identity_continuity_summary.json", summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"identity-continuity acquisition failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
