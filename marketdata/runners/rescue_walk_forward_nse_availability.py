"""Recover historical annual-report availability from official NSE announcements only."""

from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import http.cookiejar
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
API = "https://www.nseindia.com/api/corporate-announcements"
OFFICIAL_HOSTS = {"www.nseindia.com", "nsearchives.nseindia.com", "archives.nseindia.com"}
USER_AGENT = "Mozilla/5.0 (compatible; StockRankingResearch/1.0)"
MAX_JSON_BYTES = 8_000_000
MAX_PDF_BYTES = 150_000_000
FINAL_STATUSES = {
    "RESCUED_EXACT_NSE_DISSEMINATION",
    "NOT_RESCUED_NO_EXACT_EVIDENCE",
    "NOT_RESCUED_POST_CUTOFF",
    "NOT_RESCUED_AMBIGUOUS_ATTACHMENT",
}

FY_VARIANTS = {
    "2021-22": (r"2021\s*[-_/]?\s*22", r"fy\s*2022", r"financial year ended march 31,?\s*2022"),
    "2022-23": (
        r"2022\s*[-_/]?\s*23", r"fy\s*2023", r"fiscal\s+2023",
        r"annual\s*_?report\s*_?2023", r"annualreport2023",
        r"financial year ended march 31,?\s*2023",
    ),
}
PROHIBITED_SUBJECTS = re.compile(
    r"newspaper|business responsibility|\bbrsr\b|book closure|corrigendum", re.I
)
PROMISE_ONLY = re.compile(r"shall be sent|will be sent|will be uploaded|in due course", re.I)
ANNUAL_REPORT = re.compile(r"integrated\s+annual\s+report|annual\s+report|annualreport|annual_report", re.I)
ATTACHED_REPORT = re.compile(
    r"(?:attached|enclosed|herewith|submission|about).{0,180}(?:integrated\s+)?annual\s+report|"
    r"annual\s+report.{0,180}(?:attached|enclosed|herewith)", re.I | re.S,
)


def _timestamp(value: object) -> datetime:
    return datetime.strptime(str(value), "%d-%b-%Y %H:%M:%S").replace(
        tzinfo=ZoneInfo("Asia/Kolkata")
    )


def _official_pdf(url: object) -> bool:
    parsed = urlparse(str(url))
    return (
        parsed.scheme == "https"
        and parsed.hostname in OFFICIAL_HOSTS
        and parsed.path.lower().endswith(".pdf")
    )


def _matches_fy(text: str, required_fy: str) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in FY_VARIANTS[required_fy])


def classify_announcement(
    row: dict[str, object], *, ticker: str, required_fy: str, cutoff: datetime,
) -> tuple[str, str]:
    """Classify one NSE announcement without treating broadcast time as availability."""
    if str(row.get("symbol", "")) != ticker:
        return "NOT_RESCUED_AMBIGUOUS_ATTACHMENT", "historical security identity mismatch"
    attachment = str(row.get("attchmntFile", ""))
    if not _official_pdf(attachment):
        return "NOT_RESCUED_AMBIGUOUS_ATTACHMENT", "missing official NSE PDF attachment"
    subject = str(row.get("desc", ""))
    details = str(row.get("attchmntText", ""))
    identity_text = f"{subject} {details} {Path(urlparse(attachment).path).name}"
    if not ANNUAL_REPORT.search(identity_text) or not _matches_fy(identity_text, required_fy):
        return "NOT_RESCUED_AMBIGUOUS_ATTACHMENT", "attachment is not an exact required-FY annual report"
    if PROHIBITED_SUBJECTS.search(subject):
        return "NOT_RESCUED_AMBIGUOUS_ATTACHMENT", "prohibited broad announcement subject"
    filename = Path(urlparse(attachment).path).name
    filename_identifies_report = bool(ANNUAL_REPORT.search(filename) and _matches_fy(identity_text, required_fy))
    if PROMISE_ONLY.search(details) and not ATTACHED_REPORT.search(details) and not filename_identifies_report:
        return "NOT_RESCUED_AMBIGUOUS_ATTACHMENT", "announcement promises later report availability"
    if not ATTACHED_REPORT.search(details) and not filename_identifies_report:
        return "NOT_RESCUED_AMBIGUOUS_ATTACHMENT", "announcement does not identify attached annual report"
    try:
        dissemination = _timestamp(row["exchdisstime"])
    except (KeyError, TypeError, ValueError):
        return "NOT_RESCUED_NO_EXACT_EVIDENCE", "exact exchange dissemination timestamp absent"
    if dissemination > cutoff:
        return "NOT_RESCUED_POST_CUTOFF", "exact annual report was disseminated after cutoff"
    return "RESCUED_EXACT_NSE_DISSEMINATION", "exact required-FY report attached before cutoff"


