"""Auditable comparison with the Baba Venkeesh workbook reference.

The workbook is treated as evidence, never as a source of hard-coded expected
rankings.  Its cached cells and formulas are read directly from the XLSX Open
XML package with the standard library so the main product gains no spreadsheet
runtime dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pandas as pd

from stock_ranker.baseline import calculate_baseline_rankings
from stock_ranker.historical_baseline import prepare_historical_baseline


REFERENCE_VERSION = "baba_venkeesh_master_sheet_v2_1"
BENCHMARK_VERSION = "professor_reference_benchmark_v1"
DEFAULT_AS_OF_CELL = "NAV-Auto!H1"
METRICS = ("yoy_growth", "cagr_3y", "cagr_5y", "days_since_recorded_high")
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
REL_NS = {"p": "http://schemas.openxmlformats.org/package/2006/relationships"}


@dataclass(frozen=True, slots=True)
class ProfessorReferenceResult:
    reference: pd.DataFrame
    stock_comparison: pd.DataFrame
    sector_summary: pd.DataFrame
    metric_summary: pd.DataFrame
    audit: dict[str, Any]


class _XlsxCells:
    def __init__(self, path: Path):
        self.path = path
        self.formulas: dict[tuple[str, str], str] = {}
        self.formula_attributes: dict[tuple[str, str], dict[str, str]] = {}
        self.values: dict[tuple[str, str], Any] = {}
        with ZipFile(path) as archive:
            shared = self._shared_strings(archive)
            sheet_paths = self._sheet_paths(archive)
            self.sheet_names = tuple(sheet_paths)
            for name, target in sheet_paths.items():
                root = ET.fromstring(archive.read(target))
                for cell in root.findall(".//m:c", NS):
                    address = cell.attrib.get("r", "")
                    kind = cell.attrib.get("t")
                    formula = cell.find("m:f", NS)
                    raw = cell.find("m:v", NS)
                    inline = cell.find("m:is/m:t", NS)
                    if formula is not None:
                        self.formulas[(name, address)] = formula.text or ""
                        self.formula_attributes[(name, address)] = dict(formula.attrib)
                    value = inline.text if inline is not None else (raw.text if raw is not None else None)
                    if kind == "s" and value is not None:
                        value = shared[int(value)]
                    elif kind == "b" and value is not None:
                        value = value == "1"
                    elif kind not in {"str", "e", "inlineStr", "s", "b"} and value is not None:
                        number = float(value)
                        value = int(number) if number.is_integer() else number
                    self.values[(name, address)] = value

    @staticmethod
    def _shared_strings(archive: ZipFile) -> list[str]:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        return ["".join(node.text or "" for node in item.findall(".//m:t", NS))
                for item in root.findall("m:si", NS)]

    @staticmethod
    def _sheet_paths(archive: ZipFile) -> dict[str, str]:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {node.attrib["Id"]: node.attrib["Target"] for node in rels.findall("p:Relationship", REL_NS)}
        result = {}
        for sheet in workbook.findall("m:sheets/m:sheet", NS):
            target = targets[sheet.attrib[f"{{{NS['r']}}}id"]].replace("\\", "/")
            normalized = target if target.startswith("xl/") else "xl/" + target.lstrip("/")
            item = PurePosixPath(normalized)
            if item.is_absolute() or ".." in item.parts:
                raise ValueError("workbook contains an unsafe worksheet relationship")
            result[sheet.attrib["name"]] = normalized
        return result

    def value(self, sheet: str, address: str) -> Any:
        return self.values.get((sheet, address))

    def formula(self, sheet: str, address: str) -> str | None:
        return self.formulas.get((sheet, address))


def _excel_date(value: Any) -> date:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"cached workbook date is unavailable: {value!r}")
    return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _symbol(value: Any) -> tuple[str | None, str | None]:
    text = str(value or "").strip().upper()
    if ":" not in text:
        return None, None
    exchange, symbol = text.split(":", 1)
    return exchange, symbol.strip()


def extract_professor_reference(workbook_path: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Extract the comparable cached reference cells with exact provenance."""
    path = Path(workbook_path).resolve()
    if not path.is_file() or path.suffix.lower() != ".xlsx":
        raise ValueError("professor reference must be an existing .xlsx file")
    cells = _XlsxCells(path)
    as_of = _excel_date(cells.value("NAV-Auto", "H1"))
    cagr_rows: dict[str, dict[str, Any]] = {}
    for row in range(3, 500):
        ticker = cells.value("CAGR", f"A{row}")
        if ticker is None:
            continue
        key = str(ticker).strip().upper()
        cagr_rows[key] = {
            "yoy_growth": _number(cells.value("CAGR", f"H{row}")),
            "yoy_cell": f"CAGR!H{row}",
        }
    rows: list[dict[str, Any]] = []
    for row in range(2, 500):
        raw_ticker = cells.value("Stock Picker", f"N{row}")
        if raw_ticker is None:
            continue
        exchange, symbol = _symbol(raw_ticker)
        key = str(raw_ticker).strip().upper()
        raw_high_date = cells.value("Stock Picker", f"G{row}")
        high_date = None
        if _number(raw_high_date) is not None:
            high_date = _excel_date(raw_high_date).isoformat()
        cagr = cagr_rows.get(key, {})
        rows.append({
            "reference_row": row, "reference_ticker": key,
            "reference_exchange": exchange, "reference_symbol": symbol,
            "reference_company": cells.value("Stock Picker", f"B{row}"),
            "reference_as_of_date": as_of.isoformat(),
            "reference_current_price": _number(cells.value("Stock Picker", f"C{row}")),
            "reference_recorded_high": _number(cells.value("Stock Picker", f"F{row}")),
            "reference_recorded_high_date": high_date,
            "reference_days_since_recorded_high": _number(cells.value("Stock Picker", f"H{row}")),
            "reference_yoy_growth": cagr.get("yoy_growth"),
            "reference_cagr_3y": _number(cells.value("Stock Picker", f"W{row}")),
            "reference_cagr_5y": _number(cells.value("Stock Picker", f"V{row}")),
            "price_cell": f"Stock Picker!C{row}", "high_cell": f"Stock Picker!F{row}",
            "high_date_cell": f"Stock Picker!G{row}", "recency_cell": f"Stock Picker!H{row}",
            "cagr_3y_cell": f"Stock Picker!W{row}", "cagr_5y_cell": f"Stock Picker!V{row}",
            "yoy_cell": cagr.get("yoy_cell"),
            "price_formula": cells.formula("Stock Picker", f"C{row}"),
            "high_formula": cells.formula("Stock Picker", f"F{row}"),
            "high_date_formula": cells.formula("Stock Picker", f"G{row}"),
            "recency_formula": cells.formula("Stock Picker", f"H{row}"),
        })
    frame = pd.DataFrame(rows)
    metadata = {
        "reference_version": REFERENCE_VERSION,
        "workbook_filename": path.name,
        "workbook_sha256": sha256(path.read_bytes()).hexdigest(),
        "cached_as_of_date": as_of.isoformat(), "cached_as_of_cell": DEFAULT_AS_OF_CELL,
        "stock_picker_rows": len(frame),
        "worksheet_count": len(cells.sheet_names),
        "sector_or_industry_label_cells": sum(
            1 for value in cells.values.values()
            if isinstance(value, str) and value.strip().lower() in {"sector", "industry"}
        ),
        "rank_formula_cells": sum(
            1 for value in cells.formulas.values()
            if re.search(r"\bRANK(?:\.EQ|\.AVG)?\s*\(", value, flags=re.IGNORECASE)
        ),
        "stock_picker_rank_formula_cells": sum(
            1 for (sheet, _), value in cells.formulas.items()
            if sheet == "Stock Picker" and re.search(r"\bRANK(?:\.EQ|\.AVG)?\s*\(", value, flags=re.IGNORECASE)
        ),
        "methodology_boundary": (
            "The workbook supplies a personal stock list and cached price/CAGR/ATH fields; "
            "it contains no sector taxonomy or computed sector-ranking formula."
        ),
    }
    return frame, metadata


