"""Acquire point-in-time FY2025-26 annual reports from official NSE hosts."""

from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import time
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd


API = "https://www.nseindia.com/api/annual-reports"
PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-annual-reports"
CUTOFF = datetime(2026, 8, 7, 15, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
MAX_METADATA_BYTES = 2_000_000
MAX_PDF_BYTES = 150_000_000
USER_AGENT = "Mozilla/5.0 (compatible; StockRankingResearch/1.0)"


def _fetch(url: str, *, accept: str, max_bytes: int) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "www.nseindia.com", "nsearchives.nseindia.com", "archives.nseindia.com"
    }:
        raise ValueError(f"refusing non-official annual-report URL: {url}")
    request = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": PAGE,
    })
    with urlopen(request, timeout=120) as response:
        content = response.read(max_bytes + 1)
    if not content or len(content) > max_bytes:
        raise ValueError(f"invalid response size for {url}")
    return content


def _timestamp(value: object) -> datetime:
    parsed = datetime.strptime(str(value), "%d-%b-%Y %H:%M:%S")
    return parsed.replace(tzinfo=ZoneInfo("Asia/Kolkata"))


def select_annual_report(
    rows: list[dict[str, object]], cutoff: datetime = CUTOFF
) -> tuple[dict[str, object] | None, str]:
    if cutoff.tzinfo is None:
        raise ValueError("annual-report cutoff must be timezone-aware")
    candidates = []
    for row in rows:
        try:
            dissemination = _timestamp(row["disseminationDateTime"])
        except (KeyError, TypeError, ValueError):
            continue
        if (
            str(row.get("fromYr")) == "2025"
            and str(row.get("toYr")) == "2026"
            and dissemination <= cutoff
            and str(row.get("fileName", "")).lower().endswith(".pdf")
        ):
            candidates.append((row, dissemination))
    if not candidates:
        return None, "NO_ELIGIBLE_ANNUAL_REPORT"
    return max(candidates, key=lambda item: (item[1], str(item[0].get("fileName"))))[0], "SELECTED"


def acquire(universe_path: Path, output: Path, seed_directory: Path | None) -> dict[str, object]:
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    universe = pd.read_csv(universe_path)
    if {"ticker", "company", "sector"}.difference(universe.columns):
        raise ValueError("universe must contain ticker, company, sector")
    metadata_dir = output / "metadata"
    pdf_dir = output / "pdf"
    metadata_dir.mkdir(parents=True)
    pdf_dir.mkdir()
    records = []
    for ticker in sorted(universe["ticker"].astype(str)):
        url = f"{API}?{urlencode({'index': 'equities', 'symbol': ticker})}"
        entry: dict[str, object] = {"ticker": ticker, "api_url": url}
        try:
            payload = json.loads(_fetch(url, accept="application/json", max_bytes=MAX_METADATA_BYTES))
            rows = payload.get("data", [])
            if not isinstance(rows, list):
                raise ValueError("annual-report API data is not a list")
            metadata_path = metadata_dir / f"{ticker}.json"
            metadata_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8", newline="\n",
            )
            selected, status = select_annual_report(rows)
            entry.update({
                "metadata_status": "FETCHED", "metadata_record_count": len(rows),
                "metadata_path": metadata_path.relative_to(output).as_posix(),
                "metadata_sha256": sha256(metadata_path.read_bytes()).hexdigest(),
                "selection_status": status,
            })
            if selected is not None:
                source_url = str(selected["fileName"])
                filename = Path(urlparse(source_url).path).name
                destination = pdf_dir / f"{ticker}__{filename}"
                seed = seed_directory / filename if seed_directory else None
                if seed is not None and seed.is_file():
                    shutil.copyfile(seed, destination)
                    acquisition_method = "VERIFIED_LOCAL_OFFICIAL_SEED"
                else:
                    destination.write_bytes(_fetch(
                        source_url, accept="application/pdf", max_bytes=MAX_PDF_BYTES
                    ))
                    acquisition_method = "OFFICIAL_NSE_DOWNLOAD"
                content = destination.read_bytes()
                if not content.startswith(b"%PDF-"):
                    raise ValueError("annual-report response is not a PDF")
                entry.update({
                    "selected_metadata": selected, "source_url": source_url,
                    "pdf_path": destination.relative_to(output).as_posix(),
                    "pdf_filename": filename, "pdf_sha256": sha256(content).hexdigest(),
                    "pdf_size": len(content), "acquisition_method": acquisition_method,
                })
        except Exception as exc:
            entry.update({
                "metadata_status": "FAILED", "selection_status": "ACQUISITION_FAILED",
                "failure": f"{type(exc).__name__}: {exc}",
            })
        records.append(entry)
        time.sleep(0.1)
    (output / "annual_report_provenance.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    summary = {
        "requested_count": len(universe),
        "metadata_discovered_count": sum(
            int(row.get("metadata_record_count", 0)) for row in records
        ),
        "selected_count": sum(row.get("selection_status") == "SELECTED" for row in records),
        "downloaded_count": sum("pdf_sha256" in row for row in records),
        "selection_status_counts": {
            str(key): int(value) for key, value in
            pd.Series([row["selection_status"] for row in records]).value_counts().sort_index().items()
        },
        "cutoff": CUTOFF.isoformat(), "availability_timestamp": "exchange dissemination time",
        "source_api": API,
    }
    (output / "acquisition_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire official NSE FY2025-26 annual reports.")
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed-directory", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(acquire(args.universe, args.output, args.seed_directory), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"annual-report acquisition failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