class NSEClient:
    def __init__(self) -> None:
        jar = http.cookiejar.CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(jar))
        self._read(PAGE, "text/html,application/xhtml+xml", 5_000_000)

    def _read(self, url: str, accept: str, limit: int) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
            raise ValueError(f"refusing non-official NSE URL: {url}")
        request = Request(url, headers={
            "User-Agent": USER_AGENT, "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9", "Referer": PAGE,
        })
        with self._opener.open(request, timeout=120) as response:
            content = response.read(limit + 1)
        if not content or len(content) > limit:
            raise ValueError(f"invalid response size: {url}")
        return content

    def announcements(self, ticker: str, from_date: str, to_date: str) -> list[dict[str, object]]:
        url = f"{API}?{urlencode({'index': 'equities', 'symbol': ticker, 'from_date': from_date, 'to_date': to_date})}"
        payload = json.loads(self._read(url, "application/json", MAX_JSON_BYTES))
        if not isinstance(payload, list):
            raise ValueError(f"NSE announcements response is not a list: {ticker}")
        return payload

    def pdf(self, url: str) -> bytes:
        content = self._read(url, "application/pdf", MAX_PDF_BYTES)
        if not content.startswith(b"%PDF-"):
            raise ValueError("official NSE attachment is not a PDF")
        return content


def _unverified(source_cache: Path, ranking_date: str) -> list[dict[str, object]]:
    path = source_cache / ranking_date / "annual_reports/annual_report_provenance.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return sorted(
        (row for row in rows if row["selection_status"] == "UNVERIFIED_FILING_AVAILABILITY"),
        key=lambda row: str(row["ticker"]),
    )


