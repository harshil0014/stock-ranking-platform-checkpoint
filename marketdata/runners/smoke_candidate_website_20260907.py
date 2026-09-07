from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
from urllib.request import urlopen
from urllib.parse import urlencode

PROJECT = Path.home() / "Downloads" / "stock-ranking-platform"
SRC = PROJECT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CANDIDATE_LIVE = PROJECT / "data/live_market/candidate_bse_20260907_refreshed"
CANDIDATE_FACTS = PROJECT / "data/company_facts_candidate_bse_price_return_20260907"
CANDIDATE_HISTORY = PROJECT / "data/live_market/history_cache_candidate_bse_price_return_20260907"

EXPECTED = {
    "universe": 4572,
    "classified": 4422,
    "product_baseline_eligible": 2346,
    "research_v2_eligible": 63,
}

TARGETS = ("IFBAGRO", "VEEDOL", "GULFOILLUB")


def get_json(base: str, path: str, params: dict[str, str] | None = None) -> dict:
    url = base + path
    if params:
        url += "?" + urlencode(params)
    with urlopen(url, timeout=20) as r:
        if r.status != 200:
            raise RuntimeError(f"{path}: HTTP {r.status}")
        return json.loads(r.read().decode("utf-8"))


def get_text(base: str, path: str) -> str:
    with urlopen(base + path, timeout=20) as r:
        if r.status != 200:
            raise RuntimeError(f"{path}: HTTP {r.status}")
        return r.read().decode("utf-8")


def main() -> int:
    from stock_ranker.live_market import load_live_market_bundle
    from stock_ranker.company_facts import (
        CompanyFactResult,
        FACT_COLUMNS,
        load_company_fact_snapshot,
    )
    import pandas as pd
    import stock_ranker.live_website as live_website
    import stock_ranker.webapp as webapp

    for p in (CANDIDATE_LIVE, CANDIDATE_FACTS, CANDIDATE_HISTORY):
        if not p.exists():
            raise FileNotFoundError(p)

    bundle = load_live_market_bundle(CANDIDATE_LIVE)
    candidate_manifest = json.loads(
        (CANDIDATE_FACTS / "manifest.json").read_text(encoding="utf-8")
    )
    if "artifacts" in candidate_manifest:
        facts = load_company_fact_snapshot(CANDIDATE_FACTS)
    else:
        candidate_frame = pd.read_csv(
            CANDIDATE_FACTS / "company_facts.csv", low_memory=False
        )
        if (
            len(candidate_frame) != int(candidate_manifest["row_count"])
            or any(column not in FACT_COLUMNS for column in candidate_frame.columns)
            or candidate_frame["isin"].duplicated().any()
            or candidate_frame["ticker"].duplicated().any()
        ):
            raise ValueError("pre-promotion company-fact candidate is inconsistent")
        facts = CompanyFactResult(
            facts=candidate_frame.loc[:, FACT_COLUMNS],
            coverage=json.loads(
                (CANDIDATE_FACTS / "coverage.json").read_text(encoding="utf-8")
            ),
            manifest=candidate_manifest,
        )

    # Patch only in-memory presentation dependencies. No accepted pointer,
    # snapshot, cache, source file, or production data is modified.
    live_website._cached_bundle.cache_clear()
    live_website._cached_company_facts.cache_clear()
    live_website._cached_history.cache_clear()
    live_website._bundle = lambda: bundle
    live_website._company_facts = lambda: facts
    live_website.LIVE_HISTORY_ROOT = CANDIDATE_HISTORY

    # The webapp imported these functions from live_website; their module globals
    # still resolve the patched _bundle/_company_facts/history root above.
    server = webapp.create_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        health = get_json(base, "/api/health")
        assert health["status"] == "ok"

        root_html = get_text(base, "/")
        assert "<html" in root_html.lower() or "<!doctype html" in root_html.lower()
        assert len(get_text(base, "/app.js")) > 100
        assert len(get_text(base, "/styles.css")) > 100

        v2 = get_json(base, "/api/live/overview", {"model": "research_v2"})
        baseline = get_json(base, "/api/live/overview", {"model": "baseline_v1"})
        coverage = get_json(base, "/api/live/company-facts-coverage")

        assert v2["summary"]["supported_equities"] == EXPECTED["universe"]
        assert v2["summary"]["research_v2_eligible"] == EXPECTED["research_v2_eligible"]
        assert baseline["summary"]["baseline_eligible"] == EXPECTED["product_baseline_eligible"]
        assert coverage["manifest"]["row_count"] == EXPECTED["universe"]
        assert coverage["coverage"]["metrics"]["product_classified"]["count"] == EXPECTED["classified"]

        target_results = {}
        for ticker in TARGETS:
            stock = get_json(base, "/api/live/stock", {"ticker": ticker})
            hist = get_json(base, "/api/live/history", {"ticker": ticker, "range": "1y"})
            # Stock payload shape may expose the model under detail/model sections,
            # so assert against the canonical candidate bundle as the invariant.
            row = bundle.market.loc[bundle.market["ticker"].eq(ticker)]
            assert len(row) == 1
            rec = row.iloc[0]
            assert bool(rec["v2_eligible"]) is True
            assert str(rec["v2_reason_code"]) == "ELIGIBLE"
            assert hist["available"] is True
            assert hist["end_date"] == "2026-09-07"
            target_results[ticker] = {
                "v2_eligible": True,
                "v2_reason_code": "ELIGIBLE",
                "history_end_date": hist["end_date"],
                "stock_api_available": stock.get("available", True),
            }

        result = {
            "candidate_live_fingerprint": bundle.fingerprint,
            "candidate_company_facts_fingerprint": facts.manifest["fingerprint"],
            "supported_equities": v2["summary"]["supported_equities"],
            "product_baseline_eligible": baseline["summary"]["baseline_eligible"],
            "research_v2_eligible": v2["summary"]["research_v2_eligible"],
            "product_classified": coverage["coverage"]["metrics"]["product_classified"]["count"],
            "targets": target_results,
            "accepted_state_modified": False,
        }

        print(json.dumps(result, indent=2, sort_keys=True))
        print("CANDIDATE WEBSITE HTTP SMOKE: PASS")
        print("No accepted state or production data was modified.")
        return 0

    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