def _rank_corr(left: pd.Series, right: pd.Series) -> float | None:
    pair = pd.concat([left, right], axis=1).dropna()
    if len(pair) < 2 or pair.iloc[:, 0].nunique() < 2 or pair.iloc[:, 1].nunique() < 2:
        return None
    return float(pair.iloc[:, 0].rank(method="average").corr(pair.iloc[:, 1].rank(method="average")))


def _top_overlap(left: pd.Series, right: pd.Series, *, higher: bool, k: int = 5) -> float | None:
    pair = pd.concat([left, right], axis=1).dropna()
    if pair.empty:
        return None
    count = min(k, len(pair))
    a = set(pair.sort_values(pair.columns[0], ascending=not higher, kind="stable").head(count).index)
    b = set(pair.sort_values(pair.columns[1], ascending=not higher, kind="stable").head(count).index)
    return len(a & b) / count


def benchmark_professor_reference(
    workbook_path: str | Path,
    *,
    live_market_path: str | Path,
    history_cache: str | Path,
    evaluation_summary_path: str | Path,
) -> ProfessorReferenceResult:
    """Run an offline, identity-exact reference-to-platform benchmark."""
    reference, source_meta = extract_professor_reference(workbook_path)
    market = pd.read_csv(live_market_path)
    required = {"ticker", "company", "sector", "listing_date", "classification_status"}
    if not required.issubset(market.columns) or market["ticker"].duplicated().any():
        raise ValueError("live market identity snapshot is invalid")
    universe = market.loc[market["classification_status"].eq("CLASSIFIED"),
                          ["ticker", "company", "sector", "listing_date"]].copy()
    # Identity matching is against the full current NSE ordinary-equity
    # universe.  Classification availability is a separate ranking gate.
    exact = set(market["ticker"].astype(str))
    reference["ticker"] = reference.apply(
        lambda row: row["reference_symbol"] if row["reference_exchange"] == "NSE" and row["reference_symbol"] in exact else None,
        axis=1,
    )
    reference["identity_status"] = reference.apply(
        lambda row: "MATCHED_EXACT_NSE" if pd.notna(row["ticker"]) else (
            "BSE_ONLY_NO_SUBSTITUTION" if row["reference_exchange"] in {"BOM", "BSE"}
            else "NOT_IN_CURRENT_NSE_UNIVERSE"
        ), axis=1,
    )
    cache = Path(history_cache)
    histories: dict[str, pd.DataFrame | None] = {}
    current_rows = []
    as_of = str(source_meta["cached_as_of_date"])
    for row in universe.to_dict("records"):
        path = cache / f"{row['ticker']}.csv"
        history = pd.read_csv(path) if path.is_file() else None
        histories[row["ticker"]] = history
        if history is not None:
            eligible = history.loc[history["date"].astype(str) <= as_of]
            if not eligible.empty:
                current_rows.append({"ticker": row["ticker"], "close": float(eligible.iloc[-1]["adjusted_close"])})
    prepared_universe = universe.rename(columns={"ticker": "Symbol", "company": "Company Name", "sector": "Industry"})
    boundaries = universe.rename(columns={"listing_date": "valid_from_date"})[["ticker", "valid_from_date"]].copy()
    boundaries["boundary_type"] = "OFFICIAL_NSE_SECURITY_LISTING_DATE"
    boundaries["evidence_source"] = "Current official NSE equity universe DATE OF LISTING"
    prepared = prepare_historical_baseline(
        prepared_universe, pd.DataFrame(current_rows), histories,
        as_of_date=as_of, history_start_boundaries=boundaries,
    )
    rankings = calculate_baseline_rankings(prepared.baseline_input)
    anchor_highs = prepared.anchors[["ticker", "recorded_high_price"]].rename(
        columns={"recorded_high_price": "baseline_recorded_high_price"}
    )
    rankings = rankings.merge(anchor_highs, on="ticker", how="left", validate="one_to_one")
    selected = rankings[["ticker", "company", "sector", "current_price", "ath_date",
                         "baseline_recorded_high_price",
                         "yoy_growth", "cagr_3y", "cagr_5y", "days_since_recorded_high",
                         "baseline_score", "sector_rank"]].rename(columns={
                             "ath_date": "baseline_recorded_high_date",
                             "sector_rank": "baseline_sector_rank",
                         })
    comparison = reference.merge(selected, on="ticker", how="left", validate="many_to_one")
    current_columns = [
        "ticker", "company", "sector", "research_v2_score",
        "research_v2_sector_rank", "v2_eligible", "v2_reason_code",
    ]
    current = market.loc[:, [column for column in current_columns if column in market.columns]].rename(
        columns={"company": "current_company", "sector": "current_sector"}
    )
    comparison = comparison.merge(current, on="ticker", how="left", validate="many_to_one")
    comparison["company"] = comparison["company"].fillna(comparison.get("current_company"))
    comparison["sector"] = comparison["sector"].fillna(comparison.get("current_sector"))
    comparison["comparison_snapshot_note"] = (
        "Professor and reconstructed Baseline use the workbook cached date; Research V2 fields are the "
        "accepted current snapshot and are not treated as same-date reproduction evidence."
    )
    for metric in ("yoy_growth", "cagr_3y", "cagr_5y"):
        ref_col, base_col = f"reference_{metric}", metric
        comparison[f"{metric}_difference"] = comparison[base_col] - comparison[ref_col]
        comparison[f"{metric}_rounded_match"] = (
            comparison[base_col].round(2).eq(comparison[ref_col]) & comparison[ref_col].notna()
        )
    comparison["recency_day_difference"] = (
        comparison["days_since_recorded_high"] - comparison["reference_days_since_recorded_high"]
    )
    comparison["recorded_high_date_match"] = (
        comparison["baseline_recorded_high_date"].eq(comparison["reference_recorded_high_date"])
        & comparison["reference_recorded_high_date"].notna()
    )
    comparison["disagreement_reason"] = "MATCH_OR_WITHIN_REPORTED_PRECISION"
    comparison.loc[comparison["ticker"].isna(), "disagreement_reason"] = "IDENTITY_NOT_EXACTLY_MATCHED"
    comparable = comparison["ticker"].notna()
    action_mismatch = comparable & comparison["reference_recorded_high"].notna() & comparison["current_price"].notna() & (
        comparison["reference_recorded_high"] / comparison["current_price"] > 4
    )
    comparison.loc[action_mismatch, "disagreement_reason"] = "CORPORATE_ACTION_OR_PRICE_BASIS_MISMATCH"
    other = comparable & ~action_mismatch & (
        ~comparison[[f"{m}_rounded_match" for m in ("yoy_growth", "cagr_3y", "cagr_5y")]].fillna(False).all(axis=1)
        | ~comparison["recorded_high_date_match"].fillna(False)
    )
    comparison.loc[other, "disagreement_reason"] = "DATA_SOURCE_DATE_OR_METHODOLOGY_DIFFERENCE"
    comparison["price_comparison_reason"] = comparison.apply(
        lambda row: "IDENTITY_OR_REFERENCE_PRICE_UNAVAILABLE"
        if pd.isna(row.get("ticker")) or pd.isna(row.get("reference_current_price")) or pd.isna(row.get("current_price"))
        else "GOOGLE_CURRENT_QUOTE_VS_REPAIRED_ADJUSTED_DAILY_CLOSE",
        axis=1,
    )
    comparison["cagr_comparison_reason"] = comparison.apply(
        lambda row: "REFERENCE_CAGR_UNAVAILABLE"
        if all(pd.isna(row.get(f"reference_{metric}")) for metric in ("yoy_growth", "cagr_3y", "cagr_5y"))
        else "SCREENER_REPORTED_ROUNDED_PERIODS_VS_EXACT_CALENDAR_ANCHORS",
        axis=1,
    )
    comparison["high_comparison_reason"] = comparison.apply(
        lambda row: "REFERENCE_HIGH_UNAVAILABLE" if pd.isna(row.get("reference_recorded_high_date"))
        else ("MIXED_CORPORATE_ACTION_OR_PRICE_SCALE" if row.get("disagreement_reason") == "CORPORATE_ACTION_OR_PRICE_BASIS_MISMATCH"
              else "NOMINAL_INTRADAY_OR_WEEKLY_HIGH_VS_ADJUSTED_DAILY_CLOSE"),
        axis=1,
    )
    comparison["comparison_explanation"] = comparison.apply(
        lambda row: "Exact identity not available in the current NSE universe; no substitution was made."
        if pd.isna(row.get("ticker")) else
        f"Price: {row['price_comparison_reason']}; CAGR: {row['cagr_comparison_reason']}; high/recency: {row['high_comparison_reason']}.",
        axis=1,
    )
    metric_rows = []
    directions = {"yoy_growth": True, "cagr_3y": True, "cagr_5y": True,
                  "days_since_recorded_high": False}
    for metric in METRICS:
        ref_col = f"reference_{metric}"
        pair = comparison.set_index("reference_ticker")[[ref_col, metric]].dropna()
        if metric == "days_since_recorded_high":
            matches = (pair[metric].round().eq(pair[ref_col].round())).sum()
        else:
            matches = pair[metric].round(2).eq(pair[ref_col]).sum()
        metric_rows.append({
            "metric": metric, "comparable_count": len(pair), "reported_precision_match_count": int(matches),
            "reported_precision_match_rate": float(matches / len(pair)) if len(pair) else None,
            "mean_absolute_difference": float((pair[metric] - pair[ref_col]).abs().mean()) if len(pair) else None,
            "spearman_rank_correlation": _rank_corr(pair[ref_col], pair[metric]),
            "top_5_overlap": _top_overlap(pair[ref_col], pair[metric], higher=directions[metric]),
        })
    for metric, reference_column, baseline_column in (
        ("current_price", "reference_current_price", "current_price"),
        ("recorded_high_price", "reference_recorded_high", "baseline_recorded_high_price"),
    ):
        pair = comparison.set_index("reference_ticker")[[reference_column, baseline_column]].dropna()
        tolerance = pair[reference_column].abs() * .001
        matches = (pair[baseline_column].sub(pair[reference_column]).abs() <= tolerance.clip(lower=.05)).sum()
        metric_rows.append({
            "metric": metric, "comparable_count": len(pair), "reported_precision_match_count": int(matches),
            "reported_precision_match_rate": float(matches / len(pair)) if len(pair) else None,
            "mean_absolute_difference": float((pair[baseline_column] - pair[reference_column]).abs().mean()) if len(pair) else None,
            "spearman_rank_correlation": _rank_corr(pair[reference_column], pair[baseline_column]),
            "top_5_overlap": _top_overlap(pair[reference_column], pair[baseline_column], higher=True),
        })
    date_pair = comparison[["reference_recorded_high_date", "baseline_recorded_high_date"]].dropna()
    date_matches = date_pair.iloc[:, 0].eq(date_pair.iloc[:, 1]).sum()
    metric_rows.append({
        "metric": "recorded_high_date", "comparable_count": len(date_pair),
        "reported_precision_match_count": int(date_matches),
        "reported_precision_match_rate": float(date_matches / len(date_pair)) if len(date_pair) else None,
        "mean_absolute_difference": None, "spearman_rank_correlation": None, "top_5_overlap": None,
    })
    metric_summary = pd.DataFrame(metric_rows)
    sector_rows = []
    matched = comparison.loc[comparison["ticker"].notna()].copy()
    for sector, group in matched.groupby("sector", sort=True):
        values: dict[str, Any] = {"sector": sector, "matched_stock_count": len(group)}
        for metric in METRICS:
            values[f"{metric}_rank_correlation"] = _rank_corr(group[f"reference_{metric}"], group[metric])
        sector_rows.append(values)
    sector_summary = pd.DataFrame(sector_rows)
    evaluation_path = Path(evaluation_summary_path)
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    primary = evaluation["horizons"][str(evaluation["primary_horizon_months"])]
    reference_verdict = "PARTIAL MATCH"
    improvement_verdict = "INSUFFICIENT EVIDENCE" if evaluation.get("very_low_primary_sample_size") else "NO CLEAR IMPROVEMENT"
    audit = {
        **source_meta, "benchmark_version": BENCHMARK_VERSION,
        "current_universe_count": int(len(market)), "classified_universe_count": int(len(universe)),
        "exact_identity_match_count": int(reference["ticker"].notna().sum()),
        "unmatched_count": int(reference["ticker"].isna().sum()),
        "baseline_eligible_at_reference_date": int(len(rankings)),
        "baseline_reconstruction_price_basis": (
            "Repaired Yahoo adjusted daily closes already cached by the project; the same series supplies "
            "the 2026-02-17 current anchor because no separate official NSE close snapshot for that date is present."
        ),
        "reference_verdict": reference_verdict,
        "reference_verdict_reason": (
            "Comparable inputs can be benchmarked, but the workbook has no sector taxonomy or computed "
            "sector-ranking formula and its cached external values mix sources and price bases."
        ),
        "research_v2_verdict": improvement_verdict,
        "research_v2_evidence": {
            "protocol_sha256": evaluation["protocol_sha256"],
            "primary_horizon_months": evaluation["primary_horizon_months"],
            "sector_date_observations": primary["rank_ic_observation_count"],
            "research_v2_mean_rank_ic": primary["research_v2_rank_ic"]["mean"],
            "matched_baseline_mean_rank_ic": primary["matched_baseline_rank_ic"]["mean"],
            "pairwise_accuracy_research_v2": primary["pairwise"]["research_v2"]["pairwise_accuracy"],
            "pairwise_accuracy_matched_baseline": primary["pairwise"]["matched_baseline"]["pairwise_accuracy"],
            "warning": "Outcome-blind and preregistered, but only three primary sector-date observations exist.",
        },
        "ranking_claim_boundary": (
            "No professor sector rank, combined score, or top-k portfolio is claimed because none is calculated by the workbook."
        ),
    }
    return ProfessorReferenceResult(reference, comparison, sector_summary, metric_summary, audit)


def export_professor_reference(result: ProfessorReferenceResult, output_dir: str | Path) -> Path:
    """Write deterministic, reviewable benchmark evidence."""
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    frames = {
        "reference_cells.csv": result.reference,
        "stock_comparison.csv": result.stock_comparison,
        "sector_summary.csv": result.sector_summary,
        "metric_summary.csv": result.metric_summary,
    }
    files = []
    for name, frame in frames.items():
        path = root / name
        frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")
        files.append({"path": name, "sha256": sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size})
    audit_path = root / "audit_summary.json"
    audit_path.write_text(json.dumps(result.audit, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    files.append({"path": audit_path.name, "sha256": sha256(audit_path.read_bytes()).hexdigest(), "size": audit_path.stat().st_size})
    manifest = {"schema_version": 1, "benchmark_version": BENCHMARK_VERSION, "files": files}
    manifest["benchmark_fingerprint"] = sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return manifest_path
