"""Build and atomically accept the offline company-fact snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from stock_ranker.company_facts import build_company_facts, promote_company_fact_snapshot  # noqa: E402
from stock_ranker.data_state import resolve_accepted_bundle_root  # noqa: E402
from stock_ranker.live_market import load_live_market_bundle  # noqa: E402
from stock_ranker.screener_data_bundle import load_accepted_screener_data_bundle  # noqa: E402
from stock_ranker.screener_statements import accepted_screener_workbook_isins  # noqa: E402


DEFAULT_FILINGS = PROJECT_ROOT / "data/marketdata/nifty50-research-v2-2026-08-07/standalone-contract-reason-fix-run-01/filing_provenance.csv"
DEFAULT_STRATEGY = PROJECT_ROOT / "data/professor_reference/strategy_current/professor_strategy_comparison.csv"
DEFAULT_YAHOO_ROOT = PROJECT_ROOT / "data/company_facts/providers/yahoo"
DEFAULT_OFFICIAL_ROOT = PROJECT_ROOT / "data/company_facts/providers/official_exchange"
DEFAULT_BULK_CLASSIFICATION_ROOT = PROJECT_ROOT / "data/company_facts/providers/bulk_classification"
DEFAULT_SCREENER_STATE = PROJECT_ROOT / "data/company_facts/providers/screener_bundle/accepted_state.json"


def _accepted_yahoo_observations(root: Path) -> Path | None:
    pointer = root / "accepted_state.json"
    if not pointer.is_file():
        return None
    state = json.loads(pointer.read_text(encoding="utf-8"))
    candidate = (root / str(state["accepted_batch"]) / "observations.csv").resolve()
    if root.resolve() not in candidate.parents:
        raise ValueError("Yahoo accepted bundle escapes its provider store")
    return candidate


def _accepted_official_bundle(root: Path) -> Path | None:
    pointer = root / "accepted_state.json"
    if not pointer.is_file():
        return None
    state = json.loads(pointer.read_text(encoding="utf-8"))
    candidate = (root / str(state["accepted_batch"])).resolve()
    if root.resolve() not in candidate.parents or not candidate.is_dir():
        raise ValueError("official accepted bundle escapes its provider store")
    return candidate


def _accepted_bulk_classifications(root: Path) -> tuple[Path | None, str | None]:
    pointer = root / "accepted_state.json"
    if not pointer.is_file():
        return None, None
    state = json.loads(pointer.read_text(encoding="utf-8"))
    batch = (root / str(state["accepted_batch"])).resolve()
    candidate = batch / "classifications.csv"
    if root.resolve() not in batch.parents or not candidate.is_file():
        raise ValueError("bulk-classification accepted bundle escapes its provider store")
    return candidate, str(state["fingerprint"])


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Build the accepted offline company-fact layer.")
    value.add_argument("--state-root", type=Path, default=PROJECT_ROOT / "data/company_facts")
    value.add_argument("--market-state-root", type=Path, default=PROJECT_ROOT / "data/live_market")
    value.add_argument("--history-root", type=Path, default=PROJECT_ROOT / "data/live_market/history_cache")
    value.add_argument("--filing-provenance", type=Path, default=DEFAULT_FILINGS)
    value.add_argument("--professor-strategy", type=Path, default=DEFAULT_STRATEGY)
    value.add_argument("--yahoo-observations", type=Path)
    value.add_argument("--official-backbone", type=Path)
    value.add_argument("--bulk-classifications", type=Path)
    value.add_argument("--screener-state", type=Path, default=DEFAULT_SCREENER_STATE)
    value.add_argument("--dry-run", action="store_true")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    market_root = resolve_accepted_bundle_root(args.market_state_root)
    market = load_live_market_bundle(market_root)
    yahoo_observations = args.yahoo_observations or _accepted_yahoo_observations(DEFAULT_YAHOO_ROOT)
    official_backbone = args.official_backbone or _accepted_official_bundle(DEFAULT_OFFICIAL_ROOT)
    bulk_classifications, bulk_fingerprint = _accepted_bulk_classifications(DEFAULT_BULK_CLASSIFICATION_ROOT)
    if args.bulk_classifications is not None:
        bulk_classifications, bulk_fingerprint = args.bulk_classifications, None
    screener = load_accepted_screener_data_bundle(args.screener_state)
    result = build_company_facts(
        market.market, history_root=args.history_root,
        filing_provenance_path=args.filing_provenance,
        professor_strategy_path=args.professor_strategy,
        yahoo_observations_path=yahoo_observations,
        bulk_classifications_path=bulk_classifications,
        bulk_classification_fingerprint=bulk_fingerprint,
        screener_market_path=screener.root / "market_master.csv",
        screener_history_path=screener.root / "normalized_history.csv",
        screener_workbook_audit_path=screener.root / "workbook_audit.csv",
        screener_workbook_isins=accepted_screener_workbook_isins(),
        screener_bundle_fingerprint=screener.fingerprint,
        screener_source_observed_at=str(screener.summary.get("source_observed_at") or ""),
        official_backbone_path=official_backbone,
        market_fingerprint=market.fingerprint,
    )
    if args.dry_run:
        print(json.dumps({"validated": True, "would_write": False, **result.manifest}, sort_keys=True))
        return 0
    pointer = promote_company_fact_snapshot(result, args.state_root)
    print(f"Accepted {result.manifest['row_count']} company fact rows.")
    print(f"Fact fingerprint: {result.manifest['fingerprint']}")
    print(f"Accepted state: {args.state_root / 'accepted_state.json'}")
    print(json.dumps(result.coverage["metrics"], sort_keys=True))
    print(json.dumps(pointer, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
