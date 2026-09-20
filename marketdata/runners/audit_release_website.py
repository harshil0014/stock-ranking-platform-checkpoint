"""Exhaustive in-process verification of every production website entity and view."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.live_website import (  # noqa: E402
    deployment_health, live_dashboard, live_history, live_overview, live_stock,
)
from stock_ranker.research_website import (  # noqa: E402
    historical, methodology, model_candidates, overview, professor_acceptance,
    professor_reference, quant_lab, status, validation,
)


def run(output: Path) -> dict:
    if output.exists():
        raise ValueError("fresh output directory required")
    health = deployment_health()
    universe = live_overview("baseline_v1")
    rows = universe["rows"]
    if len(rows) != 4436 or not all(row["eligible"] for row in rows):
        raise ValueError("production overview is not the complete accepted universe")
    tickers = [str(row["ticker"]) for row in rows]
    if len(set(tickers)) != len(tickers):
        raise ValueError("production overview contains duplicate tickers")

    sectors = sorted({str(row["sector"]) for row in rows})
    sector_rows = []
    for sector in sectors:
        dashboard = live_dashboard(sector, "baseline_v1", "ALL")
        ranks = sorted(int(row["canonical_sector_rank"]) for row in dashboard["sector_rows"])
        expected = list(range(1, len(ranks) + 1))
        if ranks != expected:
            raise ValueError(f"non-contiguous website ranks for {sector}")
        if dashboard["sector_summary"]["prepared_companies"] != len(ranks):
            raise ValueError(f"dashboard count mismatch for {sector}")
        sector_rows.append({"sector": sector, "companies": len(ranks), "status": "PASS"})

    estimated_pages = 0
    history_available = 0
    for index, ticker in enumerate(tickers, start=1):
        page = live_stock(ticker)
        model = page["baseline_v1"]
        if not model["eligible"] or model["sector_rank"] is None:
            raise ValueError(f"unranked company page: {ticker}")
        provenance = page["company_facts"]["estimate_provenance"]
        if provenance["values"]:
            estimated_pages += 1
        if page["completion_fingerprint"] != health["completion_fingerprint"]:
            raise ValueError(f"stale completion fingerprint on company page: {ticker}")
        history_result = live_history(ticker, "1y")
        if "available" not in history_result:
            raise ValueError(f"history endpoint has no explicit availability: {ticker}")
        history_available += int(bool(history_result["available"]))
        if index % 250 == 0:
            print(f"verified company pages: {index}/{len(tickers)}", flush=True)

    view_checks = {
        "overview": overview(),
        "methodology": methodology(),
        "validation": validation(),
        "candidate_model": model_candidates(),
        "status": status(),
        "quant_lab": quant_lab(),
        "professor_reference": professor_reference(),
        "professor_acceptance": professor_acceptance(),
    }
    for year in ("2022", "2023", "2024", "2025"):
        view_checks[f"historical_{year}"] = historical(year)
    unavailable = [name for name, value in view_checks.items() if not value.get("available")]
    if unavailable:
        raise ValueError(f"production research views unavailable: {unavailable}")

    summary = {
        "schema_version": "release_website_exhaustive_audit_v1",
        "universe_count": len(tickers),
        "company_pages_verified": len(tickers),
        "history_endpoints_verified": len(tickers),
        "history_available_count": history_available,
        "history_explicitly_unavailable_count": len(tickers) - history_available,
        "estimated_company_pages_with_provenance": estimated_pages,
        "sector_count": len(sectors),
        "sector_dashboards_verified": len(sectors),
        "research_views_verified": len(view_checks),
        "broken_company_pages": 0,
        "broken_views": 0,
        "all_checks_pass": True,
        "completion_fingerprint": health["completion_fingerprint"],
    }
    output.mkdir(parents=True)
    (output / "sector_website_audit.csv").write_text(
        "sector,companies,status\n" + "".join(
            f'"{row["sector"].replace(chr(34), chr(34) * 2)}",{row["companies"]},{row["status"]}\n'
            for row in sector_rows
        ), encoding="utf-8",
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifacts = [
        {"path": path.name, "sha256": sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size}
        for path in sorted(output.iterdir())
    ]
    fingerprint = sha256(json.dumps(
        artifacts, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    (output / "manifest.json").write_text(json.dumps({
        "schema_version": "release_website_exhaustive_audit_manifest_v1",
        "fingerprint": fingerprint,
        "artifacts": artifacts,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary | {"fingerprint": fingerprint}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
