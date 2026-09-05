"""Rate-limited, cache-first ingestion of public Screener standalone history.

This module deliberately consumes the user-visible company statement tables,
not a private API.  Values are displayed in rounded Rs. crore units.  The
parser therefore carries interval-derived uncertainty and rejects ratios whose
denominators make that display precision scientifically unsafe.  Exact ISIN
identity remains external, hash-pinned evidence from a Screener Premium bulk
export; the company page must independently expose the expected NSE symbol.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
import math
from pathlib import Path
import re
import time
from typing import Final, Iterable, Mapping
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from .screener_historical_fundamentals import (
    ISIN_PATTERN,
    REPORTING_BASIS,
    SCREENER_HISTORICAL_CONTRACT_VERSION,
    sha256_file,
)


PUBLIC_VALUE_METHOD: Final = "screener_public_standalone_rounded_statements_v1"
PUBLIC_PAGE_SCHEMA: Final = "screener_public_history_cache_v1"
DEFAULT_USER_AGENT: Final = (
    "stock-ranking-platform-college-research/1.0 (+offline cache; contact repository owner)"
)
_SECTIONS = {"profit-loss", "balance-sheet", "ratios"}
_DATE_END = {"Mar": "03-31", "Jun": "06-30", "Sep": "09-30", "Dec": "12-31"}


@dataclass(frozen=True, slots=True)
class PublicPageAcquisition:
    ticker: str
    url: str
    final_url: str
    observed_at: str
    path: str
    sha256: str
    byte_count: int
    cache_status: str


class _StatementHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.section: str | None = None
        self.in_row = False
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.row: list[str] = []
        self.tables: dict[str, list[list[str]]] = {}
        self.company_id: str | None = None
        self.nse_symbols: set[str] = set()
        self.bases: dict[str, set[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id") == "company-info":
            self.company_id = values.get("data-company-id")
        if tag == "a":
            href = values.get("href") or ""
            match = re.search(r"nseindia\.com/.+?[?&]symbol=([^&#]+)", href, re.I)
            if match:
                self.nse_symbols.add(match.group(1).upper())
        if tag == "section" and values.get("id") in _SECTIONS:
            self.section = str(values["id"])
        if self.section and tag == "tr":
            self.in_row = True
            self.row = []
        if self.in_row and tag in {"th", "td"}:
            self.in_cell = True
            self.cell_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell_parts.append(data)
        if self.section and "Figures in Rs. Crores" in data:
            basis = "STANDALONE" if "Standalone" in data else "CONSOLIDATED"
            self.bases.setdefault(self.section, set()).add(basis)

    def handle_endtag(self, tag: str) -> None:
        if self.in_cell and tag in {"th", "td"}:
            value = " ".join("".join(self.cell_parts).replace("+", "").split())
            self.row.append(value)
            self.in_cell = False
        if self.in_row and tag == "tr":
            if self.row:
                self.tables.setdefault(str(self.section), []).append(self.row)
            self.in_row = False
        if tag == "section" and self.section:
            self.section = None


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(payload)
    temporary.replace(path)


def acquire_public_company_pages(
    identities: pd.DataFrame,
    cache_directory: str | Path,
    *,
    delay_seconds: float = 15.0,
    timeout_seconds: float = 30.0,
    user_agent: str = DEFAULT_USER_AGENT,
    refresh: bool = False,
    request_budget: int | None = 5,
    max_consecutive_failures: int = 1,
) -> pd.DataFrame:
    """Acquire validated public pages once and resume from immutable cache."""

    required = {"ticker", "isin"}
    missing = sorted(required - set(identities.columns))
    if missing:
        raise ValueError(f"public Screener identities missing columns: {missing}")
    frame = identities.copy(deep=True)
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["isin"] = frame["isin"].astype(str).str.strip().str.upper()
    if frame["ticker"].eq("").any() or ~frame["isin"].map(lambda x: bool(ISIN_PATTERN.fullmatch(x))).all():
        raise ValueError("public Screener identities contain blank ticker or invalid ISIN")
    if frame.duplicated("ticker").any() or frame.duplicated("isin").any():
        raise ValueError("public Screener acquisition requires unique ticker and ISIN")
    cache = Path(cache_directory)
    if request_budget is not None and request_budget < 0:
        raise ValueError("request_budget must be nonnegative or None")
    if max_consecutive_failures < 1:
        raise ValueError("max_consecutive_failures must be positive")
    records: list[dict[str, object]] = []
    requests_made = 0
    consecutive_failures = 0
    circuit_open = False
    for row in frame.sort_values(["ticker"], kind="stable").to_dict("records"):
        ticker = row["ticker"]
        path = cache / "pages" / f"{ticker}.html"
        metadata_path = cache / "pages" / f"{ticker}.json"
        url = f"https://www.screener.in/company/{quote(ticker, safe='')}/"
        status = "CACHE_HIT"
        if refresh or not path.exists() or not metadata_path.exists():
            if circuit_open or (request_budget is not None and requests_made >= request_budget):
                records.append({
                    **row, "url": url, "final_url": "", "observed_at": "",
                    "path": "", "sha256": "", "byte_count": 0,
                    "cache_status": "DEFERRED_REQUEST_BUDGET", "acquisition_error": "",
                })
                continue
            request = Request(url, headers={"User-Agent": user_agent, "Accept": "text/html"})
            requests_made += 1
            try:
                with urlopen(request, timeout=timeout_seconds) as response:
                    payload = response.read()
                    final_url = response.geturl()
                    content_type = response.headers.get("Content-Type", "")
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                consecutive_failures += 1
                circuit_open = consecutive_failures >= max_consecutive_failures
                records.append({
                    **row, "url": url, "final_url": "", "observed_at": "",
                    "path": "", "sha256": "", "byte_count": 0,
                    "cache_status": "ACQUISITION_FAILED", "acquisition_error": str(exc),
                })
                if delay_seconds > 0:
                    time.sleep(delay_seconds)
                continue
            consecutive_failures = 0
            if "text/html" not in content_type.lower() or b"id=\"company-info\"" not in payload:
                consecutive_failures += 1
                circuit_open = consecutive_failures >= max_consecutive_failures
                records.append({
                    **row, "url": url, "final_url": final_url, "observed_at": "",
                    "path": "", "sha256": "", "byte_count": len(payload),
                    "cache_status": "ACQUISITION_FAILED",
                    "acquisition_error": "response is not a validated Screener company HTML page",
                })
                if delay_seconds > 0:
                    time.sleep(delay_seconds)
                continue
            observed = datetime.now(timezone.utc).isoformat()
            _write_bytes_atomic(path, payload)
            meta = {
                "schema_version": PUBLIC_PAGE_SCHEMA,
                "ticker": ticker,
                "isin": row["isin"],
                "url": url,
                "final_url": final_url,
                "observed_at": observed,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "byte_count": len(payload),
                "user_agent": user_agent,
            }
            _write_bytes_atomic(
                metadata_path,
                (json.dumps(meta, sort_keys=True, indent=2) + "\n").encode("utf-8"),
            )
            status = "ACQUIRED"
            if delay_seconds > 0:
                time.sleep(delay_seconds)
        meta = json.loads(metadata_path.read_text(encoding="utf-8"))
        if meta.get("schema_version") != PUBLIC_PAGE_SCHEMA:
            raise ValueError(f"{ticker}: unsupported cache metadata")
        if meta.get("ticker") != ticker or meta.get("isin") != row["isin"]:
            raise ValueError(f"{ticker}: cached identity mismatch")
        actual_hash = sha256_file(path)
        if actual_hash != meta.get("sha256"):
            raise ValueError(f"{ticker}: cached page hash mismatch")
        records.append({**row, **meta, "path": str(path), "cache_status": status})
    return pd.DataFrame(records).sort_values("ticker", kind="stable").reset_index(drop=True)


def _table(rows: list[list[str]], *, section: str) -> tuple[list[str], dict[str, list[str]]]:
    if not rows or len(rows[0]) < 2:
        raise ValueError(f"{section}: missing statement table header")
    header = rows[0][1:]
    values: dict[str, list[str]] = {}
    for row in rows[1:]:
        if row and row[0] and row[0] not in values:
            values[row[0]] = row[1:]
    return header, values


def _display_number(value: str, *, field: str) -> tuple[float, float]:
    cleaned = value.strip().replace(",", "").replace("%", "")
    if cleaned in {"", "-", "--"}:
        raise ValueError(f"{field}: blank displayed value")
    try:
        number = float(cleaned)
    except ValueError as exc:
        raise ValueError(f"{field}: nonnumeric displayed value {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field}: non-finite displayed value")
    decimals = len(cleaned.partition(".")[2]) if "." in cleaned else 0
    quantum = 10.0 ** (-decimals)
    return number, quantum / 2.0


def _ratio_interval(
    numerator_parts: Iterable[tuple[float, float]],
    denominator_parts: Iterable[tuple[float, float]],
    *,
    multiplier: float = 1.0,
) -> tuple[float, float, float]:
    numerator = list(numerator_parts)
    denominator = list(denominator_parts)
    n0 = sum(v for v, _ in numerator) * multiplier
    nlo = sum(v - e for v, e in numerator) * multiplier
    nhi = sum(v + e for v, e in numerator) * multiplier
    d0 = sum(v for v, _ in denominator)
    dlo = sum(v - e for v, e in denominator)
    dhi = sum(v + e for v, e in denominator)
    if dlo <= 0 <= dhi or d0 == 0:
        raise ValueError("display-precision denominator interval crosses zero")
    candidates = [n / d for n in (nlo, nhi) for d in (dlo, dhi)]
    return n0 / d0, min(candidates), max(candidates)


def parse_public_company_history(
    html: str | bytes,
    identity: Mapping[str, object],
    *,
    source_url: str,
    source_observed_at: str,
    source_sha256: str,
    max_roce_uncertainty: float = 0.01,
    max_debt_to_equity_uncertainty: float = 0.02,
) -> pd.DataFrame:
    """Normalize displayed standalone history with explicit uncertainty gates."""

    ticker = str(identity.get("ticker", "")).strip().upper()
    isin = str(identity.get("isin", "")).strip().upper()
    company = str(identity.get("company", identity.get("name", ""))).strip()
    if not ticker or not ISIN_PATTERN.fullmatch(isin):
        raise ValueError("public page requires exact ticker and ISIN identity")
    text = html.decode("utf-8", errors="strict") if isinstance(html, bytes) else html
    parser = _StatementHTML()
    parser.feed(text)
    if parser.nse_symbols != {ticker}:
        raise ValueError(f"{ticker}: page NSE identity mismatch {sorted(parser.nse_symbols)}")
    if not parser.company_id:
        raise ValueError(f"{ticker}: page missing Screener company ID")
    basis_evidence = "EXPLICIT_STANDALONE_LABEL"
    for section in ("profit-loss", "balance-sheet"):
        if parser.bases.get(section) == {REPORTING_BASIS}:
            continue
        # Screener omits the word "Standalone" where no consolidated view
        # exists.  The documented parent-only URL plus the absence of a
        # standalone-switch link is then the reproducible basis evidence.
        expected_path = f"/company/{ticker}/"
        if expected_path not in source_url or "View Standalone" in text:
            raise ValueError(f"{ticker}: {section} is not explicitly standalone")
        basis_evidence = "SCREENER_STANDALONE_URL_ONLY_NO_CONSOLIDATED_ALTERNATIVE"
    pnl_header, pnl = _table(parser.tables.get("profit-loss", []), section="profit-loss")
    balance_header, balance = _table(parser.tables.get("balance-sheet", []), section="balance-sheet")
    pnl_dates = pnl_header[:-1] if pnl_header and pnl_header[-1] == "TTM" else pnl_header
    required_pnl = ("Profit before tax", "Interest", "Net Profit")
    required_balance = ("Equity Capital", "Reserves", "Borrowings")
    missing = [name for name in required_pnl if name not in pnl]
    missing += [name for name in required_balance if name not in balance]
    if missing:
        raise ValueError(f"{ticker}: public statements missing rows {missing}")
    observed = pd.to_datetime(source_observed_at, errors="coerce", utc=True)
    if pd.isna(observed):
        raise ValueError(f"{ticker}: malformed source_observed_at")
    rows: list[dict[str, object]] = []
    for index, label in enumerate(balance_header):
        if index == 0 or label not in pnl_dates:
            continue
        month, year_text = label.split()
        if month not in _DATE_END or not year_text.isdigit():
            continue
        pnl_index = pnl_dates.index(label)
        try:
            pat = _display_number(pnl["Net Profit"][pnl_index], field=f"{label} PAT")
            pbt = _display_number(pnl["Profit before tax"][pnl_index], field=f"{label} PBT")
            interest = _display_number(pnl["Interest"][pnl_index], field=f"{label} interest")
            equity = _display_number(balance["Equity Capital"][index], field=f"{label} equity")
            reserves = _display_number(balance["Reserves"][index], field=f"{label} reserves")
            borrowings = _display_number(balance["Borrowings"][index], field=f"{label} borrowings")
            prior_equity = _display_number(balance["Equity Capital"][index - 1], field=f"{label} prior equity")
            prior_reserves = _display_number(balance["Reserves"][index - 1], field=f"{label} prior reserves")
            prior_borrowings = _display_number(balance["Borrowings"][index - 1], field=f"{label} prior borrowings")
            prior_label = balance_header[index - 1]
            prior_pnl_index = pnl_dates.index(prior_label)
            prior_pat = _display_number(pnl["Net Profit"][prior_pnl_index], field=f"{prior_label} PAT")
            roce, roce_low, roce_high = _ratio_interval(
                [pbt, interest],
                [prior_equity, prior_reserves, prior_borrowings, equity, reserves, borrowings],
                multiplier=2.0,
            )
            debt_to_equity, de_low, de_high = _ratio_interval([borrowings], [equity, reserves])
            growth, growth_low, growth_high = _ratio_interval(
                [(pat[0] - prior_pat[0], pat[1] + prior_pat[1])], [prior_pat]
            )
        except (ValueError, IndexError):
            continue
        roce_uncertainty = max(abs(roce - roce_low), abs(roce_high - roce))
        de_uncertainty = max(abs(debt_to_equity - de_low), abs(de_high - debt_to_equity))
        precision_ok = (
            roce_uncertainty <= max_roce_uncertainty
            and de_uncertainty <= max_debt_to_equity_uncertainty
        )
        prior_month, prior_year = prior_label.split()
        rows.append({
            "ticker": ticker,
            "company": company,
            "isin": isin,
            "period_end": f"{int(year_text):04d}-{_DATE_END[month]}",
            "prior_period_end": f"{int(prior_year):04d}-{_DATE_END[prior_month]}",
            "reporting_basis": REPORTING_BASIS,
            "source_basis_evidence": basis_evidence,
            "roce": roce,
            "roce_lower_bound": roce_low,
            "roce_upper_bound": roce_high,
            "roce_uncertainty": roce_uncertainty,
            "debt_to_equity": debt_to_equity,
            "debt_to_equity_lower_bound": de_low,
            "debt_to_equity_upper_bound": de_high,
            "debt_to_equity_uncertainty": de_uncertainty,
            "current_pat": pat[0],
            "prior_pat": prior_pat[0],
            "profit_growth_yoy": growth,
            "profit_growth_yoy_lower_bound": growth_low,
            "profit_growth_yoy_upper_bound": growth_high,
            "source_precision_status": "PASS" if precision_ok else "UNSAFE_ROUNDED_RATIO_PRECISION",
            "source_name": "SCREENER_PUBLIC_COMPANY_PAGE",
            "source_url": source_url,
            "source_observed_at": observed.isoformat(),
            "source_page_sha256": source_sha256,
            "source_company_id": parser.company_id,
            "source_value_method": PUBLIC_VALUE_METHOD,
            "source_display_units": "INR_CRORE_ROUNDED_AS_PUBLISHED",
            "contract_version": SCREENER_HISTORICAL_CONTRACT_VERSION,
        })
    return pd.DataFrame(rows).sort_values(["isin", "period_end"], kind="stable").reset_index(drop=True)


def parse_cached_public_pages(cache_manifest: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse a cache manifest; retain every page-level failure deterministically."""

    accepted: list[pd.DataFrame] = []
    failures: list[dict[str, object]] = []
    for record in cache_manifest.sort_values("ticker", kind="stable").to_dict("records"):
        if record.get("cache_status") in {"ACQUISITION_FAILED", "DEFERRED_REQUEST_BUDGET"}:
            status = str(record.get("cache_status"))
            failures.append({
                "ticker": record.get("ticker"), "isin": record.get("isin"),
                "status": status,
                "reason": record.get("acquisition_error"), "source_page_sha256": "",
            })
            continue
        try:
            frame = parse_public_company_history(
                Path(record["path"]).read_bytes(),
                record,
                source_url=str(record["url"]),
                source_observed_at=str(record["observed_at"]),
                source_sha256=str(record["sha256"]),
            )
            if frame.empty:
                raise ValueError("no usable annual statement rows")
            accepted.append(frame)
        except Exception as exc:  # page-specific evidence is quarantined, not fatal
            failures.append({
                "ticker": record.get("ticker"),
                "isin": record.get("isin"),
                "status": "PUBLIC_PAGE_REJECTED",
                "reason": str(exc),
                "source_page_sha256": record.get("sha256"),
            })
    normalized = pd.concat(accepted, ignore_index=True) if accepted else pd.DataFrame()
    if len(normalized):
        normalized = normalized.sort_values(["isin", "period_end"], kind="stable").reset_index(drop=True)
    rejected = pd.DataFrame(failures)
    if len(rejected):
        rejected = rejected.sort_values(["ticker"], kind="stable").reset_index(drop=True)
    return normalized, rejected
