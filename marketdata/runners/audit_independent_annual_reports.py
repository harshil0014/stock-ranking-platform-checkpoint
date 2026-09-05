"""Audit annual-report evidence with pdfplumber, independently of pypdf locators."""

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
_MODULE_PATH = ROOT / "src" / "stock_ranker" / "pit_accounting_validation.py"
_SPEC = importlib.util.spec_from_file_location("_pit_accounting_validation", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load {_MODULE_PATH}")
_VALIDATION = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _VALIDATION
_SPEC.loader.exec_module(_VALIDATION)
parse_profit_page = _VALIDATION.parse_profit_page
parse_ratio_page = _VALIDATION.parse_ratio_page
unique_disclosure = _VALIDATION.unique_disclosure


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _pages_for(packet: dict[str, Any], *, all_profit_pages: bool = False) -> list[int]:
    pages = {
        int(item["page"])
        for field in ("roce", "debt_to_equity")
        for item in packet["evidence"][field]
    }
    # Broad pypdf profit locators often include dozens of narrative mentions.
    # They remain routing hints only: rank them by statutory-statement evidence
    # and independently re-extract at most four pages.  Omitting a true page can
    # reduce recall but can never create an accepted value.
    scored: list[tuple[int, int]] = []
    for item in packet["evidence"]["profit"]:
        snippet = " ".join(item.get("snippets", [])).casefold()
        score = 0
        score += 8 if re.search(r"statement\s+of\s+profit\s+and\s+loss", snippet) else 0
        score += 5 if "standalone" in snippet else 0
        score -= 8 if "consolidated" in snippet and "standalone" not in snippet else 0
        score += 3 if any(unit in snippet for unit in ("crore", "million", "lakh")) else 0
        score += 2 if "2026" in snippet and "2025" in snippet else 0
        score += 2 if re.search(r"profit\s*(?:/\s*\(?loss\)?)?\s*(?:after\s+tax\s*)?for\s+the\s+year|profit\s+after\s+tax", snippet) else 0
        scored.append((score, int(item["page"])))
    limit = len(scored) if all_profit_pages else 4
    pages.update(page for _, page in sorted(scored, key=lambda item: (-item[0], item[1]))[:limit])
    return sorted(pages)


def _pdf_for(provenance: dict[str, Any], root: Path) -> Path:
    path = root / str(provenance["pdf_path"])
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _serialise(item: Any) -> dict[str, Any] | None:
    if item is None:
        return None
    return {name: getattr(item, name) for name in item.__dataclass_fields__}


def _audit_one(
    packet: dict[str, Any], provenance: dict[str, Any], acquisition_root: str,
    all_profit_pages: bool = False,
) -> dict[str, Any]:
    # Imported only inside the isolated audit process.
    import pdfplumber

    root = Path(acquisition_root)
    pdf_path = _pdf_for(provenance, root)
    if _hash(pdf_path) != packet["pdf_sha256"] or provenance["pdf_sha256"] != packet["pdf_sha256"]:
        raise ValueError(f"{packet['ticker']}: PDF hash drift")
    candidate_pages = _pages_for(packet, all_profit_pages=all_profit_pages)
    extracted: dict[int, dict[str, str]] = {}
    context: dict[int, str] = {}
    identity_found = False
    with pdfplumber.open(pdf_path) as report:
        if not candidate_pages or candidate_pages[-1] > len(report.pages):
            raise ValueError(f"{packet['ticker']}: locator page outside PDF")
        # Accounting basis must be explicit on the candidate page itself.  The
        # first ten pages are inspected only for independent identity
        # corroboration; no earlier section heading is propagated forward.
        context_pages = set(range(1, min(11, len(report.pages) + 1))) | set(candidate_pages)
        for page_no in sorted(context_pages):
            page = report.pages[page_no - 1]
            text = page.extract_text_simple() or ""
            context[page_no] = text
            if page_no in candidate_pages:
                extracted[page_no] = {
                    "full": page.extract_text(x_tolerance=1, y_tolerance=2) or "",
                    "left_half": page.crop((0, 0, page.width / 2, page.height)).extract_text(x_tolerance=1, y_tolerance=2) or "",
                    "right_half": page.crop((page.width / 2, 0, page.width, page.height)).extract_text(x_tolerance=1, y_tolerance=2) or "",
                }
            if packet["isin"].replace(" ", "").casefold() in text.replace(" ", "").casefold():
                identity_found = True

    def section_basis(page_no: int) -> tuple[str, int | None]:
        lowered = context[page_no].casefold()
        standalone = any(term in lowered for term in (
            "audit of the standalone financial statements", "notes to standalone financial statements",
            "standalone statement of profit and loss", "standalone financial statements",
        ))
        consolidated = any(term in lowered for term in (
            "audit of the consolidated financial statements", "notes to consolidated financial statements",
            "consolidated statement of profit and loss", "consolidated financial statements",
        ))
        if standalone and not consolidated:
            return "STANDALONE", page_no
        if consolidated and not standalone:
            return "CONSOLIDATED", page_no
        return ("AMBIGUOUS", page_no) if standalone and consolidated else ("UNSTATED", None)

    basis_evidence = {page: section_basis(page) for page in candidate_pages}
    for page, variants in extracted.items():
        basis, marker_page = basis_evidence[page]
        if basis == "STANDALONE":
            prefix = f"Standalone financial statements section independently identified on PDF page {marker_page}.\n"
            extracted[page] = {name: prefix + value for name, value in variants.items()}

    ratio_candidates = {
        field: [
            candidate for page in candidate_pages for variant, text in extracted[page].items()
            for candidate in parse_ratio_page(field, page, text, extraction_variant=variant)
        ]
        for field in ("roce", "debt_to_equity")
    }
    profit_candidates = [
        candidate for page in candidate_pages for variant, text in extracted[page].items()
        for candidate in parse_profit_page(page, text, extraction_variant=variant)
    ]
    selected: dict[str, Any] = {}
    reasons: dict[str, str] = {}
    for field, candidates in (*ratio_candidates.items(), ("profit", profit_candidates)):
        disclosure, reason = unique_disclosure(candidates)
        selected[field] = _serialise(disclosure)
        reasons[field] = reason
    identity_chain_exact = (
        provenance["ticker"] == packet["ticker"] and provenance.get("isin", packet["isin"]) == packet["isin"]
        and provenance["pdf_sha256"] == packet["pdf_sha256"]
    )
    complete = identity_chain_exact and all(selected.values())
    debt = selected["debt_to_equity"]["current_value"] if selected["debt_to_equity"] else None
    status = (
        "INDEPENDENTLY_VALIDATED" if complete and debt is not None and debt >= 0
        else "VALIDATED_BUT_NEGATIVE_LEVERAGE" if complete
        else "QUARANTINED"
    )
    return {
        "ticker": packet["ticker"], "company": packet["company"], "isin": packet["isin"],
        "sector": packet["sector"], "pdf_sha256": packet["pdf_sha256"],
        "source_url": packet["source_url"],
        "exchange_dissemination_timestamp": packet["exchange_dissemination_timestamp"],
        "identity_found_by_independent_engine": identity_found,
        "identity_chain_status": "EXACT_NSE_METADATA_PACKET_ISIN_AND_PDF_HASH" if identity_chain_exact else "IDENTITY_MISMATCH",
        "section_basis_evidence": {str(page): {"basis": basis, "marker_page": marker} for page, (basis, marker) in basis_evidence.items()},
        "locator_pages_used_for_routing_only": candidate_pages,
        "independent_page_text_sha256": {
            str(page): {variant: sha256(text.encode("utf-8")).hexdigest() for variant, text in sorted(variants.items())}
            for page, variants in sorted(extracted.items())
        },
        "selected": selected,
        "parsed_candidates": {
            "roce": [_serialise(item) for item in ratio_candidates["roce"]],
            "debt_to_equity": [_serialise(item) for item in ratio_candidates["debt_to_equity"]],
            "profit": [_serialise(item) for item in profit_candidates],
        },
        "field_status": reasons, "validation_status": status,
        "scientific_boundary": "pdfplumber re-extraction; pypdf packets route pages only and do not supply accepted values",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--packets", type=Path)
    source.add_argument("--reviewed-specification", type=Path)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--acquisition-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--ticker", action="append", default=[])
    parser.add_argument("--all-profit-pages", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--finalize-partial", action="store_true")
    args = parser.parse_args(argv)
    if args.output_dir.exists() and not (args.resume or args.finalize_partial):
        parser.error(f"output directory already exists: {args.output_dir}")
    provenance_rows = json.loads(args.provenance.read_text(encoding="utf-8"))
    provenance = {row["ticker"]: row for row in provenance_rows}
    if len(provenance) != len(provenance_rows):
        parser.error("duplicate provenance ticker")
    reviewed_by_ticker: dict[str, Any] = {}
    if args.packets:
        packets = json.loads(args.packets.read_text(encoding="utf-8"))
    else:
        reviewed = json.loads(args.reviewed_specification.read_text(encoding="utf-8"))
        reviewed_by_ticker = {item["ticker"]: item for item in reviewed["records"]}
        packets = []
        for item in reviewed["records"]:
            source_row = provenance[item["ticker"]]
            packets.append({
                "ticker": item["ticker"], "company": item["company"], "isin": item["isin"],
                "sector": source_row.get("sector", ""), "pdf_sha256": item["pdf_sha256"],
                "source_url": source_row["source_url"],
                "exchange_dissemination_timestamp": source_row["selected_metadata"]["disseminationDateTime"],
                "evidence": {
                    field: [{"page": int(item[field]["page"])}] + [
                        {"page": int(extra["page"])} for extra in item[field].get("additional_evidence", [])
                    ]
                    for field in ("roce", "debt_to_equity", "profit")
                },
            })
    if args.ticker:
        requested = set(args.ticker)
        packets = [packet for packet in packets if packet["ticker"] in requested]
        missing_requested = sorted(requested - {packet["ticker"] for packet in packets})
        if missing_requested:
            parser.error(f"requested tickers absent from packet source: {missing_requested}")
    args.output_dir.mkdir(parents=True, exist_ok=args.resume or args.finalize_partial)
    partial_dir = args.output_dir / "partial"
    partial_dir.mkdir(exist_ok=True)
    existing = {path.stem for path in partial_dir.glob("*.json")}
    if not args.finalize_partial:
        pending = [packet for packet in packets if packet["ticker"] not in existing]
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    _audit_one, packet, provenance[packet["ticker"]], str(args.acquisition_root),
                    args.all_profit_pages,
                ): packet["ticker"]
                for packet in pending
            }
            for completed, future in enumerate(as_completed(futures), start=1):
                ticker = futures[future]
                try:
                    payload = {"kind": "result", "value": future.result()}
                except Exception as exc:  # preserve per-report evidence and continue the batch
                    payload = {"kind": "error", "value": {"ticker": ticker, "error_type": type(exc).__name__, "error": str(exc)}}
                (partial_dir / f"{ticker}.json").write_text(_canonical(payload) + "\n", encoding="utf-8", newline="\n")
                if completed % 10 == 0 or completed == len(pending):
                    print(f"checkpointed={len(existing) + completed}/{len(packets)}", flush=True)
    partials = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(partial_dir.glob("*.json"))
    }
    missing = sorted({packet["ticker"] for packet in packets} - set(partials))
    results = [payload["value"] for payload in partials.values() if payload["kind"] == "result"]
    errors = [payload["value"] for payload in partials.values() if payload["kind"] == "error"]
    if args.finalize_partial:
        errors.extend({"ticker": ticker, "error_type": "TimeoutError", "error": "TIMEOUT_OR_INTERRUPTED"} for ticker in missing)
    elif missing:
        parser.error(f"incomplete checkpoint set: {missing}")
    results.sort(key=lambda row: row["ticker"])
    errors.sort(key=lambda row: row["ticker"])
    (args.output_dir / "independent_validation_records.json").write_text(_canonical(results) + "\n", encoding="utf-8", newline="\n")
    calibration: dict[str, Any] | None = None
    if reviewed_by_ticker:
        checks: list[dict[str, Any]] = []
        for row in results:
            expected = reviewed_by_ticker[row["ticker"]]
            for field in ("roce", "debt_to_equity", "profit"):
                if expected["review_status"] != "COMPLETE_DIRECT_DISCLOSURE" or "canonical_decimal" not in expected[field] and field != "profit":
                    continue
                expected_current = (
                    float(expected[field]["canonical_decimal"])
                    if field != "profit" else float(expected[field]["current_value"])
                )
                expected_prior = float(expected[field]["prior_value"]) if field == "profit" else None
                matches = [
                    item for item in row["parsed_candidates"][field]
                    if abs(float(item["current_value"]) - expected_current) <= 1e-12
                    and (expected_prior is None or abs(float(item["prior_value"]) - expected_prior) <= 1e-12)
                    and int(item["page"]) == int(expected[field]["page"])
                ]
                selected_item = row["selected"][field]
                wrong_selected = bool(selected_item and abs(float(selected_item["current_value"]) - expected_current) > 1e-12)
                checks.append({
                    "ticker": row["ticker"], "field": field, "expected_current": expected_current,
                    "expected_prior": expected_prior, "exact_candidate_match": bool(matches),
                    "wrong_selected_value": wrong_selected,
                })
        calibration = {
            "check_count": len(checks),
            "exact_candidate_match_count": sum(item["exact_candidate_match"] for item in checks),
            "wrong_selected_value_count": sum(item["wrong_selected_value"] for item in checks),
            "checks": checks,
        }
        (args.output_dir / "calibration_report.json").write_text(_canonical(calibration) + "\n", encoding="utf-8", newline="\n")
    summary = {
        "schema_version": "pit_independent_accounting_validation_v1",
        "engine": "pdfplumber 0.11.9 / pdfminer.six 20251230",
        "packet_count": len(packets), "completed_count": len(results), "error_count": len(errors),
        "independently_validated_count": sum(row["validation_status"] == "INDEPENDENTLY_VALIDATED" for row in results),
        "negative_leverage_count": sum(row["validation_status"] == "VALIDATED_BUT_NEGATIVE_LEVERAGE" for row in results),
        "quarantined_count": sum(row["validation_status"] == "QUARANTINED" for row in results),
        "errors": errors,
        "calibration": calibration and {key: value for key, value in calibration.items() if key != "checks"},
        "auto_promotion_performed": False,
        "scientific_boundary": "Independent candidate validation only; no V2 mapping, score, rank, or frozen artifact mutation.",
    }
    summary["records_sha256"] = _hash(args.output_dir / "independent_validation_records.json")
    (args.output_dir / "independent_validation_summary.json").write_text(_canonical(summary) + "\n", encoding="utf-8", newline="\n")
    print(_canonical(summary))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
