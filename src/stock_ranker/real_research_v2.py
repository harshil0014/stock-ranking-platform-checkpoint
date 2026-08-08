"""Safe NSE XBRL and frozen real Research V2 preparation boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
from typing import Any
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from stock_ranker.historical_baseline import (
    calculate_prepared_real_rankings,
    load_historical_baseline_bundle,
)
from stock_ranker.baseline import calculate_baseline_rankings
from stock_ranker.config import BaselineConfig
from stock_ranker.research_v2 import ResearchV2Inputs, ResearchV2Result, calculate_research_v2
from stock_ranker.v2_config import ResearchV2Config
from stock_ranker.v2_contracts import FUNDAMENTAL_COLUMNS, PRICE_HISTORY_COLUMNS, UNIVERSE_COLUMNS, V2_OUTPUT_COLUMNS


RANKING_DATE = "2026-08-07"
FILING_CUTOFF = "2026-08-07T15:30:00+05:30"
MAX_XBRL_BYTES = 15_000_000
BUNDLE_VERSION = "nse_real_research_v2_bundle_v1"
FUNDAMENTAL_DATA_CONTRACT_VERSION = "nse_audited_standalone_fundamentals_v1"
IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True, slots=True)
class XBRLContext:
    context_id: str
    entity_identifier: str
    start_date: str | None
    end_date: str | None
    instant: str | None
    dimensions: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class XBRLFact:
    concept: str
    namespace: str
    context_id: str
    unit_id: str | None
    decimals: str | None
    value: str


@dataclass(frozen=True, slots=True)
class XBRLDocument:
    contexts: dict[str, XBRLContext]
    units: dict[str, str]
    facts: tuple[XBRLFact, ...]
    taxonomy_family: str


@dataclass(frozen=True, slots=True)
class RealResearchV2Bundle:
    path: Path
    universe: pd.DataFrame
    prices: pd.DataFrame
    fundamentals: pd.DataFrame
    eligibility: pd.DataFrame
    rankings: pd.DataFrame
    comparison: pd.DataFrame
    comparison_sector_summary: pd.DataFrame
    provenance: pd.DataFrame
    metadata: dict[str, Any]
    fingerprint: str


def _nse_timestamp(value: object) -> datetime:
    parsed = datetime.strptime(str(value), "%d-%b-%Y %H:%M:%S")
    return parsed.replace(tzinfo=IST)


def select_point_in_time_filing(
    rows: list[dict[str, object]],
    cutoff: datetime,
) -> tuple[dict[str, object] | None, str]:
    """Select the latest disseminated annual consolidated NSE filing revision."""

    if cutoff.tzinfo is None:
        raise ValueError("filing cutoff must be timezone-aware")
    eligible: list[tuple[dict[str, object], datetime, datetime]] = []
    for row in rows:
        try:
            dissemination = _nse_timestamp(row["creation_Date"])
            period_end = datetime.strptime(str(row["qe_Date"]), "%d-%b-%Y")
        except (KeyError, TypeError, ValueError):
            continue
        if dissemination <= cutoff and period_end.date() <= cutoff.date():
            eligible.append((row, dissemination, period_end))
    if not eligible:
        return None, "NO_ELIGIBLE_NSE_FILING"
    annual = [item for item in eligible if (item[2].month, item[2].day) == (3, 31)]
    if not annual:
        return None, "NO_COMPARABLE_PRIOR_PERIOD"
    latest_period = max(item[2] for item in annual)
    period_rows = [item for item in annual if item[2] == latest_period]
    consolidated = [
        item for item in period_rows
        if str(item[0].get("consolidated", "")).strip().lower() == "consolidated"
    ]
    if not consolidated:
        return None, "NO_CONSOLIDATED_FILING"
    selected = max(
        consolidated,
        key=lambda item: (item[1], str(item[0].get("seq_Id", ""))),
    )
    return selected[0], "SELECTED"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _namespace(tag: str) -> str:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


def taxonomy_family_from_filename(filename: str) -> str:
    match = re.search(r"INTEGRATED_FILING_(.+?)_\d+_\d+_WEB\.xml$", filename, re.I)
    if not match:
        raise ValueError(f"unsupported NSE XBRL filename: {filename}")
    return match.group(1).upper()


def parse_nse_xbrl(data: bytes, *, filename: str) -> XBRLDocument:
    if not isinstance(data, bytes) or not data or len(data) > MAX_XBRL_BYTES:
        raise ValueError("XBRL must be nonempty and no larger than 15 MB")
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("XBRL DTD and entity declarations are forbidden")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"malformed XBRL XML: {exc}") from exc
    contexts: dict[str, XBRLContext] = {}
    units: dict[str, str] = {}
    for element in root.iter():
        local = _local(element.tag)
        if local == "context":
            context_id = str(element.get("id") or "").strip()
            if not context_id or context_id in contexts:
                raise ValueError("XBRL context IDs must be nonblank and unique")
            values: dict[str, str] = {}
            dimensions = []
            entity = ""
            for child in element.iter():
                child_local = _local(child.tag)
                text = (child.text or "").strip()
                if child_local in {"startDate", "endDate", "instant"}:
                    values[child_local] = text
                elif child_local == "identifier":
                    entity = text
                elif child_local in {"explicitMember", "typedMember"}:
                    dimensions.append((str(child.get("dimension") or ""), text))
            duration = "startDate" in values or "endDate" in values
            if duration == ("instant" in values):
                raise ValueError(f"XBRL context {context_id} must be duration or instant")
            contexts[context_id] = XBRLContext(
                context_id, entity, values.get("startDate"), values.get("endDate"),
                values.get("instant"), tuple(sorted(dimensions)),
            )
        elif local == "unit":
            unit_id = str(element.get("id") or "").strip()
            measures = [
                (child.text or "").strip() for child in element.iter()
                if _local(child.tag) == "measure" and (child.text or "").strip()
            ]
            if not unit_id or not measures or unit_id in units:
                raise ValueError("XBRL units must have unique IDs and measures")
            units[unit_id] = "/".join(measures)
    facts: list[XBRLFact] = []
    seen: dict[tuple[str, str, str | None], str] = {}
    for element in root.iter():
        context_id = element.get("contextRef")
        if context_id is None:
            continue
        if context_id not in contexts:
            raise ValueError(f"XBRL fact references unknown context {context_id}")
        fact = XBRLFact(
            _local(element.tag), _namespace(element.tag), context_id,
            element.get("unitRef"), element.get("decimals"),
            (element.text or "").strip(),
        )
        key = (fact.concept, fact.context_id, fact.unit_id)
        if key in seen and seen[key] != fact.value:
            raise ValueError(f"conflicting XBRL facts for {fact.concept}/{fact.context_id}")
        if key not in seen:
            facts.append(fact)
            seen[key] = fact.value
    return XBRLDocument(contexts, units, tuple(facts), taxonomy_family_from_filename(filename))


def extract_exact_reported_metrics(
    document: XBRLDocument, mapping: dict[str, Any], period_end: str
) -> tuple[dict[str, float], dict[str, Any], list[str]]:
    metrics: dict[str, float] = {}
    provenance: dict[str, Any] = {}
    missing: list[str] = []
    for metric, specification in mapping["metrics"].items():
        concepts = set(specification["concepts"])
        candidates = []
        for fact in document.facts:
            if fact.concept not in concepts or fact.unit_id is None:
                continue
            context = document.contexts[fact.context_id]
            if context.end_date != period_end and context.instant != period_end:
                continue
            period_type = specification.get("period_type")
            if period_type == "instant" and context.instant != period_end:
                continue
            if period_type == "annual_duration":
                if context.start_date is None or context.end_date != period_end:
                    continue
                start = datetime.strptime(context.start_date, "%Y-%m-%d").date()
                end = datetime.strptime(context.end_date, "%Y-%m-%d").date()
                if not 360 <= (end - start).days <= 370:
                    continue
            unit = document.units.get(fact.unit_id, "")
            if unit.lower().split(":")[-1] != str(specification["unit"]).lower():
                continue
            try:
                value = float(fact.value)
            except ValueError:
                continue
            if np.isfinite(value):
                candidates.append((fact, context, value, unit))
        distinct = {item[2] for item in candidates}
        if not candidates:
            missing.append(metric)
        elif len(distinct) != 1:
            raise ValueError(f"AMBIGUOUS_XBRL_FACT:{metric}")
        else:
            fact, context, value, unit = candidates[0]
            metrics[metric] = value
            provenance[metric] = {
                "concept": fact.concept, "context_id": fact.context_id,
                "unit": unit, "period_start": context.start_date,
                "period_end": context.end_date, "instant": context.instant,
            }
    return metrics, provenance, missing


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def build_matched_cohort_comparison(
    universe: pd.DataFrame,
    baseline_input: pd.DataFrame,
    original_baseline_rankings: pd.DataFrame,
    research_v2_rankings: pd.DataFrame,
    eligibility: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare unchanged Baseline V1 and Research V2 on one eligible cohort."""

    eligible_tickers = set(research_v2_rankings["ticker"].astype(str))
    matched_input = baseline_input.loc[
        baseline_input["ticker"].astype(str).isin(eligible_tickers)
    ].copy()
    matched_baseline = (
        calculate_baseline_rankings(matched_input, BaselineConfig())
        if not matched_input.empty else original_baseline_rankings.iloc[0:0].copy()
    )
    comparison = universe.copy().merge(
        original_baseline_rankings.loc[:, ["ticker", "sector_rank", "baseline_score"]].rename(
            columns={"sector_rank": "original_baseline_sector_rank"}
        ), on="ticker", how="left",
    ).merge(
        matched_baseline.loc[:, ["ticker", "sector_rank"]].rename(
            columns={"sector_rank": "matched_baseline_sector_rank"}
        ), on="ticker", how="left",
    ).merge(
        research_v2_rankings.loc[:, ["ticker", "sector_rank", "research_v2_score"]].rename(
            columns={"sector_rank": "research_v2_sector_rank"}
        ), on="ticker", how="left",
    ).merge(
        eligibility.loc[:, ["ticker", "eligible", "reason_code", "reason"]],
        on="ticker", how="left",
    )
    peer_counts = research_v2_rankings.groupby("sector")["ticker"].size().rename("eligible_peer_count")
    comparison = comparison.merge(peer_counts, on="sector", how="left")
    comparison["eligible_peer_count"] = comparison["eligible_peer_count"].fillna(0).astype(int)
    comparison["comparison_status"] = np.where(
        ~comparison["eligible"].astype(bool), "INELIGIBLE",
        np.where(comparison["eligible_peer_count"].eq(1), "SINGLE_ELIGIBLE_PEER", "MATCHED_COHORT"),
    )
    comparison["rank_movement"] = np.where(
        comparison["comparison_status"].eq("MATCHED_COHORT"),
        comparison["matched_baseline_sector_rank"] - comparison["research_v2_sector_rank"],
        np.nan,
    )
    sector_rows = []
    for sector, group in comparison.groupby("sector", sort=True):
        eligible_group = group.loc[group["eligible"].astype(bool)]
        peer_count = len(eligible_group)
        baseline_order = eligible_group.sort_values(
            ["matched_baseline_sector_rank", "ticker"], kind="stable"
        )["ticker"].tolist()
        v2_order = eligible_group.sort_values(
            ["research_v2_sector_rank", "ticker"], kind="stable"
        )["ticker"].tolist()
        baseline_top = baseline_order[:5] if peer_count >= 5 else []
        v2_top = v2_order[:5] if peer_count >= 5 else []
        sector_rows.append({
            "sector": sector, "eligible_peer_count": peer_count,
            "comparison_status": "SINGLE_ELIGIBLE_PEER" if peer_count == 1 else ("MATCHED_COHORT" if peer_count > 1 else "NO_ELIGIBLE_PEER"),
            "matched_baseline_order": "|".join(baseline_order),
            "research_v2_order": "|".join(v2_order),
            "baseline_top_5": "|".join(baseline_top),
            "research_v2_top_5": "|".join(v2_top),
            "top_5_overlap": "|".join(sorted(set(baseline_top) & set(v2_top))),
            "entered_research_v2_top_5": "|".join(sorted(set(v2_top) - set(baseline_top))),
            "left_research_v2_top_5": "|".join(sorted(set(baseline_top) - set(v2_top))),
            "research_v2_exclusions": int((~group["eligible"].astype(bool)).sum()),
        })
    return comparison, pd.DataFrame(sector_rows)


