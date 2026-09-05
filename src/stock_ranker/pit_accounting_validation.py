"""Conservative, engine-independent annual-report accounting validation.

The existing pypdf pass is deliberately only a page locator.  This module
validates evidence extracted independently by another engine.  It never
derives ROCE or debt-to-equity from statement components and never promotes a
dash, blank, conflicting value, or unclear reporting basis.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Iterable


_SPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"(?<![A-Za-z])(?:\((?:\s*\d[\d,]*(?:\.\d+)?\s*)\)|[-+]?\d[\d,]*(?:\.\d+)?%?)")
_YEAR = {2024, 2025, 2026}


@dataclass(frozen=True, slots=True)
class ParsedDisclosure:
    field: str
    page: int
    current_value: float
    prior_value: float
    explicit_percent: bool
    reporting_basis: str
    label: str
    evidence_text: str
    formula_evidence: str
    unit: str = ""
    extraction_variant: str = "full"


def compact(value: str) -> str:
    return _SPACE.sub(" ", value.replace("\u2013", "-").replace("\u2014", "-")).strip()


def _value(token: str) -> tuple[Decimal, bool] | None:
    raw = compact(token)
    negative = raw.startswith("(") and raw.endswith(")")
    percent = raw.endswith("%")
    raw = raw.strip("()%+").replace(",", "").strip()
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    if negative:
        value = -value
    if int(abs(value)) in _YEAR and value == int(value):
        return None
    return value, percent


def _numeric_pairs(text: str, *, prefer_percent: bool) -> list[tuple[Decimal, Decimal, bool]]:
    parsed = [value for token in _NUMBER.findall(text) if (value := _value(token)) is not None]
    if prefer_percent:
        percents = [item for item in parsed if item[1]]
        if len(percents) >= 2:
            return [(percents[0][0], percents[1][0], True)]
    # Ratio values in statutory tables are small.  Exclude note/page indices
    # and percentage-change columns by preferring the first two decimal tokens.
    decimals = [item for item in parsed if not item[1] and ("." in str(item[0]) or abs(item[0]) < 2)]
    if len(decimals) >= 2:
        return [(decimals[-2][0], decimals[-1][0], False)]
    return []


def _basis(text: str) -> str:
    lowered = compact(text).casefold()
    # Page headings and financial-statement headers outrank incidental mentions
    # later on a notes page.
    heading = lowered[:700]
    standalone = "standalone" in heading
    consolidated = "consolidated" in heading
    if standalone and not consolidated:
        return "STANDALONE"
    if standalone and consolidated:
        return "MIXED_OR_AMBIGUOUS"
    return "UNSTATED"


def _windows(lines: list[str], patterns: Iterable[re.Pattern[str]], radius: int = 4) -> Iterable[tuple[str, str]]:
    for index, line in enumerate(lines):
        if any(pattern.search(line) for pattern in patterns):
            start = max(0, index - radius)
            end = min(len(lines), index + radius + 1)
            yield line, compact(" ".join(lines[start:end]))


def parse_ratio_page(field: str, page: int, text: str, *, extraction_variant: str = "full") -> list[ParsedDisclosure]:
    """Parse only directly disclosed issuer ratios from one extracted page."""

    if field not in {"roce", "debt_to_equity"}:
        raise ValueError(f"unsupported ratio field: {field}")
    lines = [compact(line) for line in text.splitlines() if compact(line)]
    patterns = (
        (re.compile(r"return\s+on\s+capital(?:\s+employed)?", re.I), re.compile(r"\broce\b", re.I))
        if field == "roce"
        else (re.compile(r"debt\s*[-/]?\s*(?:to\s*)?equity\s+ratio", re.I),)
    )
    results: list[ParsedDisclosure] = []
    page_lowered = compact(text).casefold()
    for index, row in enumerate(lines):
        match = next((pattern.search(row) for pattern in patterns if pattern.search(row)), None)
        if match is None:
            continue
        if field == "debt_to_equity":
            prefix = row[max(0, match.start() - 20):match.start()].casefold()
            following = compact(" ".join(lines[index:min(len(lines), index + 5)]))[match.start():].casefold()
            # Net-debt/equity subtracts cash and is a different financial
            # concept.  It cannot satisfy V2's direct debt-to-equity input.
            if re.search(r"\bnet\s*$", prefix) or "cash and cash equivalents" in following:
                continue
        label = match.group(0)
        # Limit numeric parsing to the disclosed table row, while retaining a
        # little surrounding text for numerator/denominator evidence.
        value_window = row[match.end():]
        if not _numeric_pairs(value_window, prefer_percent=field == "roce") and index + 1 < len(lines):
            next_line = lines[index + 1]
            # A wrapped value row is allowed, but another named ratio is not.
            # Without this boundary an empty D/E row could steal values from
            # the following interest-coverage/current-ratio row.
            other_ratio = re.search(
                r"(?:interest|debt service)\s+coverage\s+ratio|current\s+ratio|"
                r"return\s+on\s+|inventory\s+turnover|trade\s+(?:receivable|payable)",
                next_line,
                re.I,
            )
            if other_ratio is None:
                value_window = compact(value_window + " " + next_line)
        window = compact(" ".join(lines[max(0, index - 2):min(len(lines), index + 5)]))
        local_lowered = window.casefold()
        if field == "roce":
            formula_ok = (
                any(term in local_lowered for term in ("ebit", "profit before tax", "finance cost", "earnings before interest"))
                and "capital employed" in local_lowered
            )
        else:
            formula_ok = (
                any(term in local_lowered for term in ("total debt", "gross debt", "borrowings", "debt over"))
                and any(term in local_lowered for term in ("shareholder", "equity", "networth", "net worth"))
            )
        if not formula_ok or "2026" not in compact(text) or "2025" not in compact(text):
            continue
        pairs = _numeric_pairs(value_window, prefer_percent=field == "roce")
        for current, prior, percent in pairs:
            # Some statutory tables put the percent unit in its own column,
            # leaving ratio values unadorned.  Treat that as percent only when
            # the unit appears between the ROCE label and the first value.
            if field == "roce" and not percent and re.match(r"^[^0-9]{0,100}%", value_window):
                percent = True
            unit_context = compact(" ".join(lines[max(0, index - 1):min(len(lines), index + 3)])).casefold()
            if field == "roce" and not percent and "(in" in unit_context and "%)" in unit_context:
                percent = True
            # Explicit percentages become decimal returns.  Plain issuer ratios
            # remain exactly as disclosed (e.g. 0.09, not 0.0009).
            divisor = Decimal(100) if percent else Decimal(1)
            results.append(ParsedDisclosure(
                field=field,
                page=page,
                current_value=float(current / divisor),
                prior_value=float(prior / divisor),
                explicit_percent=percent,
                reporting_basis=_basis(text),
                label=label,
                evidence_text=window,
                formula_evidence=window,
                extraction_variant=extraction_variant,
            ))
    return results


def _profit_unit(text: str) -> str:
    # Statement units belong in the header; narrative mentions later on the
    # page cannot determine the unit.
    lowered = compact(text).casefold()[:1200]
    if "crore" in lowered:
        return "INR crore"
    if "million" in lowered:
        return "INR million"
    if "lakh" in lowered:
        return "INR lakh"
    for pattern, unit in (
        (r"(?:rs\.?|inr|₹)\s*(?:in\s*)?(?:crore|crores)|(?:amounts?|figures)\s+in\s+(?:₹\s*)?(?:crore|crores)", "INR crore"),
        (r"(?:rs\.?|inr|₹)\s*(?:in\s*)?(?:million|millions)|(?:amounts?|figures)\s+in\s+(?:₹\s*)?(?:million|millions)", "INR million"),
        (r"(?:rs\.?|inr|₹)\s*(?:in\s*)?(?:lakh|lakhs)|(?:amounts?|figures)\s+in\s+(?:₹\s*)?(?:lakh|lakhs)", "INR lakh"),
    ):
        if re.search(pattern, lowered):
            return unit
    return ""


def parse_profit_page(page: int, text: str, *, extraction_variant: str = "full") -> list[ParsedDisclosure]:
    """Parse reported annual standalone profit; never substitute a proxy."""

    lines = [compact(line) for line in text.splitlines() if compact(line)]
    patterns = (
        re.compile(r"profit\s*/?\s*\(?loss\)?\s+(?:after tax\s+)?for the year", re.I),
        re.compile(r"profit\s+for\s+the\s+year", re.I),
        re.compile(r"profit\s+after\s+tax", re.I),
    )
    basis = _basis(text)
    unit = _profit_unit(text)
    if basis != "STANDALONE" or not unit or "2026" not in compact(text) or "2025" not in compact(text):
        return []
    results: list[ParsedDisclosure] = []
    if "statement of profit and loss" not in compact(text).casefold():
        return []
    for index, row in enumerate(lines):
        match = next((pattern.search(row) for pattern in patterns if pattern.search(row)), None)
        if match is None:
            continue
        label = match.group(0)
        # Profit values belong to the statement row itself (occasionally the
        # immediately following wrapped line).  Do not pull dates or unrelated
        # amounts from preceding headers into the candidate pair.
        window = row
        lowered = label.casefold()
        if "attributable" in lowered or "margin" in lowered or "ratio" in lowered:
            continue
        parsed = [value for token in _NUMBER.findall(row[match.end():]) if (value := _value(token)) is not None]
        values = [item for item in parsed if not item[1]]
        # Statement rows normally expose current and comparative amounts.  A
        # unique pair is required; ambiguity is handled by the caller.
        if len(values) < 2:
            continue
        current, prior = values[-2][0], values[-1][0]
        results.append(ParsedDisclosure(
            field="profit",
            page=page,
            current_value=float(current),
            prior_value=float(prior),
            explicit_percent=False,
            reporting_basis=basis,
            label=label,
            evidence_text=window,
            formula_evidence="reported standalone statement profit",
            unit=unit,
            extraction_variant=extraction_variant,
        ))
    return results


def unique_disclosure(candidates: Iterable[ParsedDisclosure]) -> tuple[ParsedDisclosure | None, str]:
    """Return one unambiguous disclosure, otherwise a conservative reason."""

    candidates = list(candidates)
    if not candidates:
        return None, "NO_DIRECT_DISCLOSURE_PARSED"
    standalone = [item for item in candidates if item.reporting_basis == "STANDALONE"]
    if not standalone:
        return None, "REPORTING_BASIS_NOT_EXPLICITLY_STANDALONE"
    keys = {(item.current_value, item.prior_value, item.unit) for item in standalone}
    if len(keys) != 1:
        return None, "CONFLICTING_DIRECT_DISCLOSURES"
    return sorted(standalone, key=lambda item: item.page)[0], "VALIDATED"
