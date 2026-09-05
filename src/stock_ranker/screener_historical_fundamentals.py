"""Versioned Screener standalone history joined to an official PIT clock.

Screener company workbooks do not embed an ISIN or an explicit reporting-basis
field.  They are therefore never self-authenticating inputs: every workbook
must be accompanied by a hash-pinned manifest record which supplies exact ISIN
identity, ticker, observation time, and an explicit standalone attestation.

The financial methodology is deliberately Screener's, not an attempted
reconstruction of issuer-specific statutory ratio definitions.  The standard
v2.1 workbook exposes the ROCE calculation and the underlying balance-sheet
lines needed for debt-to-equity.  Official exchange metadata supplies only the
public-availability clock; it never supplies or changes a financial value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import math
from pathlib import Path, PurePosixPath
import re
from typing import Final, Mapping
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET

import pandas as pd


SCREENER_HISTORICAL_CONTRACT_VERSION: Final = (
    "screener_historical_standalone_official_clock_v1"
)
SCREENER_VALUE_METHOD: Final = "screener_standard_workbook_v2_1"
REPORTING_BASIS: Final = "STANDALONE"
ISIN_PATTERN: Final = re.compile(r"^INE[A-Z0-9]{9}$")
_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_REFERENCE = re.compile(r"^([A-Z]+)([0-9]+)$")


@dataclass(frozen=True, slots=True)
class ScreenerHistoricalResult:
    normalized: pd.DataFrame
    accepted: pd.DataFrame
    rejected: pd.DataFrame
    cohort_summary: pd.DataFrame


@dataclass(frozen=True, slots=True)
class ScreenerWorkbookInspection:
    company: str
    version: str
    roce_formula_sha256: str


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_company(value: object) -> str:
    return " ".join(str(value).upper().split())


def _excel_date(value: object) -> date:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"invalid Excel date serial: {value!r}")
    return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()


def _numeric(value: object, *, field: str, allow_blank: bool = False) -> float | None:
    if value in (None, "") and allow_blank:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}: nonnumeric workbook value {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field}: non-finite workbook value {value!r}")
    return number


class _XlsxCells:
    """Minimal read-only OOXML cell reader; avoids a product dependency."""

    def __init__(self, path: Path) -> None:
        try:
            self._archive = ZipFile(path)
        except (BadZipFile, OSError) as exc:
            raise ValueError(f"invalid xlsx workbook: {path}") from exc
        self._shared = self._shared_strings()
        self._sheets = self._sheet_paths()

    def close(self) -> None:
        self._archive.close()

    def __enter__(self) -> "_XlsxCells":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _shared_strings(self) -> list[str]:
        if "xl/sharedStrings.xml" not in self._archive.namelist():
            return []
        root = ET.fromstring(self._archive.read("xl/sharedStrings.xml"))
        return ["".join(node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t")) for item in root]

    def _sheet_paths(self) -> dict[str, str]:
        workbook = ET.fromstring(self._archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(self._archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in relationships.findall(f"{{{_PKG_REL_NS}}}Relationship")
        }
        result: dict[str, str] = {}
        for sheet in workbook.findall(f".//{{{_MAIN_NS}}}sheet"):
            rel_id = sheet.attrib[f"{{{_REL_NS}}}id"]
            target = PurePosixPath(targets[rel_id])
            if target.is_absolute():
                path = str(target).lstrip("/")
            else:
                path = str(PurePosixPath("xl") / target)
            result[sheet.attrib["name"]] = path
        return result

    def sheet(self, name: str) -> dict[str, tuple[object, str | None]]:
        if name not in self._sheets:
            raise ValueError(f"workbook missing sheet: {name}")
        root = ET.fromstring(self._archive.read(self._sheets[name]))
        result: dict[str, tuple[object, str | None]] = {}
        for cell in root.findall(f".//{{{_MAIN_NS}}}c"):
            ref = cell.attrib["r"]
            kind = cell.attrib.get("t")
            formula_node = cell.find(f"{{{_MAIN_NS}}}f")
            value_node = cell.find(f"{{{_MAIN_NS}}}v")
            if kind == "inlineStr":
                value: object = "".join(
                    node.text or "" for node in cell.iter(f"{{{_MAIN_NS}}}t")
                )
            elif value_node is None or value_node.text in (None, ""):
                value = None
            elif kind == "s":
                value = self._shared[int(value_node.text)]
            elif kind == "b":
                value = value_node.text == "1"
            elif kind in {"str", "e"}:
                value = value_node.text
            else:
                value = float(value_node.text)
            result[ref] = (value, formula_node.text if formula_node is not None else None)
        return result


def _cell(cells: Mapping[str, tuple[object, str | None]], ref: str) -> object:
    return cells.get(ref, (None, None))[0]


def _expected_roce_formula(current: str, previous: str) -> str:
    denominator = (
        f"{previous}4+{previous}5+{previous}6+"
        f"{current}4+{current}5+{current}6"
    )
    return (
        f'IF(({denominator})>0,(\'Profit & Loss\'!{current}10+'
        f'\'Profit & Loss\'!{current}9)*2/({denominator}),"")'
    )


def inspect_screener_historical_workbook(
    path: str | Path,
) -> ScreenerWorkbookInspection:
    """Inspect identity and the fixed v2.1 methodology without assigning an ISIN."""

    workbook_path = Path(path)
    with _XlsxCells(workbook_path) as book:
        data = book.sheet("Data Sheet")
        balance = book.sheet("Balance Sheet")
    company = _canonical_company(_cell(data, "B1"))
    if not company:
        raise ValueError("workbook company is blank")
    if float(_cell(data, "B2") or 0) != 2.1 or float(_cell(data, "B3") or 0) != 2.1:
        raise ValueError("unsupported Screener workbook version")
    columns = "BCDEFGHIJK"
    formulas: list[str] = []
    for index in range(1, len(columns)):
        current, previous = columns[index], columns[index - 1]
        actual_formula = balance.get(f"{current}24", (None, None))[1]
        if actual_formula != _expected_roce_formula(current, previous):
            raise ValueError(f"unexpected Screener ROCE formula at Balance Sheet!{current}24")
        formulas.append(actual_formula)
    return ScreenerWorkbookInspection(
        company=company,
        version="2.1",
        roce_formula_sha256=hashlib.sha256(
            "\n".join(formulas).encode("utf-8")
        ).hexdigest(),
    )
def parse_screener_historical_workbook(
    path: str | Path,
    manifest_record: Mapping[str, object],
) -> pd.DataFrame:
    """Parse one hash-pinned standard Screener standalone company workbook."""

    workbook_path = Path(path)
    required = {
        "ticker", "isin", "company", "workbook_company", "workbook_sha256",
        "reporting_basis", "source_observed_at", "basis_attestation",
    }
    missing = sorted(required - set(manifest_record))
    if missing:
        raise ValueError(f"workbook manifest missing fields: {missing}")
    isin = str(manifest_record["isin"]).strip().upper()
    if not ISIN_PATTERN.fullmatch(isin):
        raise ValueError(f"invalid exact ISIN: {isin!r}")
    if manifest_record["reporting_basis"] != REPORTING_BASIS:
        raise ValueError("Screener historical contract requires explicit STANDALONE basis")
    if not str(manifest_record["basis_attestation"]).strip():
        raise ValueError("missing standalone basis attestation")
    observed = pd.to_datetime(
        manifest_record["source_observed_at"], format="mixed", errors="coerce", utc=True
    )
    if pd.isna(observed):
        raise ValueError("source_observed_at: malformed timestamp")
    actual_hash = sha256_file(workbook_path)
    if actual_hash != str(manifest_record["workbook_sha256"]).lower():
        raise ValueError(f"workbook hash mismatch for {workbook_path.name}")

    inspection = inspect_screener_historical_workbook(workbook_path)
    workbook_company = inspection.company
    expected_company = _canonical_company(manifest_record["workbook_company"])
    if workbook_company != expected_company:
        raise ValueError(
            f"workbook company mismatch: {workbook_company!r} != {expected_company!r}"
        )
    formula_fingerprint = inspection.roce_formula_sha256
    columns = "BCDEFGHIJK"

    with _XlsxCells(workbook_path) as book:
        data = book.sheet("Data Sheet")

    rows: list[dict[str, object]] = []
    for index in range(1, len(columns)):
        current, previous = columns[index], columns[index - 1]
        current_date_value = _cell(data, f"{current}16")
        previous_date_value = _cell(data, f"{previous}16")
        if current_date_value is None or previous_date_value is None:
            continue
        period_end = _excel_date(current_date_value)
        balance_date = _excel_date(_cell(data, f"{current}56"))
        if balance_date != period_end:
            raise ValueError(f"P&L/balance-sheet period mismatch at {current}")
        prior_period_end = _excel_date(previous_date_value)
        required_values = {
            f"{current}30": _cell(data, f"{current}30"),
            f"{previous}30": _cell(data, f"{previous}30"),
            f"{current}28": _cell(data, f"{current}28"),
        }
        # A company export can legitimately contain blank historical columns
        # (for example, before a recently listed issuer reported PAT).  Such a
        # column cannot form a complete V2 observation, but it must not discard
        # later complete years from the same exact-identity workbook.
        if any(value in (None, "") for value in required_values.values()):
            continue
        current_pat = _numeric(required_values[f"{current}30"], field=f"{current}30")
        prior_pat = _numeric(required_values[f"{previous}30"], field=f"{previous}30")
        pbt = _numeric(required_values[f"{current}28"], field=f"{current}28")
        interest = _numeric(
            _cell(data, f"{current}27"), field=f"{current}27", allow_blank=True
        ) or 0.0
        current_equity = sum(
            _numeric(
                _cell(data, f"{current}{row}"), field=f"{current}{row}", allow_blank=True
            ) or 0.0
            for row in (57, 58)
        )
        previous_capital = sum(
            _numeric(
                _cell(data, f"{previous}{row}"), field=f"{previous}{row}", allow_blank=True
            ) or 0.0
            for row in (57, 58, 59)
        )
        current_borrowings = _numeric(
            _cell(data, f"{current}59"), field=f"{current}59", allow_blank=True
        ) or 0.0
        current_capital = current_equity + current_borrowings
        roce_denominator = previous_capital + current_capital
        roce = None if roce_denominator <= 0 else (pbt + interest) * 2.0 / roce_denominator
        debt_to_equity = None if current_equity == 0 else current_borrowings / current_equity
        rows.append({
            "ticker": str(manifest_record["ticker"]).strip().upper(),
            "company": str(manifest_record["company"]).strip(),
            "isin": isin,
            "period_end": period_end.isoformat(),
            "prior_period_end": prior_period_end.isoformat(),
            "reporting_basis": REPORTING_BASIS,
            "roce": roce,
            "debt_to_equity": debt_to_equity,
            "current_pat": current_pat,
            "prior_pat": prior_pat,
            "current_pbt": pbt,
            "current_interest": interest,
            "current_equity_capital": _numeric(
                _cell(data, f"{current}57"), field=f"{current}57", allow_blank=True
            ) or 0.0,
            "current_reserves": _numeric(
                _cell(data, f"{current}58"), field=f"{current}58", allow_blank=True
            ) or 0.0,
            "current_borrowings": current_borrowings,
            "prior_equity_capital": _numeric(
                _cell(data, f"{previous}57"), field=f"{previous}57", allow_blank=True
            ) or 0.0,
            "prior_reserves": _numeric(
                _cell(data, f"{previous}58"), field=f"{previous}58", allow_blank=True
            ) or 0.0,
            "prior_borrowings": _numeric(
                _cell(data, f"{previous}59"), field=f"{previous}59", allow_blank=True
            ) or 0.0,
            "source_name": "SCREENER_PREMIUM_COMPANY_EXPORT",
            "source_observed_at": observed.isoformat(),
            "source_workbook": workbook_path.name,
            "source_workbook_sha256": actual_hash,
            "source_workbook_company": workbook_company,
            "source_value_method": SCREENER_VALUE_METHOD,
            "source_precision_status": "PASS",
            "roce_formula_sha256": formula_fingerprint,
            "basis_attestation": str(manifest_record["basis_attestation"]),
            "contract_version": SCREENER_HISTORICAL_CONTRACT_VERSION,
        })
    if not rows:
        raise ValueError("workbook contains no complete annual V2 observations")
    return pd.DataFrame(rows).sort_values(["isin", "period_end"], kind="stable").reset_index(drop=True)


def official_clock_from_availability(availability: pd.DataFrame) -> pd.DataFrame:
    """Normalize the existing exchange-archive audit to exact PIT clock rows."""

    required = {
        "isin", "financial_year", "pit_available", "dissemination_timestamp",
        "source_url", "availability_status",
    }
    missing = sorted(required - set(availability.columns))
    if missing:
        raise ValueError(f"official availability missing columns: {missing}")
    frame = availability.copy(deep=True)
    truth = frame["pit_available"].map(
        lambda value: value is True or str(value).strip().lower() == "true"
    )
    frame = frame.loc[truth].copy()
    years = frame["financial_year"].astype(str).str.extract(r"^(\d{4})-(\d{4})$")
    if years.isna().any().any():
        raise ValueError("financial_year: malformed values in official availability")
    frame["period_end"] = years[1] + "-03-31"
    frame["official_available_at"] = pd.to_datetime(
        frame["dissemination_timestamp"], format="mixed", errors="coerce", utc=True
    )
    if frame["official_available_at"].isna().any():
        raise ValueError("explicit PIT rows contain malformed dissemination timestamps")
    frame["period_end"] = pd.to_datetime(frame["period_end"], format="%Y-%m-%d", utc=True)
    if (frame["official_available_at"] < frame["period_end"]).any():
        raise ValueError("official availability precedes financial period end")
    frame["filing_id"] = frame["source_url"].map(
        lambda value: hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    )
    frame = frame.sort_values(
        ["isin", "period_end", "official_available_at", "filing_id"], kind="stable"
    ).drop_duplicates(["isin", "period_end"], keep="first")
    return frame[[
        "isin", "period_end", "official_available_at", "filing_id", "source_url",
        "availability_status",
    ]].rename(columns={"source_url": "official_filing_url"}).reset_index(drop=True)


def build_screener_pit_cohorts(
    normalized: pd.DataFrame,
    official_clock: pd.DataFrame,
    ranking_dates: list[date],
) -> ScreenerHistoricalResult:
    """Construct latest eligible fundamental records at each ranking date."""

    financials = normalized.copy(deep=True)
    for column in ("period_end", "prior_period_end", "source_observed_at"):
        financials[column] = pd.to_datetime(
            financials[column], format="mixed", errors="coerce", utc=True
        )
        if financials[column].isna().any():
            raise ValueError(f"{column}: malformed normalized timestamp")
    if financials.duplicated(["isin", "period_end"]).any():
        raise ValueError("duplicate Screener ISIN/period records")
    clock = official_clock.copy(deep=True)
    for column in ("period_end", "official_available_at"):
        clock[column] = pd.to_datetime(
            clock[column], format="mixed", errors="coerce", utc=True
        )
        if clock[column].isna().any():
            raise ValueError(f"{column}: malformed official clock timestamp")
    merged = financials.merge(clock, on=["isin", "period_end"], how="left", validate="one_to_one")
    all_rows: list[pd.DataFrame] = []
    for ranking_date in sorted(set(ranking_dates)):
        cutoff = (
            pd.Timestamp(ranking_date, tz="Asia/Kolkata")
            + pd.Timedelta(hours=15, minutes=30)
        ).tz_convert("UTC")
        frame = merged.copy(deep=True)
        frame["ranking_date"] = ranking_date.isoformat()
        frame["source_observed_after_ranking_date"] = frame["source_observed_at"] > cutoff
        frame["value_clock_policy"] = (
            "SCREENER_HISTORICAL_PERIOD_VALUE_WITH_OFFICIAL_EXCHANGE_AVAILABILITY_CLOCK"
        )
        reasons: list[str] = []
        for row in frame.to_dict("records"):
            precision_status = row.get("source_precision_status", "PASS")
            if (
                pd.isna(precision_status)
                and row.get("source_value_method") == SCREENER_VALUE_METHOD
            ):
                precision_status = "PASS"
            if pd.isna(row.get("official_available_at")):
                reason = "NO_EXACT_OFFICIAL_FILING_CLOCK"
            elif row["official_available_at"] > cutoff:
                reason = "OFFICIAL_FILING_AFTER_RANKING_DATE"
            elif row["period_end"] > cutoff:
                reason = "FINANCIAL_PERIOD_AFTER_RANKING_DATE"
            elif precision_status != "PASS":
                reason = "UNSAFE_SOURCE_DISPLAY_PRECISION"
            else:
                reason = "PIT_AVAILABLE_PERIOD"
            reasons.append(reason)
        frame["period_status"] = reasons
        candidates = frame.loc[frame["period_status"].eq("PIT_AVAILABLE_PERIOD")].copy()
        frame["selected_for_ranking_date"] = False
        if len(candidates):
            chosen = candidates.sort_values(
                ["isin", "period_end", "official_available_at"], kind="stable"
            ).groupby("isin", sort=True, as_index=False).tail(1)
            superseded = candidates.index.difference(chosen.index)
            frame.loc[superseded, "period_status"] = "SUPERSEDED_BY_LATER_PIT_PERIOD"
            for index in chosen.index:
                row = frame.loc[index]
                values = [row.get(name) for name in (
                    "roce", "debt_to_equity", "current_pat", "prior_pat"
                )]
                if any(value is None or not math.isfinite(float(value)) for value in values):
                    status = "INCOMPLETE_SCREENER_FINANCIALS"
                elif float(row["debt_to_equity"]) < 0:
                    status = "NEGATIVE_DEBT_TO_EQUITY"
                elif float(row["prior_pat"]) == 0:
                    status = "ZERO_PRIOR_PAT"
                else:
                    status = "ELIGIBLE_PERIOD"
                    frame.loc[index, "selected_for_ranking_date"] = True
                frame.loc[index, "period_status"] = status
        all_rows.append(frame)
    combined = pd.concat(all_rows, ignore_index=True) if all_rows else merged.iloc[0:0].copy()
    accepted = combined.loc[combined["selected_for_ranking_date"]].copy()
    rejected = combined.loc[~combined["selected_for_ranking_date"]].copy()
    summary = (
        accepted.groupby("ranking_date", sort=True)["isin"].nunique().rename("pit_fundamental_count")
        .reindex([item.isoformat() for item in sorted(set(ranking_dates))], fill_value=0)
        .rename_axis("ranking_date").reset_index()
    )
    stable_sort = ["ranking_date", "isin", "period_end"]
    return ScreenerHistoricalResult(
        normalized=financials.sort_values(["isin", "period_end"], kind="stable").reset_index(drop=True),
        accepted=accepted.sort_values(stable_sort, kind="stable").reset_index(drop=True),
        rejected=rejected.sort_values(stable_sort, kind="stable").reset_index(drop=True),
        cohort_summary=summary,
    )


def calibrate_screener_against_gold(
    normalized: pd.DataFrame,
    gold_records: list[Mapping[str, object]],
    *,
    period_end: str = "2026-03-31",
    tolerance_crore: float = 0.011,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Check identity and reported profit; ratio differences remain visible."""

    latest = normalized.loc[normalized["period_end"].astype(str).str[:10].eq(period_end)].copy()
    gold_by_isin = {str(row["isin"]): row for row in gold_records}
    rows: list[dict[str, object]] = []
    unit_divisor = {"INR crore": 1.0, "INR million": 10.0, "INR lakh": 100.0}
    for record in latest.to_dict("records"):
        gold = gold_by_isin.get(record["isin"])
        if gold is None:
            rows.append({"isin": record["isin"], "ticker": record["ticker"], "status": "NO_GOLD_RECORD"})
            continue
        profit = gold["profit"]
        divisor = unit_divisor.get(str(profit["unit"]))
        if divisor is None:
            raise ValueError(f"unsupported gold profit unit: {profit['unit']}")
        gold_current = float(profit["current_value"]) / divisor
        gold_prior = float(profit["prior_value"]) / divisor
        current_delta = float(record["current_pat"]) - gold_current
        prior_delta = float(record["prior_pat"]) - gold_prior
        identity_match = record["ticker"] == str(gold["ticker"]) and record["isin"] == str(gold["isin"])
        pat_match = abs(current_delta) <= tolerance_crore and abs(prior_delta) <= tolerance_crore
        gold_roce = gold.get("roce", {}).get("canonical_decimal")
        gold_de = gold.get("debt_to_equity", {}).get("canonical_decimal")
        rows.append({
            "isin": record["isin"], "ticker": record["ticker"],
            "identity_match": identity_match, "pat_match": pat_match,
            "screener_current_pat_crore": record["current_pat"],
            "gold_current_pat_crore": gold_current, "current_pat_delta_crore": current_delta,
            "screener_prior_pat_crore": record["prior_pat"],
            "gold_prior_pat_crore": gold_prior, "prior_pat_delta_crore": prior_delta,
            "screener_roce": record["roce"], "gold_statutory_roce": gold_roce,
            "roce_method_delta": None if gold_roce is None else float(record["roce"]) - float(gold_roce),
            "screener_debt_to_equity": record["debt_to_equity"],
            "gold_statutory_debt_to_equity": gold_de,
            "debt_to_equity_method_delta": None if gold_de is None else float(record["debt_to_equity"]) - float(gold_de),
            "status": "PASS" if identity_match and pat_match else "FAIL",
        })
    details = pd.DataFrame(rows).sort_values(["isin"], kind="stable").reset_index(drop=True)
    summary = {
        "contract_version": SCREENER_HISTORICAL_CONTRACT_VERSION,
        "attempted": len(details),
        "identity_matches": int(details.get("identity_match", pd.Series(dtype=bool)).fillna(False).sum()),
        "pat_matches": int(details.get("pat_match", pd.Series(dtype=bool)).fillna(False).sum()),
        "failed": int(details["status"].ne("PASS").sum()) if len(details) else 0,
        "ratio_comparison_semantics": (
            "Diagnostic only: Screener canonical ratios intentionally need not equal issuer-specific statutory ratios."
        ),
        "calibration_status": "PASS" if len(details) == len(gold_records) and details["status"].eq("PASS").all() else "FAIL",
    }
    return details, summary
