"""Periodically acquire exact-identity Yahoo broad-sector classifications.

This is intentionally separate from the daily market refresh.  Product code
never imports yfinance and reads only an accepted local classification batch.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.bulk_classification import build_bulk_classifications  # noqa: E402
from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot  # noqa: E402
from stock_ranker.data_state import atomic_write_json  # noqa: E402


BSE_LIST_URL = "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/134.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.5", "Origin": "https://www.bseindia.com",
        "Referer": "https://www.bseindia.com/",
    })
    return session


def _fetch_bse() -> list[dict[str, Any]]:
    with _bse_session() as session:
        response = session.get(BSE_LIST_URL, params={
            "scripcode": "", "Group": "", "industry": "",
            "segment": "Equity", "status": "Active",
        }, timeout=30)
        response.raise_for_status()
        if "json" not in response.headers.get("content-type", "").lower():
            raise ValueError("BSE security response is not JSON")
        value = response.json()
    if not isinstance(value, list) or not value:
        raise ValueError("BSE security response is empty or malformed")
    return value


def _fetch_yahoo() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    import yfinance as yf
    from yfinance import EquityQuery

    requests_made = 0
    repeated_pages: list[dict[str, Any]] = []

    def paginate(query: EquityQuery, label: str) -> tuple[list[dict[str, Any]], int]:
        nonlocal requests_made
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        offset = 0
        total = 0
        while True:
            requests_made += 1
            response = yf.screen(query, offset=offset, size=250, sortField="ticker", sortAsc=True)
            page = response.get("quotes", []) or []
            total = int(response.get("total") or 0)
            signature = tuple(str(row.get("symbol", "")) for row in page)
            if signature in seen and page:
                repeated_pages.append({"label": label, "offset": offset})
                break
            seen.add(signature)
            rows.extend(page)
            if not page or len(rows) >= total or len(page) < 250:
                break
            offset += 250
            time.sleep(0.1)
        return rows, total

    region = EquityQuery("eq", ["region", "in"])
    universe, total = paginate(region, "Indian equity universe")
    sectors: list[dict[str, Any]] = []
    totals: dict[str, int] = {}
    for sector in sorted(region.valid_values["sector"]):
        query = EquityQuery("and", [region, EquityQuery("eq", ["sector", sector])])
        rows, sector_total = paginate(query, sector)
        totals[sector] = sector_total
        sectors.extend({"sector": sector, **row} for row in rows)
        time.sleep(0.15)
    if repeated_pages:
        raise ValueError(f"Yahoo pagination repeated pages: {repeated_pages}")
    keep = ("symbol", "exchange", "quoteType", "longName", "shortName")
    normalized_universe = [{key: row.get(key) for key in keep} for row in universe]
    normalized_sectors = [
        {"sector": row["sector"], **{key: row.get(key) for key in keep}}
        for row in sectors
    ]
    return normalized_universe, normalized_sectors, {
        "yfinance_version": yf.__version__, "request_count": requests_made,
        "reported_total": total, "sector_totals": totals,
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Acquire cached exact-identity bulk sector classifications.")
    value.add_argument("--company-facts-root", type=Path, default=ROOT / "data/company_facts")
    value.add_argument("--output-root", type=Path, default=ROOT / "data/company_facts/providers/bulk_classification")
    value.add_argument("--batch-id", required=True)
    value.add_argument("--retrieved-at")
    value.add_argument("--offline-bse", type=Path)
    value.add_argument("--offline-yahoo-universe", type=Path)
    value.add_argument("--offline-yahoo-sectors", type=Path)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    batch = args.output_root / args.batch_id
    if batch.exists():
        raise ValueError(f"classification batch already exists: {batch}")
    offline = (args.offline_bse, args.offline_yahoo_universe, args.offline_yahoo_sectors)
    if any(path is not None for path in offline) and not all(path is not None for path in offline):
        raise ValueError("all three offline evidence paths are required together")
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(args.company_facts_root)).facts
    rich_secondary = facts["secondary_identity_status"].eq("EXCHANGE_SYMBOL_MATCH") & facts["secondary_sector"].notna()
    candidates = facts.loc[facts["official_sector"].isna() & ~rich_secondary, [
        "ticker", "isin", "primary_exchange", "exchange_security_id",
    ]].copy()
    retrieved_at = args.retrieved_at or datetime.now(timezone.utc).isoformat()
    if all(path is not None for path in offline):
        bse_rows = json.loads(args.offline_bse.read_text(encoding="utf-8-sig"))
        yahoo_rows = json.loads(args.offline_yahoo_universe.read_text(encoding="utf-8-sig"))
        sector_rows = json.loads(args.offline_yahoo_sectors.read_text(encoding="utf-8-sig"))
        acquisition = {"mode": "OFFLINE_REBUILD_FROM_CACHED_PROBE", "request_count": 0}
    else:
        bse_rows = _fetch_bse()
        yahoo_rows, sector_rows, acquisition = _fetch_yahoo()
        acquisition["mode"] = "LIVE_PUBLIC_BULK_ENDPOINTS"
    result = build_bulk_classifications(
        candidates, official_bse=pd.DataFrame(bse_rows),
        yahoo_universe=pd.DataFrame(yahoo_rows),
        yahoo_sector_memberships=pd.DataFrame(sector_rows), retrieved_at=retrieved_at,
    )
    batch.mkdir(parents=True)
    result.classifications.to_csv(batch / "classifications.csv", index=False, encoding="utf-8", lineterminator="\n")
    result.audit.to_csv(batch / "audit.csv", index=False, encoding="utf-8", lineterminator="\n")
    (batch / "bse_official.json").write_text(json.dumps(bse_rows, sort_keys=True, separators=(",", ":")), encoding="utf-8", newline="\n")
    (batch / "yahoo_universe.json").write_text(json.dumps(yahoo_rows, sort_keys=True, separators=(",", ":")), encoding="utf-8", newline="\n")
    (batch / "yahoo_sectors.json").write_text(json.dumps(sector_rows, sort_keys=True, separators=(",", ":")), encoding="utf-8", newline="\n")
    atomic_write_json(batch / "summary.json", result.summary)
    artifacts = {
        name: {"sha256": _sha256(batch / name), "size": (batch / name).stat().st_size}
        for name in ("classifications.csv", "audit.csv", "bse_official.json", "yahoo_universe.json", "yahoo_sectors.json", "summary.json")
    }
    manifest = {
        "schema_version": "bulk_classification_batch_v1", "batch_id": args.batch_id,
        "fingerprint": result.fingerprint, "retrieved_at": retrieved_at,
        "classification_count": len(result.classifications),
        "classification_by_exchange": result.summary["accepted_by_exchange"],
        "acquisition": acquisition, "artifacts": artifacts,
        "taxonomy_scope": result.summary["taxonomy_scope"],
    }
    atomic_write_json(batch / "manifest.json", manifest)
    atomic_write_json(args.output_root / "accepted_state.json", {
        "accepted_batch": args.batch_id, "fingerprint": result.fingerprint,
        "classification_count": len(result.classifications), "retrieved_at": retrieved_at,
    })
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
