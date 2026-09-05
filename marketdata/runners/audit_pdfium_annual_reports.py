"""Second, PDFium-based blind audit of quarantined annual reports."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "src" / "stock_ranker" / "pit_accounting_pdfium.py"
SPEC = importlib.util.spec_from_file_location("_pit_accounting_pdfium", MODULE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {MODULE}")
PARSER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PARSER
SPEC.loader.exec_module(PARSER)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_pages(packet: dict[str, Any]) -> list[int]:
    pages = {
        int(item["page"])
        for field in ("roce", "debt_to_equity")
        for item in packet["evidence"][field]
    }
    scored: list[tuple[int, int]] = []
    for item in packet["evidence"]["profit"]:
        snippet = " ".join(item.get("snippets", [])).casefold()
        score = 8 * bool(re.search(r"statement\s+of\s+profit\s+and\s+loss", snippet))
        score += 5 * ("standalone" in snippet)
        score += 3 * any(unit in snippet for unit in ("crore", "million", "lakh"))
        score += 2 * ("2026" in snippet and "2025" in snippet)
        scored.append((score, int(item["page"])))
    pages.update(page for _, page in sorted(scored, key=lambda row: (-row[0], row[1]))[:6])
    expanded = {page + delta for page in pages for delta in (-1, 0, 1) if page + delta > 0}
    return sorted(expanded)


def _same(first: dict[str, Any] | None, second: dict[str, Any] | None) -> bool:
    if first is None or second is None:
        return False
    return (
        abs(float(first["current_value"]) - float(second["current_value"])) <= 1e-12
        and abs(float(first["prior_value"]) - float(second["prior_value"])) <= 1e-12
        and (not first.get("unit") or not second.get("unit") or first.get("unit") == second.get("unit"))
    )


def _audit_one(packet: dict[str, Any], provenance: dict[str, Any], first: dict[str, Any], root_text: str,
               deep_scan: bool = False) -> dict[str, Any]:
    import pypdfium2 as pdfium

    root = Path(root_text)
    pdf_path = root / provenance["pdf_path"]
    if not pdf_path.is_file() or _hash(pdf_path) != packet["pdf_sha256"]:
        raise ValueError(f"{packet['ticker']}: source PDF missing or hash drift")
    document = pdfium.PdfDocument(pdf_path)
    requested = [page for page in _candidate_pages(packet) if page <= len(document)]
    deep_matches: list[int] = []
    if deep_scan:
        patterns = (
            re.compile(r"return\s+on\s+capital(?:\s+employed)?|\broce\b", re.I),
            re.compile(r"(?<!net\s)debt\s*[- ]?\s*(?:to\s*)?equity\s+ratio", re.I),
            re.compile(r"profit\s*/?\s*\(?loss\)?\s+(?:after\s+tax\s+)?for\s+the\s+year|profit\s+for\s+the\s+year|profit\s+after\s+tax", re.I),
        )
        for index in range(len(document)):
            text = document[index].get_textpage().get_text_bounded()
            if any(pattern.search(text) for pattern in patterns):
                deep_matches.append(index + 1)
        requested = sorted(set(requested) | set(deep_matches))
    texts: dict[int, str] = {}
    identity = False
    for page in requested:
        text = document[page - 1].get_textpage().get_text_bounded()
        texts[page] = text
        identity = identity or packet["isin"].replace(" ", "").casefold() in text.replace(" ", "").casefold()
    # Identity may be on a cover page; it corroborates but never substitutes
    # for the exact NSE metadata + packet + PDF hash chain.
    for page in range(1, min(10, len(document)) + 1):
        if identity:
            break
        text = document[page - 1].get_textpage().get_text_bounded()
        identity = packet["isin"].replace(" ", "").casefold() in text.replace(" ", "").casefold()
    candidates = {
        "roce": [item for page, text in texts.items() for item in PARSER.parse_pdfium_ratio_page("roce", page, text)],
        "debt_to_equity": [item for page, text in texts.items() for item in PARSER.parse_pdfium_ratio_page("debt_to_equity", page, text)],
        "profit": [item for page, text in texts.items() for item in PARSER.parse_pdfium_profit_page(page, text)],
    }
    selected: dict[str, Any] = {}
    field_status: dict[str, str] = {}
    comparison: dict[str, str] = {}
    for field in ("roce", "debt_to_equity", "profit"):
        value, status = PARSER.select_pdfium_disclosure(candidates[field])
        selected[field] = PARSER.serialise_pdfium_disclosure(value)
        field_status[field] = status
        original = first.get("selected", {}).get(field)
        comparison[field] = (
            "ENGINE_AGREEMENT" if _same(original, selected[field])
            else "PDFIUM_ONLY" if original is None and selected[field] is not None
            else "FIRST_ENGINE_ONLY" if original is not None and selected[field] is None
            else "BOTH_UNRESOLVED" if original is None and selected[field] is None
            else "ENGINE_DISAGREEMENT"
        )
    complete = all(selected.values())
    disagreements = [field for field, status in comparison.items() if status == "ENGINE_DISAGREEMENT"]
    status = (
        "QUARANTINED_ENGINE_DISAGREEMENT" if disagreements
        else "PDFIUM_COMPLETE_REQUIRES_EVIDENCE_REVIEW" if complete
        else "QUARANTINED_INCOMPLETE"
    )
    return {
        "ticker": packet["ticker"], "company": packet["company"], "isin": packet["isin"],
        "pdf_sha256": packet["pdf_sha256"], "source_url": packet["source_url"],
        "exchange_dissemination_timestamp": packet["exchange_dissemination_timestamp"],
        "identity_chain_status": "EXACT_NSE_METADATA_PACKET_ISIN_AND_PDF_HASH",
        "identity_found_in_pdfium_text": identity, "pages_independently_extracted": requested,
        "deep_scan_enabled": deep_scan, "deep_scan_matched_pages": deep_matches,
        "pdfium_text_sha256": {str(page): sha256(text.encode("utf-8")).hexdigest() for page, text in sorted(texts.items())},
        "selected": selected, "field_status": field_status, "engine_comparison": comparison,
        "parsed_candidates": {field: [PARSER.serialise_pdfium_disclosure(item) for item in values] for field, values in candidates.items()},
        "validation_status": status,
        "scientific_boundary": "PDFium extraction is independent of pdfminer/pdfplumber; second-only values require evidence review and disagreements remain quarantined.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packets", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--first-engine-records", type=Path, required=True)
    parser.add_argument("--acquisition-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--deep-scan", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.output_dir.exists() and not args.resume:
        parser.error(f"output directory already exists: {args.output_dir}")
    packets_all = json.loads(args.packets.read_text(encoding="utf-8"))
    provenance_all = json.loads(args.provenance.read_text(encoding="utf-8"))
    first_all = json.loads(args.first_engine_records.read_text(encoding="utf-8"))
    provenance = {row["ticker"]: row for row in provenance_all}
    first = {row["ticker"]: row for row in first_all}
    # This route addresses the first engine's quarantine only.
    packets = [packet for packet in packets_all if first.get(packet["ticker"], {}).get("validation_status") == "QUARANTINED"]
    args.output_dir.mkdir(parents=True, exist_ok=args.resume)
    partial = args.output_dir / "partial"
    partial.mkdir(exist_ok=True)
    existing = {path.stem for path in partial.glob("*.json")}
    pending = [packet for packet in packets if packet["ticker"] not in existing]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_audit_one, packet, provenance[packet["ticker"]], first[packet["ticker"]], str(args.acquisition_root), args.deep_scan): packet["ticker"]
            for packet in pending
        }
        for count, future in enumerate(as_completed(futures), start=1):
            ticker = futures[future]
            try:
                payload = {"kind": "result", "value": future.result()}
            except Exception as exc:
                payload = {"kind": "error", "value": {"ticker": ticker, "error_type": type(exc).__name__, "error": str(exc)}}
            (partial / f"{ticker}.json").write_text(_canonical(payload) + "\n", encoding="utf-8", newline="\n")
            if count % 10 == 0 or count == len(pending):
                print(f"checkpointed={len(existing) + count}/{len(packets)}", flush=True)
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(partial.glob("*.json"))]
    records = sorted((item["value"] for item in payloads if item["kind"] == "result"), key=lambda row: row["ticker"])
    errors = sorted((item["value"] for item in payloads if item["kind"] == "error"), key=lambda row: row["ticker"])
    status_counts: dict[str, int] = {}
    for record in records:
        status_counts[record["validation_status"]] = status_counts.get(record["validation_status"], 0) + 1
    complete = [record["ticker"] for record in records if record["validation_status"] == "PDFIUM_COMPLETE_REQUIRES_EVIDENCE_REVIEW"]
    summary = {
        "requested_quarantine_count": len(packets), "completed_count": len(records), "error_count": len(errors),
        "status_counts": dict(sorted(status_counts.items())), "complete_review_candidates": complete,
        "records_sha256": sha256(_canonical(records).encode("utf-8")).hexdigest(),
        "promotion_count": 0,
        "promotion_policy": "No automatic promotion; visual/source evidence review and engine agreement or adjudication are required.",
    }
    (args.output_dir / "pdfium_validation_records.json").write_text(_canonical(records) + "\n", encoding="utf-8", newline="\n")
    (args.output_dir / "pdfium_validation_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    if errors:
        (args.output_dir / "pdfium_validation_errors.json").write_text(_canonical(errors) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
