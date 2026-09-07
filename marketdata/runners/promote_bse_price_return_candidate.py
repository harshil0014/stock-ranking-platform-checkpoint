"""Transactionally promote the validated 2026-09-07 market data checkpoint.

The live-market and company-fact stores already expose immutable snapshot
pointers.  Price history is a legacy fixed directory, so this coordinator
stages and inventories a complete cache, swaps it atomically, and retains the
previous cache.  Any later failure restores both accepted pointers and the
previous history directory.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from uuid import uuid4

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_ranker.company_facts import (  # noqa: E402
    CompanyFactResult,
    FACT_COLUMNS,
    load_company_fact_snapshot,
    promote_company_fact_snapshot,
    resolve_company_fact_snapshot,
)
from stock_ranker.data_state import (  # noqa: E402
    DataStatePaths,
    acquire_refresh_lock,
    promote_candidate_bundle,
    release_refresh_lock,
    resolve_accepted_bundle_root,
)
from stock_ranker.live_market import load_live_market_bundle  # noqa: E402


EXPECTED_MARKET_FINGERPRINT = "6dad2b7d600bdb4458bec10f854cdd69e815298369b703b0eaffeafdfb69e504"
EXPECTED_FACT_FINGERPRINT = "be12106f8841136f1a68c2552b5bb946e40d783939d5c3624b0399f3635da448"
TARGETS = ("IFBAGRO", "VEEDOL", "GULFOILLUB")


def _candidate_facts(root: Path) -> CompanyFactResult:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if "artifacts" in manifest:
        return load_company_fact_snapshot(root)
    facts = pd.read_csv(root / "company_facts.csv", low_memory=False)
    if (
        len(facts) != int(manifest["row_count"])
        or any(column not in FACT_COLUMNS for column in facts.columns)
        or facts["isin"].duplicated().any()
        or facts["ticker"].duplicated().any()
    ):
        raise ValueError("pre-promotion company-fact candidate is inconsistent")
    coverage = json.loads((root / "coverage.json").read_text(encoding="utf-8"))
    return CompanyFactResult(
        facts=facts.loc[:, FACT_COLUMNS], coverage=coverage, manifest=manifest
    )


def _cache_inventory(root: Path) -> tuple[int, str]:
    digest = sha256()
    files = sorted(root.glob("*.csv"), key=lambda path: path.name)
    for path in files:
        file_digest = sha256(path.read_bytes()).hexdigest()
        digest.update(f"{path.name}\0{path.stat().st_size}\0{file_digest}\n".encode())
    return len(files), digest.hexdigest()


def _restore_pointer(path: Path, content: bytes | None) -> None:
    if content is None:
        if path.exists():
            path.rename(path.with_name(f"{path.name}.failed-{uuid4().hex}"))
        return
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def promote(args: argparse.Namespace) -> dict[str, object]:
    market_source = args.market_candidate.resolve()
    history_source = args.history_candidate.resolve()
    facts_source = args.company_facts_candidate.resolve()
    state_root = args.state_root.resolve()
    fact_state_root = args.company_facts_state_root.resolve()
    paths = DataStatePaths.from_root(state_root)

    market = load_live_market_bundle(market_source)
    facts = _candidate_facts(facts_source)
    if market.fingerprint != args.expected_market_fingerprint:
        raise ValueError("market candidate fingerprint is not approved")
    if facts.manifest["fingerprint"] != args.expected_company_facts_fingerprint:
        raise ValueError("company-fact candidate fingerprint is not approved")
    if facts.manifest["market_fingerprint"] != market.fingerprint:
        raise ValueError("company facts do not reference the market candidate")
    if int(market.manifest["universe_count"]) != 4572:
        raise ValueError("market candidate universe count changed")
    if int(market.manifest["research_v2_eligible_count"]) != 63:
        raise ValueError("market candidate V2 count changed")
    rows = market.market.set_index("ticker")
    for ticker in TARGETS:
        if ticker not in rows.index or not bool(rows.at[ticker, "v2_eligible"]):
            raise ValueError(f"approved V2 addition is missing: {ticker}")

    source_count, source_inventory = _cache_inventory(history_source)
    if source_count != 4398:
        raise ValueError(f"history candidate contains {source_count} CSV files, expected 4398")

    run_id = uuid4().hex
    staged_market = paths.staging / f"promotion-{run_id}" / "bundle"
    staged_history = state_root / f".history-cache-staging-{run_id}"
    shutil.copytree(market_source, staged_market)
    shutil.copytree(history_source, staged_history)
    staged_count, staged_inventory = _cache_inventory(staged_history)
    if (staged_count, staged_inventory) != (source_count, source_inventory):
        raise ValueError("staged history cache differs from the validated candidate")

    market_pointer_before = paths.accepted_pointer.read_bytes() if paths.accepted_pointer.exists() else None
    facts_pointer = fact_state_root / "accepted_state.json"
    facts_pointer_before = facts_pointer.read_bytes() if facts_pointer.exists() else None
    history_current = state_root / "history_cache"
    history_previous = state_root / f"history_cache_previous_{run_id}"
    failed_history = state_root / f"history_cache_failed_{run_id}"

    lock = acquire_refresh_lock(paths)
    swapped = False
    try:
        if history_current.exists():
            history_current.replace(history_previous)
        staged_history.replace(history_current)
        swapped = True
        market_pointer = promote_candidate_bundle(paths, staged_market)
        facts_pointer_result = promote_company_fact_snapshot(facts, fact_state_root)

        accepted_market = load_live_market_bundle(resolve_accepted_bundle_root(state_root))
        accepted_facts = load_company_fact_snapshot(resolve_company_fact_snapshot(fact_state_root))
        accepted_count, accepted_inventory = _cache_inventory(history_current)
        if accepted_market.fingerprint != market.fingerprint:
            raise ValueError("accepted market fingerprint differs after promotion")
        if accepted_facts.manifest["fingerprint"] != facts.manifest["fingerprint"]:
            raise ValueError("accepted company-fact fingerprint differs after promotion")
        if (accepted_count, accepted_inventory) != (source_count, source_inventory):
            raise ValueError("accepted history cache differs after promotion")

        report = {
            "status": "ACCEPTED",
            "market_pointer": market_pointer,
            "company_facts_pointer": facts_pointer_result,
            "history_csv_count": accepted_count,
            "history_inventory_sha256": accepted_inventory,
            "previous_history_cache": str(history_previous),
            "previous_history_cache_retained": history_previous.is_dir(),
        }
        report_path = state_root / "promotion_reports" / f"bse-price-return-{run_id}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        report["report_path"] = str(report_path)
        return report
    except Exception:
        _restore_pointer(paths.accepted_pointer, market_pointer_before)
        _restore_pointer(facts_pointer, facts_pointer_before)
        if swapped and history_current.exists():
            history_current.replace(failed_history)
        if history_previous.exists():
            history_previous.replace(history_current)
        raise
    finally:
        release_refresh_lock(lock)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-candidate", type=Path, default=ROOT / "data/live_market/candidate_bse_20260907_refreshed")
    parser.add_argument("--history-candidate", type=Path, default=ROOT / "data/live_market/history_cache_candidate_bse_price_return_20260907")
    parser.add_argument("--company-facts-candidate", type=Path, default=ROOT / "data/company_facts_candidate_bse_price_return_20260907")
    parser.add_argument("--state-root", type=Path, default=ROOT / "data/live_market")
    parser.add_argument("--company-facts-state-root", type=Path, default=ROOT / "data/company_facts")
    parser.add_argument("--expected-market-fingerprint", default=EXPECTED_MARKET_FINGERPRINT)
    parser.add_argument("--expected-company-facts-fingerprint", default=EXPECTED_FACT_FINGERPRINT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        print(json.dumps(promote(args), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"PROMOTION FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
