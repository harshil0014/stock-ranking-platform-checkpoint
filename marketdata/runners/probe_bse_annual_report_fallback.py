from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import time

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.bse_annual_report_fallback import (  # noqa: E402
    exact_bse_identity_map,
    select_bse_annual_report_announcement,
)


API = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; StockRankingResearch/1.0)",
        "Accept": "application/json, text/plain, */*", "Origin": "https://www.bseindia.com",
        "Referer": "https://www.bseindia.com/",
    })
    return session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe exact-ISIN BSE annual-report announcement fallback.")
    parser.add_argument("--metadata-coverage", type=Path, required=True)
    parser.add_argument("--bse-master", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--cutoff", default="2026-08-21T23:59:59")
    args = parser.parse_args(argv)
    try:
        if args.output.exists() or not 1 <= args.limit <= 250:
            raise ValueError("output must be fresh and limit must be 1 through 250")
        coverage = pd.read_csv(args.metadata_coverage, dtype=str).fillna("")
        bse_rows = json.loads(args.bse_master.read_text(encoding="utf-8-sig"))
        identity = exact_bse_identity_map(bse_rows)
        candidates = coverage.loc[
            coverage["selection_status"].ne("SELECTED")
            & coverage["isin"].isin(identity)
        ].sort_values(["selection_key", "isin"], kind="mergesort").head(args.limit)
        args.output.mkdir(parents=True)
        records = []
        with _session() as session:
            for item in candidates.to_dict("records"):
                bse = identity[item["isin"]]
                params = {
                    "pageno": 1, "strCat": "-1", "subcategory": "-1",
                    "strPrevDate": "20260401", "strToDate": "20260821", "strSearch": "P",
                    "strscrip": bse["bse_scrip_code"], "strType": "C",
                }
                try:
                    rows = []
                    total = None
                    for page in range(1, 21):
                        params["pageno"] = page
                        response = session.get(API, params=params, timeout=30)
                        response.raise_for_status()
                        payload = response.json()
                        page_rows = payload.get("Table", [])
                        if not isinstance(page_rows, list):
                            raise ValueError("BSE announcement Table is not a list")
                        rows.extend(page_rows)
                        if total is None:
                            counts = payload.get("Table1") or []
                            total = int(counts[0].get("ROWCNT", len(page_rows))) if counts else len(page_rows)
                        if not page_rows or len(rows) >= total:
                            break
                    if total is not None and len(rows) < total:
                        raise ValueError("BSE announcement pagination exceeded safety limit")
                    selected, status = select_bse_annual_report_announcement(
                        rows, scrip_code=bse["bse_scrip_code"], cutoff=args.cutoff,
                    )
                    records.append({
                        **item, **bse, "status": status, "announcement": selected,
                        "announcement_count": len(rows), "source_api": API,
                    })
                except Exception as exc:
                    records.append({**item, **bse, "status": "BSE_METADATA_ACQUISITION_FAILED", "failure": f"{type(exc).__name__}: {exc}", "source_api": API})
                time.sleep(0.1)
        provenance = args.output / "bse_fallback_provenance.json"
        provenance.write_text(
            json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n",
        )
        counts = pd.Series([row["status"] for row in records]).value_counts().sort_index()
        summary = {
            "schema_version": "bse_annual_report_fallback_probe_v1",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "attempted_count": len(records),
            "exact_bse_identity_population_count": int(coverage["isin"].isin(identity).sum()),
            "status_counts": {str(key): int(value) for key, value in counts.items()},
            "accepted_fundamental_record_count": 0,
            "scientific_boundary": "Metadata candidates only; PDF identity, basis, disclosures, periods and values remain unverified.",
            "provenance_sha256": sha256(provenance.read_bytes()).hexdigest(),
        }
        (args.output / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n",
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"BSE annual-report fallback probe failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
