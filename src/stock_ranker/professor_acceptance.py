"""Deterministic acceptance audit for an externally supplied security cohort.

The cohort and verified identity evidence are data inputs.  This module never
contains company-specific aliases or expected ranks and never fuzzy-matches an
identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


VERSION = "professor_supplied_acceptance_v1"
PRICE_METRICS = ("yoy_growth", "cagr_3y", "cagr_5y", "days_since_recorded_high")
V2_FACTORS = (
    "return_1y", "cagr_3y", "cagr_5y", "days_since_recorded_high",
    "annualized_volatility_1y", "max_drawdown_3y", "roce",
    "debt_to_equity", "profit_growth_yoy",
)


@dataclass(frozen=True, slots=True)
class ProfessorAcceptanceResult:
    securities: pd.DataFrame
    ranked_comparison: pd.DataFrame
    audit: dict[str, Any]


def _load_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{source.name} must contain a JSON object")
    return value


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _history(path: Path, as_of: str) -> dict[str, Any]:
    blank = {
        "history_start_date": None, "history_end_date": None,
        "history_observation_count": 0, "anchor_1y_available": False,
        "anchor_3y_available": False, "anchor_5y_available": False,
        "recorded_high_price": None, "recorded_high_date": None,
        "history_yoy_growth": None, "history_cagr_3y": None,
        "history_cagr_5y": None, "history_days_since_recorded_high": None,
    }
    if not path.is_file():
        return blank
    frame = pd.read_csv(path)
    if not {"date", "adjusted_close"}.issubset(frame.columns):
        raise ValueError(f"history schema is invalid: {path}")
    frame["date"] = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="raise")
    frame["adjusted_close"] = pd.to_numeric(frame["adjusted_close"], errors="coerce")
    frame = frame.loc[frame["date"].le(pd.Timestamp(as_of))].dropna(subset=["adjusted_close"])
    frame = frame.loc[frame["adjusted_close"].gt(0)].sort_values("date", kind="stable")
    if frame.empty:
        return blank
    current = float(frame.iloc[-1]["adjusted_close"])
    current_date = frame.iloc[-1]["date"]
    anchors: dict[int, float | None] = {}
    for years in (1, 3, 5):
        target = pd.Timestamp(as_of) - pd.DateOffset(years=years)
        candidates = frame.loc[frame["date"].between(target - pd.Timedelta(days=7), target)]
        anchors[years] = None if candidates.empty else float(candidates.iloc[-1]["adjusted_close"])
    maximum = float(frame["adjusted_close"].max())
    high_date = frame.loc[frame["adjusted_close"].eq(maximum), "date"].iloc[-1]
    return {
        "history_start_date": frame.iloc[0]["date"].date().isoformat(),
        "history_end_date": current_date.date().isoformat(),
        "history_observation_count": int(len(frame)),
        "anchor_1y_available": anchors[1] is not None,
        "anchor_3y_available": anchors[3] is not None,
        "anchor_5y_available": anchors[5] is not None,
        "recorded_high_price": maximum,
        "recorded_high_date": high_date.date().isoformat(),
        "history_yoy_growth": None if anchors[1] is None else current / anchors[1] - 1,
        "history_cagr_3y": None if anchors[3] is None else (current / anchors[3]) ** (1 / 3) - 1,
        "history_cagr_5y": None if anchors[5] is None else (current / anchors[5]) ** (1 / 5) - 1,
        "history_days_since_recorded_high": int((current_date - high_date).days),
    }


def _validate_request(request: dict[str, Any]) -> tuple[list[str], dict[str, int]]:
    universe = request.get("universe")
    ranking = request.get("reference_ranking")
    if not isinstance(universe, list) or not universe or not all(isinstance(x, str) and x.strip() for x in universe):
        raise ValueError("acceptance request universe must be a nonempty string list")
    normalized = [x.strip().upper() for x in universe]
    if len(set(normalized)) != len(normalized):
        raise ValueError("acceptance request universe contains duplicate codes")
    if not isinstance(ranking, list):
        raise ValueError("reference_ranking must be a list")
    ranks: dict[str, int] = {}
    for item in ranking:
        if not isinstance(item, dict) or set(item) != {"rank", "code"}:
            raise ValueError("each reference ranking row requires rank and code")
        code, rank = str(item["code"]).strip().upper(), int(item["rank"])
        if code not in normalized or code in ranks or rank < 1:
            raise ValueError("reference ranking contains an invalid code or rank")
        ranks[code] = rank
    if sorted(ranks.values()) != list(range(1, len(ranks) + 1)):
        raise ValueError("reference ranks must be contiguous from one")
    return normalized, ranks


def _load_bse_snapshot(path: str | Path | None) -> pd.DataFrame:
    """Load an optional official BSE CM-UDiFF snapshot by exact code and ISIN."""

    columns = ["FinInstrmId", "ISIN", "TradDt", "ClsPric"]
    if path is None or not Path(path).is_file():
        return pd.DataFrame(columns=columns).set_index("FinInstrmId", drop=False)
    frame = pd.read_csv(path, dtype={"FinInstrmId": "string"}, low_memory=False)
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"BSE snapshot is missing columns: {', '.join(missing)}")
    frame = frame.loc[:, columns].copy()
    frame["FinInstrmId"] = frame["FinInstrmId"].astype("string").str.strip()
    if frame["FinInstrmId"].duplicated().any():
        duplicates = sorted(frame.loc[frame["FinInstrmId"].duplicated(False), "FinInstrmId"].unique())
        raise ValueError(f"BSE snapshot contains duplicate instrument IDs: {duplicates}")
    frame["TradDt"] = pd.to_datetime(frame["TradDt"], format="%Y-%m-%d", errors="raise")
    frame["ClsPric"] = pd.to_numeric(frame["ClsPric"], errors="coerce")
    return frame.set_index("FinInstrmId", drop=False)


def build_professor_acceptance(
    request_path: str | Path, identity_evidence_path: str | Path, *,
    live_market_path: str | Path, nse_history_root: str | Path,
    supplemental_nse_history_root: str | Path, bse_history_root: str | Path,
    bse_snapshot_path: str | Path | None = None,
) -> ProfessorAcceptanceResult:
    """Resolve and audit every requested code without fuzzy substitution."""

    request, evidence_doc = _load_json(request_path), _load_json(identity_evidence_path)
    universe, reference_ranks = _validate_request(request)
    evidence_rows = evidence_doc.get("identities")
    if not isinstance(evidence_rows, list):
        raise ValueError("identity evidence must contain an identities list")
    evidence = {str(row["requested_code"]).upper(): row for row in evidence_rows}
    if len(evidence) != len(evidence_rows):
        raise ValueError("identity evidence contains duplicate requested codes")
    market = pd.read_csv(live_market_path, low_memory=False)
    if market["ticker"].duplicated().any():
        raise ValueError("live market contains duplicate tickers")
    by_ticker = market.set_index("ticker", drop=False)
    bse_snapshot = _load_bse_snapshot(bse_snapshot_path)
    as_of = str(market["trade_date"].dropna().iloc[0])
    rows: list[dict[str, Any]] = []
    for requested in universe:
        item = evidence.get(requested, {})
        supplied_exchange = requested.split(":", 1)[0] if ":" in requested else None
        supplied_symbol = requested.split(":", 1)[1] if ":" in requested else requested
        canonical_exchange = str(item.get("canonical_exchange") or supplied_exchange or "").upper()
        canonical_symbol = str(item.get("canonical_symbol") or supplied_symbol).upper()
        nse_ticker = item.get("nse_ticker")
        if supplied_exchange == "NSE":
            nse_ticker = supplied_symbol
        elif supplied_exchange is None and canonical_exchange == "NSE":
            nse_ticker = canonical_symbol
        market_row = by_ticker.loc[nse_ticker] if nse_ticker in by_ticker.index else None
        identity_status = "UNRESOLVED_IDENTITY"
        if market_row is not None:
            expected_isin = str(item.get("isin") or market_row["isin"])
            if str(market_row["isin"]) != expected_isin:
                raise ValueError(f"ISIN mismatch for {requested}")
            identity_status = "MATCHED_EXACT_NSE" if supplied_exchange == "NSE" else (
                "MATCHED_VERIFIED_PREFIXLESS_NSE" if supplied_exchange is None
                else "MATCHED_CROSS_LISTED_ISIN"
            )
        elif canonical_exchange == "BSE" and item.get("isin") and item.get("company"):
            identity_status = "VERIFIED_BSE_ONLY"
        row: dict[str, Any] = {
            "requested_code": requested, "reference_rank": reference_ranks.get(requested),
            "supplied_exchange": supplied_exchange, "supplied_symbol": supplied_symbol,
            "canonical_exchange": canonical_exchange or None,
            "canonical_symbol": canonical_symbol or None,
            "canonical_company": item.get("company"), "isin": item.get("isin"),
            "listing_status": item.get("listing_status"), "identity_status": identity_status,
            "mapping_decision": item.get("mapping_decision"),
            "identity_evidence_source": item.get("source_url"),
            "provider_symbol": item.get("provider_symbol"),
        }
        if market_row is not None:
            row.update({
                "canonical_company": market_row["company"], "isin": market_row["isin"],
                "listing_status": "CURRENT_NSE_EQUITY_UNIVERSE",
                "sector": market_row.get("sector"), "industry": market_row.get("industry"),
                "size_classification": market_row.get("size_segment"),
                "classification_status": market_row.get("classification_status"),
                "latest_price": _finite(market_row.get("latest_price")),
                "latest_price_date": market_row.get("trade_date"),
                "price_source": market_row.get("snapshot_source"),
                "baseline_eligibility_reason": market_row.get("baseline_reason_code"),
                "baseline_eligibility_explanation": market_row.get("baseline_reason"),
                "baseline_eligible": bool(market_row.get("baseline_eligible")),
                "baseline_score": _finite(market_row.get("baseline_score")),
                "baseline_sector_rank": _finite(market_row.get("baseline_sector_rank")),
                "research_v2_eligible": bool(market_row.get("v2_eligible")),
                "research_v2_reason": market_row.get("v2_reason_code"),
                "research_v2_explanation": market_row.get("v2_reason"),
                "research_v2_score": _finite(market_row.get("research_v2_score")),
                "research_v2_sector_rank": _finite(market_row.get("research_v2_sector_rank")),
            })
            for metric in PRICE_METRICS:
                column = "baseline_yoy_growth" if metric == "yoy_growth" else f"baseline_{metric}"
                row[f"baseline_{metric}"] = _finite(market_row.get(column))
            for factor in V2_FACTORS:
                row[f"v2_{factor}"] = _finite(market_row.get(factor))
                row[f"v2_{factor}_contribution"] = _finite(market_row.get(f"{factor}_contribution"))
            standard = Path(nse_history_root) / f"{nse_ticker}.csv"
            supplemental = Path(supplemental_nse_history_root) / f"{nse_ticker}.csv"
            exact_bse = Path(bse_history_root) / f"{supplied_symbol}.csv"
            history_path = standard if standard.is_file() else supplemental
            history_source = "prepared exact NSE adjusted-price history"
            if not history_path.is_file() and supplied_exchange in {"BOM", "BSE"} and exact_bse.is_file():
                history_path = exact_bse
                history_source = "exact same-ISIN BSE adjusted-price history"
            row["history_source"] = history_source if history_path.is_file() else None
            row.update(_history(history_path, as_of))
        else:
            bse_path = Path(bse_history_root) / f"{supplied_symbol}.csv"
            history = _history(bse_path, as_of)
            row.update(history)
            row["history_source"] = "exact verified BSE adjusted-price history" if bse_path.is_file() else None
            last = None
            latest_date = history["history_end_date"]
            price_source = None
            if bse_path.is_file():
                raw = pd.read_csv(bse_path)
                eligible = raw.loc[raw["date"].astype(str).le(as_of)]
                if not eligible.empty:
                    last = _finite(eligible.iloc[-1].get("close", eligible.iloc[-1].get("adjusted_close")))
                    price_source = "Yahoo Finance through yfinance; exact verified .BO symbol"
            if last is None and supplied_symbol in bse_snapshot.index:
                snapshot_row = bse_snapshot.loc[supplied_symbol]
                if str(snapshot_row["ISIN"]).strip() != str(item.get("isin") or "").strip():
                    raise ValueError(f"BSE snapshot ISIN mismatch for {requested}")
                snapshot_date = snapshot_row["TradDt"]
                if snapshot_date <= pd.Timestamp(as_of):
                    last = _finite(snapshot_row["ClsPric"])
                    latest_date = snapshot_date.date().isoformat()
                    price_source = "Official BSE CM-UDiFF BhavCopy Final; exact code and ISIN"
            row.update({
                "sector": None, "industry": item.get("industry"), "size_classification": None,
                "classification_status": "BSE_OUTSIDE_ACCEPTED_NSE_SECTOR_TAXONOMY",
                "latest_price": last, "latest_price_date": latest_date,
                "price_source": price_source,
                "baseline_eligible": False, "baseline_eligibility_reason": "UNCLASSIFIED_BSE",
                "baseline_eligibility_explanation": "No accepted NSE Indices sector classification exists for this BSE-only security.",
                "baseline_yoy_growth": history["history_yoy_growth"],
                "baseline_cagr_3y": history["history_cagr_3y"],
                "baseline_cagr_5y": history["history_cagr_5y"],
                "baseline_days_since_recorded_high": history["history_days_since_recorded_high"],
                "baseline_score": None, "baseline_sector_rank": None,
                "research_v2_eligible": False,
                "research_v2_reason": "BSE_FUNDAMENTAL_CONTRACT_UNAVAILABLE",
                "research_v2_explanation": "The accepted real Research V2 contract is NSE audited standalone fundamentals only.",
                "research_v2_score": None, "research_v2_sector_rank": None,
            })
            for factor in V2_FACTORS:
                row[f"v2_{factor}"] = None
                row[f"v2_{factor}_contribution"] = None
        if identity_status == "UNRESOLVED_IDENTITY":
            row["resolution_status"] = "DEFECT REMAINS"
            row["resolution_reason"] = "No exact verified security identity is available."
        elif row.get("latest_price") is None:
            row["resolution_status"] = "LEGITIMATELY UNAVAILABLE"
            row["resolution_reason"] = "Identity is verified, but the accepted providers contain no current series."
        else:
            row["resolution_status"] = "RESOLVED"
            row["resolution_reason"] = "Exact identity and current price are available; model-specific eligibility is reported separately."
        rows.append(row)
    securities = pd.DataFrame(rows)
    ranked = securities.loc[securities["reference_rank"].notna()].sort_values("reference_rank", kind="stable").copy()
    if ranked.empty:
        ranked["baseline_position_status"] = pd.Series(dtype="object")
        ranked["research_v2_position_status"] = pd.Series(dtype="object")
    else:
        ranked["baseline_position_status"] = ranked.apply(
            lambda x: f"SECTOR_RANK_{int(x['baseline_sector_rank'])}" if x["baseline_eligible"] else str(x["baseline_eligibility_reason"]), axis=1
        )
        ranked["research_v2_position_status"] = ranked.apply(
            lambda x: f"SECTOR_RANK_{int(x['research_v2_sector_rank'])}" if x["research_v2_eligible"] else str(x["research_v2_reason"]), axis=1
        )
    comparable_pairs = 0
    agreeing_pairs = 0
    ranked_records = ranked.to_dict("records")
    for index, left in enumerate(ranked_records):
        for right in ranked_records[index + 1:]:
            if left.get("sector") and left.get("sector") == right.get("sector") and left.get("baseline_eligible") and right.get("baseline_eligible"):
                comparable_pairs += 1
                agreeing_pairs += int(float(left["baseline_sector_rank"]) <= float(right["baseline_sector_rank"]))
    counts = securities["resolution_status"].value_counts().to_dict()
    audit = {
        "schema_version": 1, "benchmark_version": VERSION,
        "request_fingerprint": sha256(json.dumps(request, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "requested_security_count": len(securities), "reference_ranking_count": len(ranked),
        "resolution_counts": {key: int(value) for key, value in sorted(counts.items())},
        "identity_coverage": float(securities["identity_status"].ne("UNRESOLVED_IDENTITY").mean()),
        "current_price_coverage": float(securities["latest_price"].notna().mean()),
        "baseline_eligible_count": int(securities["baseline_eligible"].sum()),
        "research_v2_eligible_count": int(securities["research_v2_eligible"].sum()),
        "reference_ranking_verdict": "NOT REPRODUCIBLE FROM AVAILABLE METHODOLOGY",
        "reference_ranking_reason": (
            "The supplied ordering has no score, sector scope, tie convention, or formula. Baseline ranks are sector-relative, "
            "so a global Spearman correlation or top-k overlap would be scientifically invalid."
        ),
        "global_rank_correlation": None, "global_top_k_overlap": None,
        "within_sector_comparable_pair_count": comparable_pairs,
        "within_sector_pairwise_agreement": None if comparable_pairs == 0 else agreeing_pairs / comparable_pairs,
        "research_v2_verdict": "INSUFFICIENT EVIDENCE" if not securities["research_v2_eligible"].any() else "NO CLEAR IMPROVEMENT",
        "scientific_boundary": "Reference ranks are evaluation evidence only; no formulas, weights, eligibility rules, sectors, or outcomes were tuned.",
    }
    return ProfessorAcceptanceResult(securities, ranked, audit)


def export_professor_acceptance(result: ProfessorAcceptanceResult, output_dir: str | Path) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for name, frame in (("security_acceptance.csv", result.securities), ("reference_ranking_comparison.csv", result.ranked_comparison)):
        path = root / name
        frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")
        files.append({"path": name, "sha256": sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size})
    audit_path = root / "acceptance_summary.json"
    audit_path.write_text(json.dumps(result.audit, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    files.append({"path": audit_path.name, "sha256": sha256(audit_path.read_bytes()).hexdigest(), "size": audit_path.stat().st_size})
    manifest = {"schema_version": 1, "benchmark_version": VERSION, "files": files}
    manifest["acceptance_fingerprint"] = sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return path