def prepare_real_research_v2_bundle(
    raw_root: str | Path,
    baseline_root: str | Path,
    mapping_path: str | Path,
    output_root: str | Path,
    annual_report_acquisition_root: str | Path | None = None,
    annual_report_audit_root: str | Path | None = None,
    annual_report_mapping_path: str | Path | None = None,
) -> str:
    raw = Path(raw_root).resolve()
    output = Path(output_root).resolve()
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    output.mkdir(parents=True)
    baseline = load_historical_baseline_bundle(baseline_root)
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    universe = baseline.eligibility.loc[:, ["ticker", "company", "sector"]].copy()
    history = pd.read_csv(Path(baseline_root) / "historical_prices.csv")
    boundaries = pd.read_csv(Path(baseline_root) / "security_history_boundaries.csv")
    for item in boundaries.to_dict("records"):
        history = history.loc[
            ~history["ticker"].eq(item["ticker"])
            | history["date"].ge(item["valid_from_date"])
        ]
    prices = history.loc[:, ["ticker", "date", "adjusted_close"]].copy()
    provenance_raw = json.loads((raw / "filing_provenance.json").read_text(encoding="utf-8"))
    provenance_rows: list[dict[str, Any]] = []
    fundamental_rows: list[dict[str, Any]] = []
    eligibility_rows: list[dict[str, Any]] = []
    identity = universe.set_index("ticker")
    for entry in sorted(provenance_raw, key=lambda row: row["ticker"]):
        ticker = entry["ticker"]
        reason_code = entry["selection_status"]
        reason = "No eligible official annual consolidated filing was selected."
        details: dict[str, Any] = {}
        taxonomy_family = None
        if reason_code == "SELECTED":
            selected = entry["selected_metadata"]
            xbrl_path = raw / entry["xbrl_path"]
            try:
                document = parse_nse_xbrl(xbrl_path.read_bytes(), filename=xbrl_path.name.split("__", 1)[1])
                taxonomy_family = document.taxonomy_family
                if taxonomy_family not in mapping["taxonomy_families"]:
                    reason_code = "UNSUPPORTED_NSE_TAXONOMY"
                    reason = f"Taxonomy family {taxonomy_family} has no approved exact mapping."
                else:
                    metrics, details, missing = extract_exact_reported_metrics(
                        document, mapping, datetime.strptime(selected["qe_Date"], "%d-%b-%Y").date().isoformat()
                    )
                    if missing:
                        reason_code = "MISSING_REQUIRED_ACCOUNTING_FACT"
                        reason = "Official XBRL does not explicitly report accepted canonical values: " + ", ".join(missing)
                    else:
                        reason_code = "ELIGIBLE"
                        reason = "All exact reported fundamental facts were available."
                        fundamental_rows.append({
                            "ticker": ticker,
                            "period_end": datetime.strptime(selected["qe_Date"], "%d-%b-%Y").date().isoformat(),
                            "available_date": datetime.strptime(selected["creation_Date"], "%d-%b-%Y %H:%M:%S").date().isoformat(),
                            **metrics,
                        })
            except ValueError as exc:
                reason_code = "AMBIGUOUS_XBRL_FACT" if "AMBIGUOUS" in str(exc) else "UNSUPPORTED_NSE_TAXONOMY"
                reason = str(exc)
        selected = entry.get("selected_metadata", {})
        provenance_rows.append({
            "ticker": ticker, "selection_status": entry["selection_status"],
            "reason_code": reason_code, "taxonomy_family": taxonomy_family,
            "period_end": selected.get("qe_Date"), "submission_type": selected.get("type_Sub"),
            "statement_basis": selected.get("consolidated"), "audited": selected.get("audited"),
            "broadcast_timestamp": selected.get("broadcast_Date"),
            "exchange_dissemination_timestamp": selected.get("creation_Date"),
            "revision_timestamp": selected.get("revised_Date"),
            "revision_remarks": selected.get("revision_Remark"),
            "metadata_sha256": entry.get("metadata_sha256"),
            "source_xbrl_url": entry.get("xbrl_url"),
            "xbrl_sha256": entry.get("xbrl_sha256"),
            "fact_provenance": json.dumps(details, sort_keys=True, separators=(",", ":")),
        })
        ident = identity.loc[ticker]
        eligibility_rows.append({
            "ticker": ticker, "company": ident["company"], "sector": ident["sector"],
            "ranking_date": RANKING_DATE, "eligible": reason_code == "ELIGIBLE",
            "reason_code": reason_code, "reason": reason,
        })
    annual_report_enabled = all(value is not None for value in (
        annual_report_acquisition_root, annual_report_audit_root,
        annual_report_mapping_path,
    ))
    annual_report_summary: dict[str, Any] = {}
    annual_coverage_rows: list[dict[str, Any]] = []
    if any(value is not None for value in (
        annual_report_acquisition_root, annual_report_audit_root,
        annual_report_mapping_path,
    )) and not annual_report_enabled:
        raise ValueError("all annual-report rescue paths must be supplied together")
    if annual_report_enabled:
        annual_root = Path(annual_report_acquisition_root).resolve()
        audit_root = Path(annual_report_audit_root).resolve()
        annual_mapping_file = Path(annual_report_mapping_path).resolve()
        annual_mapping = json.loads(annual_mapping_file.read_text(encoding="utf-8"))
        if annual_mapping.get("fundamental_data_contract_version") != FUNDAMENTAL_DATA_CONTRACT_VERSION:
            raise ValueError("unexpected fundamental data contract version")
        if annual_mapping.get("reporting_basis") != "STANDALONE":
            raise ValueError("real Research V2 fundamentals must use the audited standalone basis")
        annual_provenance = {
            row["ticker"]: row for row in json.loads(
                (annual_root / "annual_report_provenance.json").read_text(encoding="utf-8")
            )
        }
        annual_audit = {
            row["ticker"]: row for row in json.loads(
                (audit_root / "candidate_audit.json").read_text(encoding="utf-8")
            )
        }
        accepted = {row["ticker"]: row for row in annual_mapping["accepted"]}
        reviewed_exclusions = {
            row["ticker"]: row for row in annual_mapping.get("reviewed_exclusions", [])
        }
        if len(accepted) != len(annual_mapping["accepted"]):
            raise ValueError("annual-report accepted tickers must be unique")
        fundamental_rows = []
        eligibility_by_ticker = {row["ticker"]: row for row in eligibility_rows}
        provenance_by_ticker = {row["ticker"]: row for row in provenance_rows}
        for ticker in sorted(identity.index):
            source = annual_provenance.get(ticker, {})
            audit = annual_audit.get(ticker, {})
            status = eligibility_by_ticker[ticker]
            disclosure = accepted.get(ticker)
            annual_fields: dict[str, Any] = {
                "annual_report_selection_status": source.get("selection_status"),
                "annual_report_audit_status": audit.get("audit_status"),
                "annual_report_source_url": source.get("source_url"),
                "annual_report_pdf_filename": source.get("pdf_filename"),
                "annual_report_pdf_sha256": source.get("pdf_sha256"),
                "annual_report_text_sha256": audit.get("text_sha256"),
            }
            if disclosure is not None:
                if disclosure.get("reporting_basis") != "STANDALONE":
                    raise ValueError(f"non-standalone annual-report mapping: {ticker}")
                if disclosure.get("pdf_sha256") and source.get("pdf_sha256") != disclosure["pdf_sha256"]:
                    raise ValueError(f"annual-report PDF hash mismatch: {ticker}")
                if disclosure.get("text_sha256") and audit.get("text_sha256") != disclosure["text_sha256"]:
                    raise ValueError(f"annual-report text hash mismatch: {ticker}")
                selected = source["selected_metadata"]
                dissemination = _nse_timestamp(selected["disseminationDateTime"])
                if dissemination > datetime.fromisoformat(FILING_CUTOFF):
                    raise ValueError(f"post-cutoff annual report selected: {ticker}")
                profit = disclosure["profit"]
                growth = float(profit["current_value"] / profit["prior_value"] - 1)
                if "canonical_profit_growth_yoy" in profit and not np.isclose(
                    growth, profit["canonical_profit_growth_yoy"], rtol=0, atol=1e-15
                ):
                    raise ValueError(f"annual-report profit growth mismatch: {ticker}")
                fundamental_rows.append({
                    "ticker": ticker, "period_end": "2026-03-31",
                    "available_date": dissemination.date().isoformat(),
                    "roce": disclosure["roce"]["canonical_decimal"],
                    "debt_to_equity": disclosure["debt_to_equity"]["canonical_decimal"],
                    "profit_growth_yoy": growth,
                })
                status.update({
                    "eligible": True, "reason_code": "ELIGIBLE",
                    "reason": "All three canonical fundamentals were directly disclosed on the reviewed audited standalone annual-report basis.",
                })
                annual_fields.update({
                    "annual_report_financial_year": disclosure["financial_year"],
                    "annual_report_submission_type": selected["submission_type"],
                    "annual_report_broadcast_timestamp": selected["broadcast_dttm"],
                    "annual_report_exchange_dissemination_timestamp": selected["disseminationDateTime"],
                    "annual_report_reporting_basis": disclosure["reporting_basis"],
                    "fundamental_data_contract_version": FUNDAMENTAL_DATA_CONTRACT_VERSION,
                    "annual_report_roce": json.dumps(disclosure["roce"], sort_keys=True, separators=(",", ":")),
                    "annual_report_debt_to_equity": json.dumps(disclosure["debt_to_equity"], sort_keys=True, separators=(",", ":")),
                    "annual_report_profit": json.dumps(disclosure["profit"], sort_keys=True, separators=(",", ":")),
                })
            elif ticker in reviewed_exclusions:
                status.update({
                    "eligible": False,
                    "reason_code": reviewed_exclusions[ticker]["classification"],
                    "reason": reviewed_exclusions[ticker]["reason"],
                })
            elif source.get("selection_status") != "SELECTED":
                status.update({
                    "eligible": False, "reason_code": "NO_ELIGIBLE_ANNUAL_REPORT",
                    "reason": "No official NSE-hosted FY2025-26 annual report was disseminated by the cutoff.",
                })
            elif audit.get("audit_status") != "EXTRACTED":
                status.update({
                    "eligible": False, "reason_code": "ANNUAL_REPORT_EXTRACTION_FAILED",
                    "reason": "The official annual-report PDF could not be conservatively extracted with the approved parser.",
                })
            elif not int(audit.get("roce_candidate_page_count", 0)):
                status.update({
                    "eligible": False, "reason_code": "MISSING_EXPLICIT_ROCE",
                    "reason": "No explicit Return on Capital Employed/ROCE disclosure was found; substitutes are not accepted.",
                })
            else:
                status.update({
                    "eligible": False,
                    "reason_code": "AMBIGUOUS_ANNUAL_REPORT_DISCLOSURE",
                    "reason": "Candidate annual-report disclosures were found but reporting basis, table identity, or comparable values were not sufficiently reviewed for canonical use.",
                })
            provenance_by_ticker[ticker].update(annual_fields)
            direct = disclosure is not None
            annual_coverage_rows.append({
                "ticker": ticker, "company": identity.loc[ticker, "company"],
                "sector": identity.loc[ticker, "sector"],
                "taxonomy_family": provenance_by_ticker[ticker].get("taxonomy_family"),
                "report_status": source.get("selection_status"),
                "audit_status": audit.get("audit_status"),
                "roce_classification": (
                    "DIRECT_DISCLOSURE" if direct else
                    reviewed_exclusions.get(ticker, {}).get("classification") or
                    ("AMBIGUOUS" if int(audit.get("roce_candidate_page_count", 0)) else "MISSING")
                ),
                "debt_to_equity_classification": (
                    "DIRECT_DISCLOSURE" if direct else
                    reviewed_exclusions.get(ticker, {}).get("classification") or
                    ("AMBIGUOUS" if int(audit.get("debt_equity_candidate_page_count", 0)) else "MISSING")
                ),
                "profit_classification": (
                    "DIRECT_DISCLOSURE" if direct else
                    reviewed_exclusions.get(ticker, {}).get("classification") or
                    ("AMBIGUOUS" if int(audit.get("profit_candidate_page_count", 0)) else "MISSING")
                ),
                "all_three_direct": direct,
                "eligibility_reason_code": status["reason_code"],
            })
        provenance_rows = [provenance_by_ticker[ticker] for ticker in sorted(provenance_by_ticker)]
        eligibility_rows = [eligibility_by_ticker[ticker] for ticker in sorted(eligibility_by_ticker)]
        annual_report_summary = json.loads(
            (annual_root / "acquisition_summary.json").read_text(encoding="utf-8")
        ) | json.loads((audit_root / "audit_summary.json").read_text(encoding="utf-8"))
    fundamentals = pd.DataFrame(fundamental_rows, columns=list(FUNDAMENTAL_COLUMNS))
    eligibility = pd.DataFrame(eligibility_rows).sort_values(["sector", "ticker"], kind="stable")
    if fundamentals.empty:
        result = ResearchV2Result(pd.DataFrame(columns=list(V2_OUTPUT_COLUMNS)), eligibility)
    else:
        result = calculate_research_v2(
            ResearchV2Inputs(universe, prices, fundamentals),
            ResearchV2Config(ranking_date=datetime.strptime(RANKING_DATE, "%Y-%m-%d").date()),
        )
        adapter_status = eligibility.set_index("ticker")
        engine_status = result.eligibility.set_index("ticker")
        for ticker in adapter_status.index:
            if not bool(adapter_status.loc[ticker, "eligible"]):
                engine_status.loc[ticker, ["eligible", "reason_code", "reason"]] = adapter_status.loc[ticker, ["eligible", "reason_code", "reason"]]
        result = ResearchV2Result(result.rankings, engine_status.reset_index())
    baseline_rankings, _ = calculate_prepared_real_rankings(baseline)
    comparison, comparison_sector_summary = build_matched_cohort_comparison(
        universe, baseline.baseline_input, baseline_rankings,
        result.rankings, eligibility,
    )
    files = {
        "universe.csv": universe, "prices.csv": prices,
        "fundamentals.csv": fundamentals, "eligibility.csv": eligibility,
        "rankings.csv": result.rankings, "comparison.csv": comparison,
        "comparison_sector_summary.csv": comparison_sector_summary,
        "filing_provenance.csv": pd.DataFrame(provenance_rows),
        "annual_report_coverage.csv": pd.DataFrame(annual_coverage_rows),
    }
    for name, frame in files.items():
        frame.to_csv(output / name, index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")
    shutil.copyfile(mapping_path, output / "xbrl_mapping.json")
    if annual_report_enabled:
        shutil.copyfile(annual_report_mapping_path, output / "annual_report_mapping.json")
    metadata = {
        "bundle_version": BUNDLE_VERSION, "ranking_date": RANKING_DATE,
        "filing_cutoff": FILING_CUTOFF, "requested_count": len(universe),
        "filings_discovered": json.loads((raw / "acquisition_summary.json").read_text())["metadata_records_discovered"],
        "selected_xbrl_count": sum(row["selection_status"] == "SELECTED" for row in provenance_rows),
        "rejected_filing_count": sum(row["selection_status"] != "SELECTED" for row in provenance_rows),
        "successfully_mapped_count": len(fundamentals),
        "eligible_count": int(eligibility["eligible"].sum()),
        "excluded_count": int((~eligibility["eligible"]).sum()),
        "reason_counts": {str(k): int(v) for k, v in eligibility.loc[~eligibility["eligible"], "reason_code"].value_counts().sort_index().items()},
        "taxonomy_families": sorted({row["taxonomy_family"] for row in provenance_rows if row["taxonomy_family"]}),
        "eligible_sector_count": int(eligibility.loc[eligibility["eligible"], "sector"].nunique()),
        "baseline_bundle_fingerprint": baseline.fingerprint,
        "fundamental_data_contract_version": FUNDAMENTAL_DATA_CONTRACT_VERSION,
        "fundamental_data_contract_label": "NSE Audited Standalone Fundamentals v1",
        "status": "AUDITED_STANDALONE_CONTRACT",
        "annual_report_summary": annual_report_summary,
        "annual_report_coverage_by_taxonomy": {
            str(key): {"requested": int(len(group)), "eligible": int(group["all_three_direct"].sum())}
            for key, group in pd.DataFrame(annual_coverage_rows).groupby("taxonomy_family", dropna=False, sort=True)
        } if annual_coverage_rows else {},
        "annual_report_coverage_by_sector": {
            str(key): {"requested": int(len(group)), "eligible": int(group["all_three_direct"].sum())}
            for key, group in pd.DataFrame(annual_coverage_rows).groupby("sector", sort=True)
        } if annual_coverage_rows else {},
        "scientific_boundary": "Only reviewed direct FY2025-26 audited standalone annual-report disclosures are canonical; no basis mixing, proxy ratios, or derived accounting ratios are permitted.",
    }
    (output / "bundle_metadata.json").write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    entries = []
    for path in sorted(output.iterdir(), key=lambda item: item.name):
        if path.name == "bundle_manifest.json" or not path.is_file():
            continue
        entries.append({"path": path.name, "sha256": _sha(path), "size": path.stat().st_size})
    fingerprint = sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (output / "bundle_manifest.json").write_text(json.dumps({"schema_version": 1, "bundle_fingerprint": fingerprint, "files": entries}, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    return fingerprint


def load_real_research_v2_bundle(path: str | Path) -> RealResearchV2Bundle:
    root = Path(path).resolve()
    manifest = json.loads((root / "bundle_manifest.json").read_text(encoding="utf-8"))
    entries = manifest["files"]
    for entry in entries:
        target = root / entry["path"]
        if not target.is_file() or _sha(target) != entry["sha256"]:
            raise ValueError(f"real Research V2 bundle hash mismatch: {entry['path']}")
    fingerprint = sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if fingerprint != manifest["bundle_fingerprint"]:
        raise ValueError("real Research V2 bundle fingerprint mismatch")
    return RealResearchV2Bundle(
        root, pd.read_csv(root / "universe.csv"), pd.read_csv(root / "prices.csv"),
        pd.read_csv(root / "fundamentals.csv"), pd.read_csv(root / "eligibility.csv"),
        pd.read_csv(root / "rankings.csv"), pd.read_csv(root / "comparison.csv"),
        pd.read_csv(root / "comparison_sector_summary.csv"),
        pd.read_csv(root / "filing_provenance.csv"),
        json.loads((root / "bundle_metadata.json").read_text(encoding="utf-8")), fingerprint,
    )
