"""Extract conservative annual-report disclosure candidates with pypdf."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import re
import subprocess
import sys

import pandas as pd

PATTERNS = {
    "roce": re.compile(r"\b(?:return\s+on\s+capital\s+employed|ROCE)\b", re.I),
    "debt_to_equity": re.compile(
        r"\b(?:debt\s*[-/]?\s*(?:to\s*)?equity(?:\s+ratio)?|debt-equity)\b", re.I
    ),
    "profit": re.compile(
        r"\b(?:profit\s+after\s+tax|profit\s+for\s+the\s+year|net\s+profit|PAT)\b", re.I
    ),
}
SUBSTITUTES = re.compile(
    r"\b(?:return\s+on\s+(?:assets|equity|invested\s+capital|net\s+worth)|ROA|ROE|ROEV|ROIC)\b",
    re.I,
)
FORMULA = re.compile(r"(?:formula|calculated\s+as|computed\s+as|=|numerator|denominator)", re.I)


def _extractor_version() -> str:
    try:
        return version("pypdf")
    except PackageNotFoundError:
        return "UNAVAILABLE_IN_ORCHESTRATOR_ENVIRONMENT"


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _snippets(text: str, pattern: re.Pattern[str], radius: int = 700) -> list[str]:
    normalized = _normalize(text)
    snippets = []
    for match in pattern.finditer(normalized):
        candidate = normalized[max(0, match.start() - radius):match.end() + radius]
        if candidate not in snippets:
            snippets.append(candidate)
        if len(snippets) == 8:
            break
    return snippets


def _candidate_pages(text_dump: str) -> list[dict[str, object]]:
    records = []
    parts = re.split(r"\n=== PDF PAGE (\d+) ===\n", text_dump)
    for index in range(1, len(parts), 2):
        page_number = int(parts[index])
        text = parts[index + 1]
        candidates = {name: _snippets(text, pattern) for name, pattern in PATTERNS.items()}
        substitute = _snippets(text, SUBSTITUTES)
        if any(candidates.values()) or substitute:
            records.append({
                "page": page_number, "roce": candidates["roce"],
                "debt_to_equity": candidates["debt_to_equity"],
                "profit": candidates["profit"], "substitutes": substitute,
                "formula_language": any(
                    FORMULA.search(snippet)
                    for values in candidates.values() for snippet in values
                ),
            })
    return records


def _worker(pdf: Path, text_path: Path, candidate_path: Path) -> int:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(pdf, strict=True)
        parse_mode = "STRICT"
    except PdfReadError:
        reader = PdfReader(pdf, strict=False)
        parse_mode = "LENIENT_XREF_RECOVERY"
    if reader.is_encrypted:
        raise ValueError("encrypted annual report")
    text_dump = "".join(
        f"\n=== PDF PAGE {page_number} ===\n{page.extract_text() or ''}"
        for page_number, page in enumerate(reader.pages, start=1)
    )
    text_path.write_text(text_dump, encoding="utf-8", newline="\n")
    candidate_path.write_text(
        json.dumps({"page_count": len(reader.pages), "pdf_parse_mode": parse_mode,
                    "candidate_pages": _candidate_pages(text_dump)},
                   ensure_ascii=False, sort_keys=True),
        encoding="utf-8", newline="\n",
    )
    return 0


def _audit_entry(
    entry: dict[str, object], acquisition_root: Path, output: Path, timeout_seconds: int = 300,
) -> dict[str, object]:
    row: dict[str, object] = {
        "ticker": entry["ticker"], "selection_status": entry["selection_status"]
    }
    if entry["selection_status"] != "SELECTED":
        row["audit_status"] = "NO_ELIGIBLE_ANNUAL_REPORT"
        return row
    try:
        pdf = acquisition_root / str(entry["pdf_path"])
        if sha256(pdf.read_bytes()).hexdigest() != entry["pdf_sha256"]:
            raise ValueError("PDF hash mismatch")
        text_path = output / "text" / f"{entry['ticker']}.txt"
        candidate_path = output / "candidates" / f"{entry['ticker']}.json"
        if not text_path.is_file() or not candidate_path.is_file():
            # A text-only checkpoint may be an interrupted direct write. Re-run
            # the isolated worker instead of trusting or repairing partial text.
            try:
                subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--worker-pdf", str(pdf),
                     "--worker-text", str(text_path), "--worker-candidates", str(candidate_path)],
                    check=True, timeout=timeout_seconds, capture_output=True, text=True,
                )
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError(f"PDF extraction exceeded {timeout_seconds} seconds") from exc
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or exc.stdout or "worker failed").strip()[-1000:]
                raise RuntimeError(f"PDF worker failed: {detail}") from exc
        candidate_data = json.loads(candidate_path.read_text(encoding="utf-8"))
        page_records = candidate_data["candidate_pages"]
        row.update({
            "audit_status": "EXTRACTED", "page_count": candidate_data["page_count"],
            "text_path": text_path.relative_to(output).as_posix(),
            "text_sha256": sha256(text_path.read_bytes()).hexdigest(),
            "pdf_sha256": entry["pdf_sha256"], "source_url": entry["source_url"],
            "selected_metadata": entry["selected_metadata"],
            "pdf_parse_mode": candidate_data.get("pdf_parse_mode", "LEGACY_STRICT"),
            "candidate_pages": page_records,
            "roce_candidate_page_count": sum(bool(item["roce"]) for item in page_records),
            "debt_equity_candidate_page_count": sum(bool(item["debt_to_equity"]) for item in page_records),
            "profit_candidate_page_count": sum(bool(item["profit"]) for item in page_records),
        })
    except Exception as exc:
        row.update({"audit_status": "PDF_EXTRACTION_FAILED", "failure": f"{type(exc).__name__}: {exc}"})
    return row


def audit(
    acquisition_root: Path, output: Path, *, resume: bool = False, workers: int = 1,
    timeout_seconds: int = 300,
) -> dict[str, object]:
    if not 1 <= workers <= 8:
        raise ValueError("workers must be between 1 and 8")
    if not 60 <= timeout_seconds <= 900:
        raise ValueError("timeout_seconds must be between 60 and 900")
    if output.exists() and not resume:
        raise ValueError(f"output already exists: {output}")
    output.mkdir(parents=True, exist_ok=resume)
    text_dir = output / "text"
    text_dir.mkdir(exist_ok=resume)
    candidate_dir = output / "candidates"
    candidate_dir.mkdir(exist_ok=resume)
    provenance = json.loads(
        (acquisition_root / "annual_report_provenance.json").read_text(encoding="utf-8")
    )
    entries = sorted(provenance, key=lambda item: item["ticker"])
    if workers == 1:
        results = [_audit_entry(entry, acquisition_root, output, timeout_seconds) for entry in entries]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(
                lambda entry: _audit_entry(entry, acquisition_root, output, timeout_seconds), entries
            ))
    (output / "candidate_audit.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    summary = {
        "requested_count": len(results),
        "extracted_count": sum(row["audit_status"] == "EXTRACTED" for row in results),
        "extraction_failed_count": sum(row["audit_status"] == "PDF_EXTRACTION_FAILED" for row in results),
        "no_report_count": sum(row["audit_status"] == "NO_ELIGIBLE_ANNUAL_REPORT" for row in results),
        "roce_candidate_count": sum(int(row.get("roce_candidate_page_count", 0)) > 0 for row in results),
        "debt_equity_candidate_count": sum(int(row.get("debt_equity_candidate_page_count", 0)) > 0 for row in results),
        "profit_candidate_count": sum(int(row.get("profit_candidate_page_count", 0)) > 0 for row in results),
        "extractor": "pypdf", "extractor_version": _extractor_version(),
        "extractor_license": "BSD-3-Clause",
        "pdf_parse_mode_counts": {
            str(key): int(value) for key, value in pd.Series([
                row.get("pdf_parse_mode", "NOT_EXTRACTED") for row in results
            ]).value_counts().sort_index().items()
        },
    }
    (output / "audit_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit official NSE annual-report PDF disclosures.")
    parser.add_argument("--acquisition-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--worker-pdf", type=Path)
    parser.add_argument("--worker-text", type=Path)
    parser.add_argument("--worker-candidates", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.worker_pdf:
            if args.worker_text is None or args.worker_candidates is None:
                raise ValueError("worker output paths are required")
            return _worker(args.worker_pdf, args.worker_text, args.worker_candidates)
        if args.acquisition_root is None or args.output is None:
            raise ValueError("acquisition root and output are required")
        print(json.dumps(audit(
            args.acquisition_root, args.output, resume=args.resume, workers=args.workers,
            timeout_seconds=args.timeout_seconds,
        ), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"annual-report audit failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
