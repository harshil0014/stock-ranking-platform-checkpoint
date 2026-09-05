"""Auditable OK Strategy workbook benchmark and optional Screener export adapter.

The workbook and any user-supplied Screener export are evidence.  Neither is
used to change the accepted Baseline V1 or Research V2 calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
import math
from numbers import Real
from pathlib import Path
import re
from typing import Any

import pandas as pd

from stock_ranker.professor_reference import _XlsxCells


STRATEGY_VERSION = "ok_strategy_master_sheet_v4_3"
BENCHMARK_VERSION = "professor_strategy_benchmark_v1"


@dataclass(frozen=True, slots=True)
class ProfessorStrategyResult:
    securities: pd.DataFrame
    workbook_ranking: pd.DataFrame
    diagnostics: pd.DataFrame
    audit: dict[str, Any]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _date(value: Any) -> str | None:
    if _number(value) is None:
        return None
    return (datetime(1899, 12, 30) + timedelta(days=float(value))).date().isoformat()


def _code(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if text.startswith(("NSE:", "BOM:", "BSE:")):
        return text.replace("BSE:", "BOM:", 1)
    return f"NSE:{text}"


def extract_ok_strategy_workbook(workbook_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Extract cached SIP ranking and CAGR evidence with cell provenance."""
    path = Path(workbook_path).resolve()
    if not path.is_file() or path.suffix.lower() != ".xlsx":
        raise ValueError("OK Strategy reference must be an existing .xlsx file")
    cells = _XlsxCells(path)
    required = {"Instructions", "SIP Portfolio", "CAGR"}
    if not required.issubset(cells.sheet_names):
        raise ValueError(f"workbook is missing required sheets: {sorted(required - set(cells.sheet_names))}")

    cagr_rows: list[dict[str, Any]] = []
    for row in range(3, 500):
        code = _code(cells.value("CAGR", f"A{row}"))
        if not code:
            continue
        cagr_rows.append({
            "requested_code": code,
            "workbook_company": cells.value("CAGR", f"B{row}"),
            "workbook_current_price": _number(cells.value("CAGR", f"C{row}")),
            "workbook_cagr_10y": _number(cells.value("CAGR", f"D{row}")),
            "workbook_cagr_5y": _number(cells.value("CAGR", f"E{row}")),
            "workbook_cagr_3y": _number(cells.value("CAGR", f"F{row}")),
            "workbook_cagr_1y": _number(cells.value("CAGR", f"G{row}")),
            "workbook_industry": cells.value("CAGR", f"H{row}"),
            "workbook_market_cap": _number(cells.value("CAGR", f"I{row}")),
            "cagr_row": row,
            "cagr_cells": f"CAGR!A{row}:I{row}",
        })
    cagr = pd.DataFrame(cagr_rows)
    if not cagr.empty:
        substantive = [column for column in cagr.columns if column not in {"requested_code", "cagr_row", "cagr_cells"}]
        conflicts = cagr.groupby("requested_code", dropna=False)[substantive].nunique(dropna=False).max(axis=1)
        if (conflicts > 1).any():
            raise ValueError(f"conflicting duplicate CAGR rows: {sorted(conflicts[conflicts > 1].index)}")
        provenance = cagr.groupby("requested_code", sort=False).agg(
            cagr_rows=("cagr_row", lambda values: ";".join(str(value) for value in values)),
            cagr_cells=("cagr_cells", lambda values: ";".join(str(value) for value in values)),
        )
        cagr = cagr.drop_duplicates("requested_code", keep="first")
        cagr = cagr.drop(columns=["cagr_row", "cagr_cells"]).merge(
            provenance.reset_index(), on="requested_code", how="left", validate="one_to_one"
        )

    sip_rows: list[dict[str, Any]] = []
    master_rank_formula = cells.formula("SIP Portfolio", "N7")
    master_rank_attributes = cells.formula_attributes.get(("SIP Portfolio", "N7"), {})
    shared_rank_range = master_rank_attributes.get("ref") if master_rank_attributes.get("t") == "shared" else None
    for row in range(7, 500):
        raw = cells.value("SIP Portfolio", f"B{row}")
        if raw is None or str(raw).strip().casefold() == "total":
            continue
        code = _code(raw)
        if not code:
            continue
        formula = cells.formula("SIP Portfolio", f"N{row}")
        rank_attributes = cells.formula_attributes.get(("SIP Portfolio", f"N{row}"), {})
        if not formula and shared_rank_range == "N7:N20" and rank_attributes.get("t") == "shared" and rank_attributes.get("si") == master_rank_attributes.get("si"):
            formula = re.sub(r"I7", f"I{row}", str(master_rank_formula), count=1)
        sip_rows.append({
            "requested_code": code,
            "workbook_company": cells.value("SIP Portfolio", f"C{row}"),
            "workbook_sip_current_price": _number(cells.value("SIP Portfolio", f"D{row}")),
            "workbook_sip_shares": _number(cells.value("SIP Portfolio", f"E{row}")),
            "workbook_sip_average_price": _number(cells.value("SIP Portfolio", f"F{row}")),
            "workbook_sip_invested": _number(cells.value("SIP Portfolio", f"G{row}")),
            "workbook_sip_current_value": _number(cells.value("SIP Portfolio", f"H{row}")),
            "workbook_sip_profit_loss": _number(cells.value("SIP Portfolio", f"I{row}")),
            "workbook_sip_cagr_10y": _number(cells.value("SIP Portfolio", f"J{row}")),
            "workbook_sip_cagr_5y": _number(cells.value("SIP Portfolio", f"K{row}")),
            "workbook_sip_cagr_3y": _number(cells.value("SIP Portfolio", f"L{row}")),
            "workbook_sip_rank": _number(cells.value("SIP Portfolio", f"N{row}")),
            "sip_rank_formula": formula,
            "sip_row": row,
            "sip_cells": f"SIP Portfolio!B{row}:N{row}",
        })
    sip = pd.DataFrame(sip_rows)
    if sip.empty:
        raise ValueError("workbook contains no cached SIP Portfolio records")
    if sip["requested_code"].duplicated().any():
        raise ValueError("workbook SIP Portfolio contains duplicate security codes")
    expected_formula = sip.apply(
        lambda item: bool(re.fullmatch(rf"rank\(I{int(item['sip_row'])},\$I\$7:\$I\$20\)",
                                       str(item["sip_rank_formula"] or ""), flags=re.IGNORECASE)), axis=1,
    )
    calculated = sip["workbook_sip_profit_loss"].rank(method="min", ascending=False)
    rank_match = calculated.eq(sip["workbook_sip_rank"]).all()
    metadata = {
        "schema_version": 1,
        "workbook_version": STRATEGY_VERSION,
        "workbook_filename": path.name,
        "workbook_sha256": sha256(path.read_bytes()).hexdigest(),
        "workbook_as_of_date": _date(cells.value("Instructions", "L1")),
        "worksheet_count": len(cells.sheet_names),
        "worksheet_names": list(cells.sheet_names),
        "formula_count": len(cells.formulas),
        "googlefinance_formula_count": sum("GOOGLEFINANCE" in formula.upper() for formula in cells.formulas.values()),
        "rank_formula_count": int(expected_formula.sum()),
        "rank_formula_definition_count": sum(bool(re.search(r"\bRANK(?:\.EQ|\.AVG)?\s*\(", formula, re.I)) for formula in cells.formulas.values()),
        "rank_formula_shared_range": shared_rank_range,
        "sip_record_count": len(sip),
        "sip_rank_formulas_exact": bool(expected_formula.all()),
        "sip_cached_ranks_recalculate_exactly": bool(rank_match),
        "sip_monthly_amount": _number(cells.value("SIP Portfolio", "B1")),
        "sip_months": _number(cells.value("SIP Portfolio", "B2")),
        "sip_interval_days": _number(cells.value("SIP Portfolio", "B3")),
        "methodology_boundary": (
            "The workbook's only explicit stock ranking is Excel RANK over SIP Portfolio profit/loss. "
            "CAGR values and industries are cached evidence, not a disclosed formula for the supplied 14-stock ordering."
        ),
    }
    return sip, cagr, metadata


