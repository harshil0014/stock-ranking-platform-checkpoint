"""Acquire official NSE Integrated Filing metadata and annual XBRLs."""

from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from stock_ranker.real_research_v2 import select_point_in_time_filing  # noqa: E402


API = "https://www.nseindia.com/api/integrated-filing-results"
TYPE = "Integrated Filing- Financials"
CUTOFF = datetime(2026, 8, 7, 15, 30, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
USER_AGENT = "Mozilla/5.0 (compatible; StockRankingResearch/1.0)"


def _fetch(url: str, *, accept: str, max_bytes: int) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "www.nseindia.com", "nsearchives.nseindia.com"
    }:
        raise ValueError(f"refusing non-official source URL: {url}")
    request = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/companies-listing/corporate-integrated-filing",
    })
    with urlopen(request, timeout=60) as response:
        content = response.read(max_bytes + 1)
    if not content or len(content) > max_bytes:
        raise ValueError(f"invalid response size for {url}")
    return content


def acquire(universe_path: Path, output: Path) -> dict[str, object]:
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    universe = pd.read_csv(universe_path)
    if set(("ticker", "company", "sector")).difference(universe.columns):
        raise ValueError("universe must contain ticker, company, sector")
    metadata_dir = output / "raw" / "metadata"
    xbrl_dir = output / "raw" / "xbrl"
    metadata_dir.mkdir(parents=True)
    xbrl_dir.mkdir(parents=True)
    provenance = []
    discovered = 0
    downloaded = 0
    for ticker in sorted(universe["ticker"].astype(str)):
        query = urlencode({
            "type": TYPE, "symbol": ticker, "index": "equities",
            "page": 1, "size": 100,
        })
        api_url = f"{API}?{query}"
        try:
            raw = _fetch(api_url, accept="application/json", max_bytes=5_000_000)
            payload = json.loads(raw)
            rows = payload.get("data", [])
            if not isinstance(rows, list):
                raise ValueError("NSE API data is not a list")
            discovered += len(rows)
            metadata_path = metadata_dir / f"{ticker}.json"
            metadata_path.write_text(
                json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8", newline="\n",
            )
            selected, status = select_point_in_time_filing(rows, CUTOFF)
            entry: dict[str, object] = {
                "ticker": ticker, "metadata_status": "FETCHED",
                "metadata_record_count": len(rows), "selection_status": status,
                "metadata_path": metadata_path.relative_to(output).as_posix(),
                "metadata_sha256": sha256(metadata_path.read_bytes()).hexdigest(),
            }
            if selected is not None:
                xbrl_url = str(selected.get("xbrl", ""))
                xbrl_name = Path(urlparse(xbrl_url).path).name
                if not xbrl_name.lower().endswith(".xml"):
                    raise ValueError("selected filing has no XML XBRL URL")
                content = _fetch(xbrl_url, accept="application/xml,text/xml,*/*", max_bytes=15_000_000)
                xbrl_path = xbrl_dir / f"{ticker}__{xbrl_name}"
                xbrl_path.write_bytes(content)
                downloaded += 1
                entry.update({
                    "selected_metadata": selected,
                    "xbrl_url": xbrl_url,
                    "xbrl_path": xbrl_path.relative_to(output).as_posix(),
                    "xbrl_sha256": sha256(content).hexdigest(),
                    "xbrl_size": len(content),
                })
            provenance.append(entry)
        except Exception as exc:
            provenance.append({
                "ticker": ticker, "metadata_status": "FAILED",
                "selection_status": "NO_ELIGIBLE_NSE_FILING",
                "failure": f"{type(exc).__name__}: {exc}",
            })
        time.sleep(0.1)
    (output / "filing_provenance.json").write_text(
        json.dumps(provenance, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    summary = {
        "requested_count": len(universe), "metadata_records_discovered": discovered,
        "selected_xbrl_count": downloaded, "cutoff": CUTOFF.isoformat(),
        "availability_timestamp": "exchange dissemination time (NSE creation_Date)",
        "source_api": API, "source_type": TYPE,
    }
    (output / "acquisition_summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire official NSE annual consolidated XBRLs.")
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(acquire(args.universe, args.output), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"acquisition failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