def acquire(source_cache: Path, output: Path) -> dict[str, object]:
    if output.exists():
        raise ValueError(f"availability-rescue output already exists: {output}")
    output.mkdir(parents=True)
    client = NSEClient()
    snapshots = []
    configurations = (
        ("2022-08-05", "2021-22", "01-04-2022", "30-09-2022"),
        ("2023-08-07", "2022-23", "01-04-2023", "30-09-2023"),
    )
    for ranking_date, required_fy, from_date, to_date in configurations:
        cutoff = datetime.fromisoformat(f"{ranking_date}T15:30:00+05:30")
        date_root = output / ranking_date
        metadata_root = date_root / "metadata"
        pdf_root = date_root / "pdf"
        metadata_root.mkdir(parents=True)
        pdf_root.mkdir()
        attempts = []
        for original in _unverified(source_cache, ranking_date):
            ticker = str(original["ticker"])
            rows = client.announcements(ticker, from_date, to_date)
            metadata_path = metadata_root / f"{ticker}.json"
            metadata_path.write_text(
                json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8", newline="\n",
            )
            candidates = []
            for row in rows:
                blob = " ".join(str(row.get(key, "")) for key in ("desc", "attchmntText", "attchmntFile"))
                if ANNUAL_REPORT.search(blob):
                    status, reason = classify_announcement(
                        row, ticker=ticker, required_fy=required_fy, cutoff=cutoff,
                    )
                    candidates.append({"status": status, "reason": reason, "record": row})
            rescued = [row for row in candidates if row["status"] == "RESCUED_EXACT_NSE_DISSEMINATION"]
            post_cutoff = [row for row in candidates if row["status"] == "NOT_RESCUED_POST_CUTOFF"]
            ambiguous = [row for row in candidates if row["status"] == "NOT_RESCUED_AMBIGUOUS_ATTACHMENT"]
            if rescued:
                selected = max(
                    rescued,
                    key=lambda item: (_timestamp(item["record"]["exchdisstime"]), str(item["record"].get("seq_id", ""))),
                )
                content = client.pdf(str(selected["record"]["attchmntFile"]))
                destination = pdf_root / f"{ticker}__{Path(urlparse(str(selected['record']['attchmntFile'])).path).name}"
                destination.write_bytes(content)
                final_status = "RESCUED_EXACT_NSE_DISSEMINATION"
                final_reason = selected["reason"]
                selected_record = selected["record"]
                pdf_path = destination.relative_to(output).as_posix()
                pdf_sha256 = sha256(content).hexdigest()
            elif post_cutoff:
                selected = min(post_cutoff, key=lambda item: _timestamp(item["record"]["exchdisstime"]))
                final_status = "NOT_RESCUED_POST_CUTOFF"
                final_reason = selected["reason"]
                selected_record = selected["record"]
                pdf_path = None
                pdf_sha256 = None
            elif ambiguous:
                final_status = "NOT_RESCUED_AMBIGUOUS_ATTACHMENT"
                final_reason = "; ".join(sorted({str(item["reason"]) for item in ambiguous}))
                selected_record = None
                pdf_path = None
                pdf_sha256 = None
            else:
                final_status = "NOT_RESCUED_NO_EXACT_EVIDENCE"
                final_reason = "official NSE announcement history contains no exact required-FY annual-report evidence"
                selected_record = None
                pdf_path = None
                pdf_sha256 = None
            attempts.append({
                "ticker": ticker,
                "company": next((str(row.get("sm_name")) for row in rows if row.get("symbol") == ticker), ""),
                "required_fiscal_year": required_fy,
                "cutoff": cutoff.isoformat(),
                "annual_report_archive_dissemination": None,
                "original_archive_selection_status": original["selection_status"],
                "original_archive_metadata_sha256": original["metadata_sha256"],
                "availability_rescue": {
                    "source": "NSE_CORPORATE_ANNOUNCEMENT",
                    "api_endpoint": API,
                    "metadata_path": metadata_path.relative_to(output).as_posix(),
                    "metadata_sha256": sha256(metadata_path.read_bytes()).hexdigest(),
                    "candidate_record_count": len(candidates),
                    "evidence_status": final_status,
                    "reason": final_reason,
                    "exchange_dissemination_timestamp": selected_record.get("exchdisstime") if selected_record else None,
                    "broadcast_timestamp": selected_record.get("an_dt") if selected_record else None,
                    "source_identifier": selected_record.get("seq_id") if selected_record else None,
                    "subject": selected_record.get("desc") if selected_record else None,
                    "details": selected_record.get("attchmntText") if selected_record else None,
                    "attachment_url": selected_record.get("attchmntFile") if selected_record else None,
                    "attachment_path": pdf_path,
                    "attachment_sha256": pdf_sha256,
                },
            })
            time.sleep(0.15)
        provenance_path = date_root / "availability_rescue_provenance.json"
        provenance_path.write_text(
            json.dumps(attempts, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n",
        )
        audit_provenance = []
        for attempt in attempts:
            rescue = attempt["availability_rescue"]
            selected = rescue["evidence_status"] == "RESCUED_EXACT_NSE_DISSEMINATION"
            audit_provenance.append({
                "ticker": attempt["ticker"],
                "selection_status": "SELECTED" if selected else rescue["evidence_status"],
                "selected_metadata": {
                    "fileName": rescue["attachment_url"],
                    "broadcast_dttm": rescue["broadcast_timestamp"],
                    "disseminationDateTime": rescue["exchange_dissemination_timestamp"],
                } if selected else None,
                "source_url": rescue["attachment_url"] if selected else None,
                "pdf_path": str(rescue["attachment_path"]).removeprefix(f"{ranking_date}/") if selected else None,
                "pdf_sha256": rescue["attachment_sha256"] if selected else None,
            })
        (date_root / "annual_report_provenance.json").write_text(
            json.dumps(audit_provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n",
        )
        counts = {status: 0 for status in sorted(FINAL_STATUSES)}
        for row in attempts:
            counts[row["availability_rescue"]["evidence_status"]] += 1
        snapshots.append({
            "ranking_date": ranking_date, "required_fiscal_year": required_fy,
            "attempted_count": len(attempts), "status_counts": counts,
            "provenance_path": provenance_path.relative_to(output).as_posix(),
            "provenance_sha256": sha256(provenance_path.read_bytes()).hexdigest(),
        })
    summary = {
        "schema_version": 1,
        "source_policy": "OFFICIAL_NSE_ONLY",
        "outcome_data_acquired": False,
        "snapshots": snapshots,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rescue blank historical annual-report availability from NSE.")
    parser.add_argument("--source-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(acquire(args.source_cache, args.output), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"NSE availability rescue failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