def _screener_export(path_value: str | Path | None, source_date: date | None) -> tuple[pd.DataFrame, dict[str, Any]]:
    if path_value is None:
        return pd.DataFrame(columns=["requested_code", "screener_industry"]), {
            "status": "SCREENER_EXPORT_NOT_SUPPLIED", "row_count": 0, "source_date": None,
            "policy": "No scraping or API is attempted; Screener states that it provides no API.",
        }
    path = Path(path_value).resolve()
    if not path.is_file() or source_date is None:
        raise ValueError("Screener evidence requires an existing CSV and an explicit source date")
    frame = pd.read_csv(path)
    lookup = {str(column).strip().casefold(): column for column in frame.columns}
    industry = lookup.get("industry")
    nse = lookup.get("nse code")
    bse = lookup.get("bse code")
    if industry is None or (nse is None and bse is None):
        raise ValueError("Screener export requires Industry and NSE Code and/or BSE Code columns")
    rows: list[dict[str, str]] = []
    for item in frame.to_dict("records"):
        industry_value = str(item.get(industry) or "").strip()
        if not industry_value:
            continue
        if nse is not None and pd.notna(item.get(nse)) and str(item[nse]).strip():
            rows.append({"requested_code": _code(item[nse]), "screener_industry": industry_value})
        if bse is not None and pd.notna(item.get(bse)) and str(item[bse]).strip():
            raw = str(item[bse]).strip().removesuffix(".0")
            rows.append({"requested_code": f"BOM:{raw}", "screener_industry": industry_value})
    result = pd.DataFrame(rows).drop_duplicates()
    if result["requested_code"].duplicated().any():
        raise ValueError("Screener export maps one exact security code to conflicting industries")
    return result, {
        "status": "USER_SUPPLIED_EXPORT_VALIDATED", "row_count": len(result),
        "source_date": source_date.isoformat(), "sha256": sha256(path.read_bytes()).hexdigest(),
        "license_boundary": "User-supplied personal export; redistribution rights are not inferred.",
    }


