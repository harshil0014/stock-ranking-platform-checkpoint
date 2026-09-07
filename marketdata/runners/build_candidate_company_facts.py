from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path.home() / "Downloads" / "stock-ranking-platform"
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_ranker.company_facts import build_company_facts  # noqa: E402
from stock_ranker.live_market import load_live_market_bundle  # noqa: E402
from stock_ranker.screener_data_bundle import load_accepted_screener_data_bundle  # noqa: E402


DEFAULT_MARKET = PROJECT_ROOT / "data/live_market/candidate_bse_20260907"
DEFAULT_HISTORY = PROJECT_ROOT / "data/live_market/history_cache_candidate_bse_20260907"
DEFAULT_OUTPUT = PROJECT_ROOT / "data/company_facts_candidate_bse_20260907"

DEFAULT_FILINGS = PROJECT_ROOT / "data/marketdata/nifty50-research-v2-2026-08-07/standalone-contract-reason-fix-run-01/filing_provenance.csv"
DEFAULT_STRATEGY = PROJECT_ROOT / "data/professor_reference/strategy_current/professor_strategy_comparison.csv"

YAHOO_ROOT = PROJECT_ROOT / "data/company_facts/providers/yahoo"
OFFICIAL_ROOT = PROJECT_ROOT / "data/company_facts/providers/official_exchange"
BULK_ROOT = PROJECT_ROOT / "data/company_facts/providers/bulk_classification"
SCREENER_STATE = PROJECT_ROOT / "data/company_facts/providers/screener_bundle/accepted_state.json"


def accepted_yahoo_observations(root: Path) -> Path | None:
    pointer = root / "accepted_state.json"
    if not pointer.is_file():
        return None
    state = json.loads(pointer.read_text(encoding="utf-8"))
    candidate = (root / str(state["accepted_batch"]) / "observations.csv").resolve()
    if root.resolve() not in candidate.parents or not candidate.is_file():
        raise ValueError("Yahoo accepted bundle is invalid")
    return candidate


def accepted_official_bundle(root: Path) -> Path | None:
    pointer = root / "accepted_state.json"
    if not pointer.is_file():
        return None
    state = json.loads(pointer.read_text(encoding="utf-8"))
    candidate = (root / str(state["accepted_batch"])).resolve()
    if root.resolve() not in candidate.parents or not candidate.is_dir():
        raise ValueError("official accepted bundle is invalid")
    return candidate


def accepted_bulk(root: Path) -> tuple[Path | None, str | None]:
    pointer = root / "accepted_state.json"
    if not pointer.is_file():
        return None, None
    state = json.loads(pointer.read_text(encoding="utf-8"))
    batch = (root / str(state["accepted_batch"])).resolve()
    candidate = batch / "classifications.csv"
    if root.resolve() not in batch.parents or not candidate.is_file():
        raise ValueError("bulk classification accepted bundle is invalid")
    return candidate, str(state.get("fingerprint") or "")


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Build isolated candidate company facts/Product Baseline from the "
            "candidate NSE+BSE market bundle and candidate adjusted-history cache."
        )
    )
    p.add_argument("--market-root", type=Path, default=DEFAULT_MARKET)
    p.add_argument("--history-root", type=Path, default=DEFAULT_HISTORY)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = p.parse_args(argv)

    try:
        market = load_live_market_bundle(args.market_root.resolve())

        yahoo = accepted_yahoo_observations(YAHOO_ROOT)
        official = accepted_official_bundle(OFFICIAL_ROOT)
        bulk_path, bulk_fp = accepted_bulk(BULK_ROOT)
        screener = load_accepted_screener_data_bundle(SCREENER_STATE)

        result = build_company_facts(
            market.market,
            history_root=args.history_root.resolve(),
            filing_provenance_path=DEFAULT_FILINGS,
            professor_strategy_path=DEFAULT_STRATEGY,
            yahoo_observations_path=yahoo,
            bulk_classifications_path=bulk_path,
            bulk_classification_fingerprint=bulk_fp,
            screener_market_path=screener.root / "market_master.csv",
            screener_history_path=screener.root / "normalized_history.csv",
            screener_workbook_audit_path=screener.root / "workbook_audit.csv",
            screener_bundle_fingerprint=screener.fingerprint,
            screener_source_observed_at=str(
                screener.summary.get("source_observed_at") or ""
            ),
            official_backbone_path=official,
            market_fingerprint=market.fingerprint,
        )

        facts = result.facts.copy()
        output = args.output_root.resolve()
        output.mkdir(parents=True, exist_ok=True)

        facts_path = output / "company_facts.csv"
        tmp = facts_path.with_suffix(".csv.tmp")
        facts.to_csv(tmp, index=False, lineterminator="\n", encoding="utf-8")
        tmp.replace(facts_path)

        bse = facts.loc[facts["primary_exchange"].astype(str).str.upper().eq("BSE")].copy()

        summary = {
            "market_rows": int(len(facts)),
            "market_fingerprint": market.fingerprint,
            "fact_fingerprint": result.manifest.get("fingerprint"),
            "history_status_counts": facts["history_status"].astype(str).value_counts().to_dict(),
            "history_1y_usable": int(facts["history_1y_usable"].fillna(False).astype(bool).sum()),
            "history_3y_usable": int(facts["history_3y_usable"].fillna(False).astype(bool).sum()),
            "history_5y_usable": int(facts["history_5y_usable"].fillna(False).astype(bool).sum()),
            "product_classified": int(
                facts["product_classification_evidence"].astype(str).ne("UNCLASSIFIED").sum()
            ),
            "product_baseline_eligible": int(
                facts["product_baseline_eligible"].fillna(False).astype(bool).sum()
            ),
            "bse_rows": int(len(bse)),
            "bse_history_usable": int(
                bse["history_status"].astype(str).eq("ACCEPTED_ADJUSTED_HISTORY").sum()
            ),
            "bse_product_classified": int(
                bse["product_classification_evidence"].astype(str).ne("UNCLASSIFIED").sum()
            ),
            "bse_product_baseline_eligible": int(
                bse["product_baseline_eligible"].fillna(False).astype(bool).sum()
            ),
            "output": str(output),
            "accepted_state_modified": False,
        }

        atomic_text(
            output / "summary.json",
            json.dumps(summary, indent=2, sort_keys=True),
        )
        atomic_text(
            output / "coverage.json",
            json.dumps(result.coverage, indent=2, sort_keys=True, default=str),
        )
        atomic_text(
            output / "manifest.json",
            json.dumps(result.manifest, indent=2, sort_keys=True, default=str),
        )

        print(json.dumps(summary, indent=2, sort_keys=True))
        print(f"Candidate facts: {facts_path}")
        print(f"Summary: {output / 'summary.json'}")
        print("CANDIDATE COMPANY FACTS BUILD: PASS")
        print("Accepted market/company-fact state was NOT modified.")
        return 0

    except Exception as exc:
        print(
            f"CANDIDATE COMPANY FACTS BUILD FAILED: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
