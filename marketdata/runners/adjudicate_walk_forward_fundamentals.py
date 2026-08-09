"""Build deterministic, outcome-blind annual-report review packets."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys


PAGE_MARKER = re.compile(r"\n=== PDF PAGE (\d+) ===\n")
STANDALONE_AUDIT = re.compile(
    r"(?:independent auditor.{0,400}standalone financial statements|"
    r"report on the audit of the standalone financial statements|"
    r"auditors? report on the standalone financial statements|"
    r"report on the audit.{0,120}standalone.{0,40}statements)", re.I | re.S
)
CONSOLIDATED_AUDIT = re.compile(
    r"(?:independent auditor.{0,400}consolidated financial statements|"
    r"report on the audit of the consolidated financial statements|"
    r"report on the audit.{0,120}consolidated.{0,40}statements)", re.I | re.S
)
STANDALONE_PROFIT = re.compile(
    r"(?:standalone\s+)?statement of profit and loss", re.I | re.S
)
ROCE = re.compile(r"\b(?:return\s+on\s+capital\s+employed|ROCE)\b", re.I)
DEBT_EQUITY = re.compile(
    r"\bdebt\s*[-/]?\s*(?:to\s*)?equity(?:\s+ratio)?\b|\bdebt-equity\b", re.I
)
PROFIT = re.compile(r"\b(?:profit\s+for\s+the\s+year|profit\s+after\s+tax)\b", re.I)


def split_pages(text: str) -> dict[int, str]:
    parts = PAGE_MARKER.split(text)
    return {int(parts[index]): parts[index + 1] for index in range(1, len(parts), 2)}


def _excerpt(text: str, pattern: re.Pattern[str], radius: int = 550) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    result: list[str] = []
    for match in pattern.finditer(normalized):
        value = normalized[max(0, match.start() - radius):match.end() + radius]
        if value not in result:
            result.append(value)
    return result[:8]


def identify_statement_ranges(pages: dict[int, str]) -> dict[str, int | None]:
    standalone_starts = [number for number, text in pages.items() if STANDALONE_AUDIT.search(text)]
    standalone_start = min(standalone_starts) if standalone_starts else None
    consolidated_starts = [
        number for number, text in pages.items()
        if CONSOLIDATED_AUDIT.search(text) and (standalone_start is None or number > standalone_start)
    ]
    consolidated_start = min(consolidated_starts) if consolidated_starts else None
    standalone_end = consolidated_start - 1 if consolidated_start is not None else max(pages, default=None)
    return {
        "standalone_start_page": standalone_start,
        "standalone_end_page": standalone_end,
        "consolidated_start_page": consolidated_start,
        "consolidated_end_page": max(pages, default=None) if consolidated_start is not None else None,
    }


def build_packet(audit: dict[str, object], text: str, ranking_date: str, required_fy: str) -> dict[str, object]:
    pages = split_pages(text)
    ranges = identify_statement_ranges(pages)
    start, end = ranges["standalone_start_page"], ranges["standalone_end_page"]
    in_standalone = {
        number: page for number, page in pages.items()
        if start is not None and end is not None and start <= number <= end
    }

    def candidates(pattern: re.Pattern[str]) -> list[dict[str, object]]:
        return [
            {"page": number, "excerpts": _excerpt(page, pattern)}
            for number, page in in_standalone.items() if pattern.search(page)
        ]

    profit_pages = [
        {"page": number, "excerpts": _excerpt(page, PROFIT)}
        for number, page in in_standalone.items()
        if STANDALONE_PROFIT.search(page) and PROFIT.search(page)
    ]
    metadata = audit.get("selected_metadata") or {}
    return {
        "schema_version": 1,
        "ticker": audit["ticker"],
        "ranking_date": ranking_date,
        "required_fiscal_year": required_fy,
        "pdf_filename": metadata.get("fileName"),
        "pdf_sha256": audit.get("pdf_sha256"),
        "broadcast_timestamp": metadata.get("broadcast_dttm"),
        "dissemination_timestamp": metadata.get("disseminationDateTime"),
        "section_boundaries": ranges,
        "roce": {"candidate_pages": candidates(ROCE)},
        "debt_to_equity": {"candidate_pages": candidates(DEBT_EQUITY)},
        "profit": {"candidate_pages": profit_pages},
        "review_state": "PENDING_MANUAL_REVIEW",
        "review_reason": "Evidence packet generated; an explicit final adjudication is required.",
    }


def adjudicate(cache: Path, output: Path, ranking_date: str, required_fy: str) -> dict[str, object]:
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    output.mkdir(parents=True)
    audits = json.loads((cache / "annual_report_audit/candidate_audit.json").read_text(encoding="utf-8"))
    rows = []
    for audit in sorted(audits, key=lambda row: row["ticker"]):
        if audit.get("selection_status") != "SELECTED" or audit.get("audit_status") != "EXTRACTED":
            continue
        text_path = cache / "annual_report_audit" / str(audit["text_path"])
        if sha256(text_path.read_bytes()).hexdigest() != audit["text_sha256"]:
            raise ValueError(f"extracted text hash mismatch: {audit['ticker']}")
        packet = build_packet(audit, text_path.read_text(encoding="utf-8"), ranking_date, required_fy)
        packet_path = output / f"{audit['ticker']}.json"
        packet_path.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n",
        )
        rows.append({
            "ticker": audit["ticker"],
            "packet": packet_path.name,
            "standalone_start_page": packet["section_boundaries"]["standalone_start_page"],
            "standalone_end_page": packet["section_boundaries"]["standalone_end_page"],
            "consolidated_start_page": packet["section_boundaries"]["consolidated_start_page"],
            "roce_pages": [row["page"] for row in packet["roce"]["candidate_pages"]],
            "debt_to_equity_pages": [row["page"] for row in packet["debt_to_equity"]["candidate_pages"]],
            "profit_pages": [row["page"] for row in packet["profit"]["candidate_pages"]],
            "review_state": packet["review_state"],
        })
    inventory = {"schema_version": 1, "ranking_date": ranking_date, "required_fiscal_year": required_fy, "rows": rows}
    (output / "inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return inventory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build cached annual-report adjudication packets.")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ranking-date", required=True)
    parser.add_argument("--required-fy", required=True)
    args = parser.parse_args(argv)
    try:
        result = adjudicate(args.cache, args.output, args.ranking_date, args.required_fy)
        print(json.dumps({"packet_count": len(result["rows"])}, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"fundamental adjudication failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