def _comparison(reference: pd.Series, candidate: pd.Series, label: str) -> dict[str, Any]:
    pair = pd.concat([reference.rename("reference"), candidate.rename("candidate")], axis=1).dropna()
    if len(pair) < 2:
        return {"candidate": label, "count": len(pair), "spearman": None, "pairwise_agreement": None, "top_5_overlap": None}
    rank = pair["candidate"].rank(method="min", ascending=True)
    spearman = pair["reference"].rank(method="average").corr(rank.rank(method="average"))
    agree = total = 0
    records = pair.assign(candidate_rank=rank).to_dict("records")
    for index, left in enumerate(records):
        for right in records[index + 1:]:
            total += 1
            agree += int((left["reference"] < right["reference"]) == (left["candidate_rank"] < right["candidate_rank"]))
    count = min(5, len(pair))
    ref_top = set(pair.nsmallest(count, "reference").index)
    candidate_top = set(rank.nsmallest(count).index)
    return {"candidate": label, "count": len(pair), "spearman": float(spearman),
            "pairwise_agreement": agree / total, "top_5_overlap": len(ref_top & candidate_top) / count}


def benchmark_professor_strategy(
    workbook_path: str | Path, *, request_path: str | Path, acceptance_csv: str | Path,
    screener_export_path: str | Path | None = None, screener_source_date: date | None = None,
) -> ProfessorStrategyResult:
    """Compare workbook evidence with the exact supplied cohort and accepted platform evidence."""
    sip, cagr, source = extract_ok_strategy_workbook(workbook_path)
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    reference = pd.DataFrame(request.get("reference_ranking", [])).rename(columns={"code": "requested_code", "rank": "reference_rank"})
    reference["requested_code"] = reference["requested_code"].map(_code)
    acceptance = pd.read_csv(acceptance_csv, low_memory=False)
    if acceptance["requested_code"].duplicated().any():
        raise ValueError("acceptance evidence contains duplicate requested_code values")
    expected = {_code(value) for value in request.get("universe", [])}
    if set(acceptance["requested_code"].map(_code)) != expected:
        raise ValueError("acceptance evidence does not match the supplied exact-code universe")
    acceptance["requested_code"] = acceptance["requested_code"].map(_code)
    screener, screener_meta = _screener_export(screener_export_path, screener_source_date)
    if "reference_rank" in acceptance.columns:
        supplied = acceptance.set_index("requested_code")["reference_rank"]
        expected_ranks = reference.set_index("requested_code")["reference_rank"]
        for code, value in expected_ranks.items():
            if code not in supplied.index or _number(supplied.loc[code]) != _number(value):
                raise ValueError("acceptance reference ranks differ from the supplied request")
        frame = acceptance.copy()
    else:
        frame = acceptance.merge(reference, on="requested_code", how="left", validate="one_to_one")
    frame = frame.merge(sip, on="requested_code", how="left", suffixes=("", "_sip"), validate="one_to_one")
    if not cagr.empty:
        frame = frame.merge(cagr, on="requested_code", how="left", suffixes=("", "_cagr"), validate="one_to_one")
    frame = frame.merge(screener, on="requested_code", how="left", validate="one_to_one")
    frame["workbook_evidence_status"] = frame["workbook_sip_rank"].notna().map(
        {True: "SIP_RANK_AND_CACHED_FIELDS_AVAILABLE", False: "NOT_IN_WORKBOOK_SIP_COHORT"}
    )
    frame["screener_evidence_status"] = frame["screener_industry"].notna().map(
        {True: "EXACT_CODE_EXPORT_MATCH", False: screener_meta["status"]}
    )
    frame["strategy_disagreement_reason"] = frame.apply(
        lambda item: (
            "EXACT_POSITION_MATCH" if pd.notna(item.get("reference_rank")) and item.get("reference_rank") == item.get("workbook_sip_rank")
            else "SUPPLIED_ORDER_DIFFERS_FROM_EXPLICIT_SIP_RANK" if pd.notna(item.get("reference_rank"))
            else "NO_SUPPLIED_REFERENCE_RANK"
        ), axis=1,
    )
    ranked = frame.loc[frame["reference_rank"].notna()].copy().set_index("requested_code")
    if set(ranked.index) != set(sip["requested_code"]):
        raise ValueError("workbook SIP cohort does not exactly match the supplied 14-stock ranking")
    diagnostics = [_comparison(ranked["reference_rank"], ranked["workbook_sip_rank"], "explicit_workbook_sip_rank")]
    for column, label in (("workbook_sip_cagr_10y", "cached_10y_cagr"),
                          ("workbook_sip_cagr_5y", "cached_5y_cagr"),
                          ("workbook_sip_cagr_3y", "cached_3y_cagr")):
        value_rank = ranked[column].rank(method="min", ascending=False)
        diagnostics.append(_comparison(ranked["reference_rank"], value_rank, label))
    diagnostics_frame = pd.DataFrame(diagnostics)
    sip_diag = diagnostics[0]
    exact = int((ranked["reference_rank"] == ranked["workbook_sip_rank"]).sum())
    audit = {
        **source,
        "benchmark_version": BENCHMARK_VERSION,
        "requested_security_count": len(frame),
        "reference_ranking_count": len(ranked),
        "exact_sip_rank_position_count": exact,
        "explicit_sip_rank_spearman": sip_diag["spearman"],
        "explicit_sip_rank_pairwise_agreement": sip_diag["pairwise_agreement"],
        "explicit_sip_rank_top_5_overlap": sip_diag["top_5_overlap"],
        "reference_verdict": "REFERENCE MATCH" if exact == len(ranked) else "PARTIAL MATCH",
        "reference_verdict_reason": (
            "The workbook SIP profit/loss rank is the strongest explicit reproducible signal, but it does not exactly equal "
            "the supplied ordering. The exact override, snapshot, or additional ordering rule is not disclosed."
        ),
        "baseline_relationship": (
            "Baseline V1 is a defensible project operationalization of price growth and recorded-high signals, not the "
            "workbook's SIP profit/loss ranking; sector-relative Baseline ranks are not compared as a global rank list."
        ),
        "research_v2_verdict": "INSUFFICIENT EVIDENCE" if int(frame["research_v2_eligible"].fillna(False).sum()) == 0 else "NO CLEAR IMPROVEMENT",
        "screener_evidence": screener_meta,
        "smallest_required_professor_input": (
            "The exact rule, overrides, and as-of snapshot used to transform the workbook SIP rank into the supplied 14-stock order."
        ),
        "scientific_boundary": "No score, rank, sector, formula, weight, eligibility rule, or frozen outcome was changed.",
    }
    return ProfessorStrategyResult(frame, ranked.reset_index(), diagnostics_frame, audit)


def export_professor_strategy(result: ProfessorStrategyResult, output_dir: str | Path) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for name, frame in (("professor_strategy_comparison.csv", result.securities),
                        ("workbook_sip_ranking.csv", result.workbook_ranking),
                        ("strategy_diagnostics.csv", result.diagnostics)):
        path = root / name
        frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")
        files.append({"path": name, "sha256": sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size})
    summary = root / "strategy_summary.json"
    summary.write_text(json.dumps(result.audit, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    files.append({"path": summary.name, "sha256": sha256(summary.read_bytes()).hexdigest(), "size": summary.stat().st_size})
    manifest = {"schema_version": 1, "benchmark_version": BENCHMARK_VERSION, "files": files}
    manifest["strategy_fingerprint"] = sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return path
