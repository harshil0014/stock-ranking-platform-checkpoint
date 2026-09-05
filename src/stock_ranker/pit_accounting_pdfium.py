"""Conservative parsing of PDFium text for statutory accounting disclosures.

This is intentionally independent of the pdfminer/pdfplumber validator.  It
accepts only directly disclosed standalone values and explicit ratio formulas.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Iterable


@dataclass(frozen=True, slots=True)
class PdfiumDisclosure:
    field: str
    page: int
    current_value: float
    prior_value: float
    unit: str
    label: str
    evidence_text: str
    formula_evidence: str
    reporting_basis: str = "STANDALONE"


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u2013", "-").replace("\u2014", "-").replace("\ufffd", "'" )).strip()


def _number(token: str) -> tuple[Decimal, bool] | None:
    raw = token.strip()
    negative = raw.startswith("(") and raw.endswith(")")
    percent = raw.endswith("%")
    raw = raw.strip("()%+").replace(",", "").strip()
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    if value in {Decimal(2024), Decimal(2025), Decimal(2026)}:
        return None
    return (-value if negative else value), percent


_TOKEN = re.compile(r"(?:\(\s*\d[\d,]*(?:\.\d+)?%?\s*\)|[-+]?\d[\d,]*(?:\.\d+)?%?)")
_NEXT_RATIO = re.compile(
    r"^(?:\(?[a-z]+\)?[.)]?\s*)?(?:current\s+ratio|debt\s+service|return\s+on\s+(?:equity|investment)|"
    r"inventory\s+turnover|trade\s+(?:receivable|payable)|net\s+(?:capital|profit))",
    re.I,
)


def _values(text: str, *, percent_first: bool) -> tuple[float, float] | None:
    parsed = [item for token in _TOKEN.findall(text) if (item := _number(token)) is not None]
    if percent_first:
        percentages = [item[0] for item in parsed if item[1]]
        if len(percentages) >= 2:
            return float(percentages[0] / 100), float(percentages[1] / 100)
    plain = [item[0] for item in parsed if not item[1]]
    if len(plain) >= 2:
        return float(plain[0]), float(plain[1])
    return None


def _standalone(text: str) -> bool:
    heading = _compact(text).casefold()[:1200]
    return "standalone" in heading and not (
        "consolidated" in heading and heading.find("consolidated") < heading.find("standalone")
    )


def _comparative_periods(text: str) -> bool:
    compacted = _compact(text)
    return ("2026" in compacted and "2025" in compacted) or (
        "2025-26" in compacted and "2024-25" in compacted
    )


def _formula(text: str, field: str) -> str | None:
    compacted = _compact(text)
    lowered = compacted.casefold()
    if field == "debt_to_equity":
        if re.search(r"net\s+debt\s*[-/]?\s*(?:to\s*)?equity", lowered):
            return None
        debt = any(term in lowered for term in ("total debt", "gross debt", "borrowings"))
        equity = any(term in lowered for term in ("shareholder's equity", "shareholders' equity", "shareholder s equity", "net worth", "networth"))
        if debt and equity:
            return "Direct issuer definition uses total/gross debt or borrowings and shareholder equity/net worth."
    else:
        numerator = any(term in lowered for term in ("ebit", "earning before interest", "earnings before interest", "profit before tax", "finance cost"))
        if numerator and "capital employed" in lowered:
            return "Direct issuer definition identifies earnings numerator and capital employed denominator."
    return None


def _logical_ratio_row(lines: list[str], index: int) -> str:
    """Join wrapped cells belonging to one ratio, stopping at the next row."""

    selected = [lines[index]]
    for line in lines[index + 1:min(len(lines), index + 6)]:
        if _NEXT_RATIO.search(line):
            break
        selected.append(line)
    return _compact(" ".join(selected))


def parse_pdfium_ratio_page(field: str, page: int, text: str) -> list[PdfiumDisclosure]:
    if field not in {"roce", "debt_to_equity"}:
        raise ValueError(f"unsupported ratio field: {field}")
    if not _standalone(text) or not _comparative_periods(text):
        return []
    lines = [_compact(line) for line in text.splitlines() if _compact(line)]
    formula = _formula(text, field)
    if formula is None:
        return []
    pattern = (
        re.compile(r"return\s+on\s+capital(?:\s+employed)?|\broce\b", re.I)
        if field == "roce" else re.compile(r"(?<!net\s)debt\s*[- ]?\s*(?:to\s*)?equity\s+ratio", re.I)
    )
    results: list[PdfiumDisclosure] = []
    for index, line in enumerate(lines):
        match = pattern.search(line)
        if not match:
            continue
        if field == "debt_to_equity" and "net debt" in line.casefold():
            continue
        window = _logical_ratio_row(lines, index)
        # Values may be wrapped across cells/lines, but the logical-row helper
        # stops before the next metric so its variance cannot leak in.
        logical_match = pattern.search(window)
        assert logical_match is not None
        value_text = window[logical_match.end():]
        if field == "debt_to_equity" and re.match(r"^[^0-9]{0,120}(?:-|\u2013)\s+(?:-|\u2013)(?:\s|$)", value_text):
            continue
        # Some issuer tables put the percent unit in the row label and render
        # the current/comparative cells as plain decimals.  Accept that layout
        # only when exactly two plain values follow the label and an explicit
        # percentage variance is also present.  This excludes page/note/year
        # integers while preserving direct table disclosures.
        plain_percent_cells = False
        if field == "roce" and len(re.findall(r"\d[\d,]*(?:\.\d+)?%", value_text)) < 2:
            parsed_tokens = [item for token in _TOKEN.findall(value_text) if (item := _number(token)) is not None]
            plain = [item for item in parsed_tokens if not item[1]]
            if "(%)" not in line or len(plain) != 2 or not any(item[1] for item in parsed_tokens):
                continue
            plain_percent_cells = True
        values = _values(value_text, percent_first=field == "roce")
        if values is None:
            continue
        current, prior = values
        if plain_percent_cells:
            current, prior = current / 100, prior / 100
        # D/E is a unitless direct ratio, not the change percentage in column 3.
        if field == "debt_to_equity" and (abs(current) > 20 or abs(prior) > 20):
            continue
        results.append(PdfiumDisclosure(
            field=field, page=page, current_value=current, prior_value=prior,
            unit="decimal return" if field == "roce" else "ratio",
            label=match.group(0), evidence_text=window, formula_evidence=formula,
        ))
    return results


def parse_pdfium_profit_page(page: int, text: str) -> list[PdfiumDisclosure]:
    if not _standalone(text) or not _comparative_periods(text):
        return []
    compacted = _compact(text)
    lowered = compacted.casefold()
    if "statement of profit and loss" not in lowered:
        return []
    heading = lowered[:1600]
    unit = "INR crore" if "crore" in heading else "INR million" if "million" in heading else "INR lakh" if "lakh" in heading else ""
    if not unit:
        return []
    pattern = re.compile(r"profit\s*/?\s*\(?loss\)?\s+(?:after\s+tax\s+)?for\s+the\s+year|profit\s+for\s+the\s+year|profit\s+after\s+tax", re.I)
    results: list[PdfiumDisclosure] = []
    for line in (_compact(item) for item in text.splitlines()):
        match = pattern.search(line)
        if not match or "margin" in line.casefold() or "ratio" in line.casefold():
            continue
        tail = line[match.end():]
        parsed = [item for token in _TOKEN.findall(tail) if (item := _number(token)) is not None and not item[1]]
        # Note references such as "(7) + (8)" may precede the two statement
        # amounts. Three or more ordinary amounts are an ambiguous subtotal
        # layout and are not silently selected.
        note_prefix = re.match(r"^\s*\(\d{1,2}\)\s*(?:\+\s*\(\d{1,2}\)\s*)?", tail)
        if note_prefix:
            tail = tail[note_prefix.end():]
            parsed = [item for token in _TOKEN.findall(tail) if (item := _number(token)) is not None and not item[1]]
        if len(parsed) == 2:
            values = float(parsed[0][0]), float(parsed[1][0])
        elif len(parsed) == 4:
            # Directors' financial-summary tables frequently place audited
            # consolidated and standalone columns side by side.  Select only
            # when the basis order and four comparative cells are explicit.
            basis = re.search(r"\b(consolidated)\s+(standalone)\b|\b(standalone)\s+(consolidated)\b", compacted, re.I)
            if basis is None:
                continue
            offset = 2 if basis.group(1) else 0
            values = float(parsed[offset][0]), float(parsed[offset + 1][0])
        else:
            continue
        results.append(PdfiumDisclosure(
            field="profit", page=page, current_value=values[0], prior_value=values[1],
            unit=unit, label=match.group(0), evidence_text=line,
            formula_evidence="Direct standalone statement profit row.",
        ))
    return results


def select_pdfium_disclosure(candidates: Iterable[PdfiumDisclosure]) -> tuple[PdfiumDisclosure | None, str]:
    items = list(candidates)
    if not items:
        return None, "NO_EXACT_PDFIUM_DISCLOSURE"
    keys = {(item.current_value, item.prior_value, item.unit) for item in items}
    if len(keys) != 1:
        return None, "CONFLICTING_PDFIUM_DISCLOSURES"
    return sorted(items, key=lambda item: item.page)[0], "VALIDATED"


def serialise_pdfium_disclosure(value: PdfiumDisclosure | None) -> dict[str, object] | None:
    return asdict(value) if value else None
