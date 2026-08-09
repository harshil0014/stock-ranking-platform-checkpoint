"""Outcome-blind historical prediction reconstruction for the frozen protocol."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import numpy as np
import pandas as pd

from stock_ranker.baseline import calculate_baseline_rankings
from stock_ranker.config import BaselineConfig
from stock_ranker.historical_baseline import prepare_historical_baseline
from stock_ranker.real_research_v2 import build_matched_cohort_comparison
from stock_ranker.research_v2 import (
    ResearchV2Inputs,
    ResearchV2Result,
    _price_metrics,
    calculate_research_v2,
)
from stock_ranker.v2_config import ResearchV2Config
from stock_ranker.v2_contracts import FUNDAMENTAL_COLUMNS, V2_OUTPUT_COLUMNS


PROTOCOL_IDENTIFIER = "walk_forward_validation_protocol_v1"
PROTOCOL_SHA256 = "a81278b799e1a61c3684f3b319fb14e2f6f0db6a2bdad1cd79b2ce13fd6f8576"
BLIND_BUNDLE_VERSION = "blind_historical_predictions_v1"
REQUIRED_FISCAL_YEARS = {
    "2022-08-05": ("2021-22", "2022-03-31"),
    "2023-08-07": ("2022-23", "2023-03-31"),
    "2024-08-07": ("2023-24", "2024-03-31"),
    "2025-08-07": ("2024-25", "2025-03-31"),
}
MCWB_MEMBER = "nifty50_mcwb.csv"
PIT_REBASE_ABSOLUTE_TOLERANCE = 1e-10
PROHIBITED_OUTCOME_FIELDS = {
    "future_return", "forward_return", "label", "label_end_date",
    "rank_ic", "ic", "pairwise_accuracy", "realized_return",
    "spread_return", "winner", "model_win", "endpoint_price_3m",
    "endpoint_price_6m", "endpoint_price_12m",
}


@dataclass(frozen=True, slots=True)
class BlindSnapshot:
    ranking_date: str
    universe: pd.DataFrame
    identity: pd.DataFrame
    prices: pd.DataFrame
    repair_sensitivity: pd.DataFrame
    baseline_full: pd.DataFrame
    fundamentals: pd.DataFrame
    research_v2: pd.DataFrame
    matched_baseline: pd.DataFrame
    exclusions: pd.DataFrame
    provenance: dict[str, Any]


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def protocol_fingerprint(path: str | Path) -> str:
    parsed = json.loads(Path(path).read_text(encoding="utf-8"))
    return sha256(canonical_json_bytes(parsed)).hexdigest()


def parse_mcwb_archive(
    path: str | Path,
    *,
    expected_zip_sha256: str,
    expected_csv_sha256: str,
) -> pd.DataFrame:
    """Parse one hash-verified official historical NIFTY 50 snapshot."""

    source = Path(path)
    content = source.read_bytes()
    if sha256(content).hexdigest() != expected_zip_sha256:
        raise ValueError(f"official MCWB ZIP hash mismatch: {source.name}")
    with ZipFile(source) as archive:
        if archive.namelist().count(MCWB_MEMBER) != 1:
            raise ValueError(f"official MCWB archive must contain exactly one {MCWB_MEMBER}")
        csv_bytes = archive.read(MCWB_MEMBER)
    if sha256(csv_bytes).hexdigest() != expected_csv_sha256:
        raise ValueError(f"official MCWB NIFTY 50 CSV hash mismatch: {source.name}")
    text = csv_bytes.decode("utf-8-sig")
    frame = pd.read_csv(StringIO(text), skiprows=2)
    required = {"Sr. No", "Security Symbol", "Security Name", "Industry"}
    if required.difference(frame.columns):
        raise ValueError(f"official MCWB schema mismatch: {source.name}")
    serial = pd.to_numeric(frame["Sr. No"], errors="coerce")
    frame = frame.loc[serial.notna()].copy()
    frame["source_row_number"] = serial.loc[serial.notna()].astype(int)
    frame["historical_symbol"] = frame["Security Symbol"].astype(str).str.strip()
    frame["company"] = frame["Security Name"].astype(str).str.strip()
    frame["historical_industry"] = frame["Industry"].astype(str).str.strip()
    if frame["historical_symbol"].eq("").any() or frame["historical_symbol"].duplicated().any():
        raise ValueError("official MCWB symbols must be nonblank and unique")
    frame["source_status"] = np.where(
        frame["historical_symbol"].eq("DUMMYREL"),
        "SYNTHETIC_CORPORATE_ACTION_PLACEHOLDER", "INVESTABLE",
    )
    frame["investable"] = ~frame["historical_symbol"].eq("DUMMYREL")
    return frame.loc[:, [
        "source_row_number", "historical_symbol", "company",
        "historical_industry", "source_status", "investable",
    ]].sort_values("source_row_number", kind="stable").reset_index(drop=True)


def apply_historical_sector_mapping(
    universe: pd.DataFrame,
    mapping: dict[str, Any],
    ranking_date: str,
) -> pd.DataFrame:
    """Map verbatim MCWB Industry labels to the historical official Sector tier."""

    documents = [
        item for item in mapping["classification_documents"]
        if ranking_date in item["applicable_ranking_dates"]
    ]
    if len(documents) != 1:
        raise ValueError(f"expected one applicable NSE classification document: {ranking_date}")
    document = documents[0]
    rows = mapping["mappings"]
    labels = [str(item["historical_industry"]) for item in rows]
    if len(labels) != len(set(labels)):
        raise ValueError("duplicate historical Industry in NSE Sector mapping")
    lookup = {str(item["historical_industry"]): item for item in rows}
    result = universe.copy(deep=True)
    unresolved = sorted(set(result["historical_industry"]) - set(lookup))
    if unresolved:
        raise ValueError("unresolved historical Industry mapping: " + ", ".join(unresolved))
    result["historical_sector"] = result["historical_industry"].map(
        lambda value: lookup[str(value)]["historical_sector"]
    )
    result["official_sector_code"] = result["historical_industry"].map(
        lambda value: lookup[str(value)]["official_sector_code"]
    )
    result["classification_document_id"] = document["document_id"]
    if result["historical_sector"].isna().any() or result["historical_sector"].eq("").any():
        raise ValueError("historical NSE Sector mapping produced a blank value")
    return result


def provider_identity(
    universe: pd.DataFrame,
    aliases: dict[str, str] | None = None,
) -> pd.DataFrame:
    aliases = aliases or {}
    rows = []
    for row in universe.to_dict("records"):
        symbol = str(row["historical_symbol"])
        if symbol == "DUMMYREL":
            rows.append({
                "historical_symbol": symbol,
                "company": row["company"],
                "historical_industry": row["historical_industry"],
                "historical_sector": row["historical_sector"],
                "official_sector_code": row["official_sector_code"],
                "classification_document_id": row["classification_document_id"],
                "provider_symbol": None,
                "identity_resolution_status": "NON_INVESTABLE_PLACEHOLDER",
                "identity_evidence": "Frozen July 2023 DUMMYREL protocol rule",
            })
            continue
        provider = aliases.get(symbol, f"{symbol}.NS")
        if symbol == "HDFC" and provider == "HDFCBANK.NS":
            raise ValueError("HDFC must not be substituted with HDFCBANK")
        if symbol == "DUMMYREL" and provider == "JIOFIN.NS":
            raise ValueError("DUMMYREL must not be substituted with JIOFIN")
        rows.append({
            "historical_symbol": symbol,
            "company": row["company"],
            "historical_industry": row["historical_industry"],
            "historical_sector": row["historical_sector"],
            "official_sector_code": row["official_sector_code"],
            "classification_document_id": row["classification_document_id"],
            "provider_symbol": provider,
            "identity_resolution_status": "DECLARATIVE_ALIAS" if symbol in aliases else "EXACT_NS_RULE",
            "identity_evidence": (
                "Exact declarative provider alias" if symbol in aliases
                else "Exact official historical NSE symbol plus .NS"
            ),
        })
    return pd.DataFrame(rows)


def provider_request_window(ranking_date: str) -> dict[str, str]:
    cutoff = date.fromisoformat(ranking_date)
    return {
        "start_inclusive": "1900-01-01",
        "end_exclusive": (cutoff + timedelta(days=1)).isoformat(),
        "maximum_allowed_observation": cutoff.isoformat(),
    }


def cutoff_rebased_prices(frame: pd.DataFrame, ranking_date: str) -> pd.DataFrame:
    """Validate one provider panel and apply the frozen cutoff rebase."""

    required = {
        "ticker", "provider_symbol", "date", "close", "adj_close",
        "dividends", "stock_splits", "repaired",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError("predictor prices missing columns: " + ", ".join(sorted(missing)))
    result = frame.loc[:, sorted(required)].copy()
    result["date"] = pd.to_datetime(result["date"], format="%Y-%m-%d", errors="raise")
    cutoff = pd.Timestamp(ranking_date)
    if (result["date"] > cutoff).any():
        raise ValueError("BLINDNESS_VIOLATION: predictor price exists after ranking cutoff")
    for column in ("close", "adj_close"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
        if (~np.isfinite(result[column]) | (result[column] <= 0)).any():
            raise ValueError(f"predictor {column} must be finite and positive")
    output = []
    for ticker, group in result.groupby("ticker", sort=True):
        ordered = group.sort_values("date", kind="stable").copy()
        terminal = ordered.iloc[-1]
        if terminal["date"] != cutoff:
            raise ValueError(f"no provider observation on ranking date: {ticker}")
        factor = float(terminal["adj_close"] / terminal["close"])
        if not np.isfinite(factor) or factor <= 0:
            raise ValueError(f"invalid cutoff adjustment factor: {ticker}")
        ordered["cutoff_adjustment_factor"] = factor
        ordered["pit_adjusted_price"] = ordered["adj_close"] / factor
        if not np.isclose(
            float(ordered.iloc[-1]["pit_adjusted_price"]),
            float(terminal["close"]), rtol=0, atol=PIT_REBASE_ABSOLUTE_TOLERANCE,
        ):
            raise ValueError(f"PIT rebase identity failed at cutoff: {ticker}")
        output.append(ordered)
    combined = pd.concat(output, ignore_index=True) if output else result.assign(
        cutoff_adjustment_factor=pd.Series(dtype=float),
        pit_adjusted_price=pd.Series(dtype=float),
    )
    combined["date"] = combined["date"].dt.strftime("%Y-%m-%d")
    return combined.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)


def assert_outcome_blind(frame: pd.DataFrame, ranking_date: str | None = None) -> None:
    lowered = {str(column).strip().lower() for column in frame.columns}
    forbidden = sorted(lowered & PROHIBITED_OUTCOME_FIELDS)
    if forbidden:
        raise ValueError("OUTCOME_FIELD_FORBIDDEN: " + ", ".join(forbidden))
    if ranking_date is not None and "date" in frame.columns:
        dates = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="raise")
        if (dates > pd.Timestamp(ranking_date)).any():
            raise ValueError("BLINDNESS_VIOLATION: artifact contains a post-cutoff price")


def validate_blind_snapshot_directory(path: str | Path, ranking_date: str) -> None:
    """Re-open a written snapshot and enforce its outcome-blind boundary."""

    root = Path(path)
    required = {
        "historical_universe.csv", "identity_resolution.csv",
        "predictor_prices.csv", "repair_sensitivity.csv", "baseline_full.csv",
        "fundamentals.csv", "research_v2.csv", "matched_baseline.csv",
        "exclusions.csv", "provenance.json", "manifest.json",
    }
    present = {item.name for item in root.iterdir() if item.is_file()}
    if present != required:
        raise ValueError("blind snapshot artifact set mismatch")
    for csv_path in sorted(root.glob("*.csv")):
        frame = pd.read_csv(csv_path)
        assert_outcome_blind(
            frame,
            ranking_date if csv_path.name == "predictor_prices.csv" else None,
        )
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    if provenance.get("future_outcome_data_present") is not False:
        raise ValueError("blind snapshot lacks negative outcome-data attestation")


def _baseline_from_prices(
    universe: pd.DataFrame,
    prices: pd.DataFrame,
    ranking_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    investable = universe.loc[universe["investable"]].copy()
    accepted_universe = investable.rename(columns={
        "historical_symbol": "Symbol", "company": "Company Name",
        "historical_sector": "Industry",
    })
    histories: dict[str, pd.DataFrame | None] = {}
    snapshot_rows = []
    for ticker in accepted_universe["Symbol"]:
        group = prices.loc[prices["ticker"].eq(ticker)]
        if group.empty:
            histories[str(ticker)] = None
            continue
        histories[str(ticker)] = group.loc[:, ["date", "close", "pit_adjusted_price"]].rename(
            columns={"close": "raw_close", "pit_adjusted_price": "adjusted_close"}
        )
        snapshot_rows.append({
            "ticker": ticker,
            "close": float(group.sort_values("date", kind="stable").iloc[-1]["pit_adjusted_price"]),
        })
    prepared = prepare_historical_baseline(
        accepted_universe, pd.DataFrame(snapshot_rows), histories,
        as_of_date=ranking_date,
    )
    rankings = (
        calculate_baseline_rankings(prepared.baseline_input, BaselineConfig())
        if not prepared.baseline_input.empty
        else pd.DataFrame()
    )
    return rankings, prepared.baseline_input, prepared.eligibility


def _price_metric_rows(prices: pd.DataFrame, universe: pd.DataFrame, ranking_date: str) -> pd.DataFrame:
    config = ResearchV2Config(ranking_date=date.fromisoformat(ranking_date))
    rows = []
    identity = universe.set_index("historical_symbol")
    for ticker in universe.loc[universe["investable"], "historical_symbol"]:
        group = prices.loc[prices["ticker"].eq(ticker), ["date", "pit_adjusted_price"]].rename(
            columns={"pit_adjusted_price": "adjusted_close"}
        )
        group["date"] = pd.to_datetime(group["date"], format="%Y-%m-%d")
        metrics, issues = _price_metrics(group, pd.Timestamp(ranking_date), config)
        rows.append({
            "ticker": ticker,
            "company": identity.loc[ticker, "company"],
            "sector": identity.loc[ticker, "historical_sector"],
            **metrics,
            "price_eligible": not issues,
            "price_reason_codes": "|".join(code for code, _ in issues),
        })
    return pd.DataFrame(rows)


def repair_sensitivity(
    repaired: pd.DataFrame,
    unrepaired: pd.DataFrame,
    universe: pd.DataFrame,
    ranking_date: str,
) -> pd.DataFrame:
    left = _price_metric_rows(repaired, universe, ranking_date)
    right = _price_metric_rows(unrepaired, universe, ranking_date)
    merged = left.merge(right, on=["ticker", "company", "sector"], suffixes=("_repair_true", "_repair_false"))
    metric_columns = [
        "return_1y", "cagr_3y", "cagr_5y", "days_since_recorded_high",
        "annualized_volatility_1y", "max_drawdown_3y",
    ]
    difference_columns = []
    for metric in metric_columns:
        column = f"{metric}_difference"
        merged[column] = merged[f"{metric}_repair_true"] - merged[f"{metric}_repair_false"]
        difference_columns.append(column)
    finite_differences = merged[difference_columns].fillna(0).abs()
    eligibility_changed = ~merged["price_eligible_repair_true"].eq(
        merged["price_eligible_repair_false"]
    )
    merged["repair_status"] = np.where(
        finite_differences.gt(1e-12).any(axis=1) | eligibility_changed,
        "REPAIR_AFFECTED", "REPAIR_INSENSITIVE",
    )
    true_rankings, _, _ = _baseline_from_prices(universe, repaired, ranking_date)
    false_rankings, _, _ = _baseline_from_prices(universe, unrepaired, ranking_date)
    if true_rankings.empty and false_rankings.empty:
        merged["material_baseline_rank_impact"] = False
    else:
        true_ranks = true_rankings.reindex(columns=["ticker", "sector_rank"])
        false_ranks = false_rankings.reindex(columns=["ticker", "sector_rank"])
        rank_compare = true_ranks.merge(
            false_ranks, on="ticker", how="outer",
            suffixes=("_repair_true", "_repair_false")
        )
        rank_compare["material_baseline_rank_impact"] = (
            rank_compare["sector_rank_repair_true"].isna()
            | rank_compare["sector_rank_repair_false"].isna()
            | ~rank_compare["sector_rank_repair_true"].eq(
                rank_compare["sector_rank_repair_false"]
            )
        )
        merged = merged.merge(rank_compare, on="ticker", how="left")
        merged["material_baseline_rank_impact"] = merged[
            "material_baseline_rank_impact"
        ].fillna(False)
    return merged.sort_values("ticker", kind="stable").reset_index(drop=True)


def _fundamentals_from_mapping(
    mapping: dict[str, Any], ranking_date: str,
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    snapshot = next(
        item for item in mapping["snapshots"] if item["ranking_date"] == ranking_date
    )
    required_fiscal_year, required_period_end = REQUIRED_FISCAL_YEARS[ranking_date]
    if snapshot.get("required_fiscal_year") != required_fiscal_year:
        raise ValueError("historical fundamental mapping fiscal year mismatch")
    rows = []
    provenance = {}
    for item in snapshot["accepted"]:
        if item.get("reporting_basis") != "STANDALONE":
            raise ValueError("historical fundamental mapping must be standalone")
        if item.get("financial_year") != required_fiscal_year:
            raise ValueError("historical fundamental mapping cannot fall back to another FY")
        if item.get("period_end") != required_period_end:
            raise ValueError("historical fundamental mapping period end mismatch")
        available_date = date.fromisoformat(str(item["available_date"]))
        if available_date > date.fromisoformat(ranking_date):
            raise ValueError("historical fundamental mapping is post-cutoff")
        if item["roce"].get("classification") != "DIRECT_DISCLOSURE":
            raise ValueError("historical ROCE must be a reviewed direct disclosure")
        roce_label = str(item["roce"].get("label", "")).lower()
        if "return on capital employed" not in roce_label and "roce" not in roce_label:
            raise ValueError("historical ROCE cannot use a substitute ratio")
        if item["debt_to_equity"].get("classification") != "DIRECT_DISCLOSURE":
            raise ValueError("historical debt-to-equity must be a reviewed direct disclosure")
        debt_label = str(item["debt_to_equity"].get("label", "")).lower().replace("-", " ")
        if "debt equity" not in debt_label and "debt to equity" not in debt_label:
            raise ValueError("historical debt-to-equity label is not explicit")
        if item["profit"].get("classification") != "DIRECT_DISCLOSURE":
            raise ValueError("historical profit must be a reviewed direct disclosure")
        for section in ("roce", "debt_to_equity", "profit"):
            if not item[section].get("page") or not item[section].get("table"):
                raise ValueError(f"historical {section} provenance is incomplete")
        if not item.get("pdf_sha256"):
            raise ValueError("historical fundamental mapping lacks PDF provenance")
        current = float(item["profit"]["current_value"])
        prior = float(item["profit"]["prior_value"])
        if not np.isfinite(current) or not np.isfinite(prior) or prior == 0:
            raise ValueError("historical profit pair must be finite with nonzero prior profit")
        rows.append({
            "ticker": item["ticker"], "period_end": item["period_end"],
            "available_date": item["available_date"],
            "roce": item["roce"]["canonical_decimal"],
            "debt_to_equity": item["debt_to_equity"]["canonical_decimal"],
            "profit_growth_yoy": current / prior - 1,
        })
        provenance[item["ticker"]] = item
    return pd.DataFrame(rows, columns=list(FUNDAMENTAL_COLUMNS)), provenance


def build_blind_snapshot(
    universe: pd.DataFrame,
    identity: pd.DataFrame,
    repaired_prices: pd.DataFrame,
    unrepaired_prices: pd.DataFrame,
    annual_mapping: dict[str, Any],
    ranking_date: str,
    source_provenance: dict[str, Any],
) -> BlindSnapshot:
    for frame in (repaired_prices, unrepaired_prices):
        assert_outcome_blind(frame, ranking_date)
    baseline, baseline_input, baseline_eligibility = _baseline_from_prices(
        universe, repaired_prices, ranking_date
    )
    taxonomy = universe.loc[:, [
        "historical_symbol", "historical_industry", "historical_sector",
        "official_sector_code", "classification_document_id",
    ]].rename(columns={"historical_symbol": "ticker"})
    if not baseline.empty:
        baseline = baseline.merge(taxonomy, on="ticker", how="left", validate="one_to_one")
    sensitivity = repair_sensitivity(
        repaired_prices, unrepaired_prices, universe, ranking_date
    )
    fundamentals, fundamental_provenance = _fundamentals_from_mapping(
        annual_mapping, ranking_date
    )
    investable = universe.loc[universe["investable"]].rename(columns={
        "historical_symbol": "ticker", "historical_sector": "sector"
    })[["ticker", "company", "sector"]]
    v2_prices = repaired_prices[["ticker", "date", "pit_adjusted_price"]].rename(
        columns={"pit_adjusted_price": "adjusted_close"}
    )
    if fundamentals.empty:
        price_audit = _price_metric_rows(repaired_prices, universe, ranking_date).set_index("ticker")
        identity_audit = identity.set_index("historical_symbol")
        eligibility_rows = []
        for row in investable.to_dict("records"):
            ticker = str(row["ticker"])
            identity_status = str(identity_audit.loc[ticker, "identity_resolution_status"])
            if identity_status != "RESOLVED":
                reason_code = "PROVIDER_SYMBOL_UNAVAILABLE"
                reason = str(identity_audit.loc[ticker, "identity_evidence"])
            elif not bool(price_audit.loc[ticker, "price_eligible"]):
                codes = str(price_audit.loc[ticker, "price_reason_codes"])
                reason_code = codes.split("|")[0]
                reason = "Existing Research V2 price eligibility failed: " + codes
            else:
                reason_code = "MISSING_REVIEWED_STANDALONE_FUNDAMENTALS"
                reason = (
                    "No manually reviewed annual-report mapping satisfies the frozen "
                    "standalone contract."
                )
            eligibility_rows.append({
                **row, "ranking_date": ranking_date, "eligible": False,
                "reason_code": reason_code, "reason": reason,
            })
        v2_result = ResearchV2Result(
            pd.DataFrame(columns=list(V2_OUTPUT_COLUMNS)),
            pd.DataFrame(eligibility_rows),
        )
    else:
        v2_result = calculate_research_v2(
            ResearchV2Inputs(investable, v2_prices, fundamentals),
            ResearchV2Config(ranking_date=date.fromisoformat(ranking_date)),
        )
    if not v2_result.rankings.empty:
        v2_result = ResearchV2Result(
            v2_result.rankings.merge(
                taxonomy, on="ticker", how="left", validate="one_to_one"
            ),
            v2_result.eligibility,
        )
    comparison, _ = build_matched_cohort_comparison(
        investable, baseline_input, baseline, v2_result.rankings,
        v2_result.eligibility,
    )
    matched = comparison.loc[:, [
        "ticker", "company", "sector", "original_baseline_sector_rank",
        "matched_baseline_sector_rank", "research_v2_sector_rank",
        "eligible_peer_count", "comparison_status",
    ]].merge(taxonomy, on="ticker", how="left", validate="one_to_one")
    exclusions = pd.concat([
        baseline_eligibility.loc[~baseline_eligibility["eligible"]].assign(model="BASELINE_V1"),
        v2_result.eligibility.loc[~v2_result.eligibility["eligible"]].assign(model="RESEARCH_V2"),
    ], ignore_index=True)
    provenance = {
        **source_provenance,
        "blind_bundle_version": BLIND_BUNDLE_VERSION,
        "protocol_identifier": PROTOCOL_IDENTIFIER,
        "protocol_sha256": PROTOCOL_SHA256,
        "ranking_date": ranking_date,
        "future_outcome_data_present": False,
        "fundamental_mapping_accepted_count": len(fundamentals),
        "fundamental_provenance": fundamental_provenance,
    }
    snapshot = BlindSnapshot(
        ranking_date, universe, identity, repaired_prices, sensitivity,
        baseline, fundamentals, v2_result.rankings, matched, exclusions,
        provenance,
    )
    for frame in (
        snapshot.universe, snapshot.identity, snapshot.prices,
        snapshot.repair_sensitivity, snapshot.baseline_full,
        snapshot.fundamentals, snapshot.research_v2,
        snapshot.matched_baseline, snapshot.exclusions,
    ):
        assert_outcome_blind(frame, ranking_date if "date" in frame.columns else None)
    return snapshot


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(
        path, index=False, encoding="utf-8", lineterminator="\n",
        float_format="%.17g",
    )


def write_blind_snapshot(snapshot: BlindSnapshot, output: str | Path) -> str:
    root = Path(output)
    if root.exists():
        raise ValueError(f"blind snapshot output already exists: {root}")
    root.mkdir(parents=True)
    files = {
        "historical_universe.csv": snapshot.universe,
        "identity_resolution.csv": snapshot.identity,
        "predictor_prices.csv": snapshot.prices,
        "repair_sensitivity.csv": snapshot.repair_sensitivity,
        "baseline_full.csv": snapshot.baseline_full,
        "fundamentals.csv": snapshot.fundamentals,
        "research_v2.csv": snapshot.research_v2,
        "matched_baseline.csv": snapshot.matched_baseline,
        "exclusions.csv": snapshot.exclusions,
    }
    for name, frame in files.items():
        _write_csv(frame, root / name)
    (root / "provenance.json").write_text(
        json.dumps(snapshot.provenance, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    inventory = [
        {"path": path.name, "sha256": sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size}
        for path in sorted(root.iterdir()) if path.is_file()
    ]
    fingerprint = sha256(canonical_json_bytes(inventory)).hexdigest()
    (root / "manifest.json").write_text(
        json.dumps({
            "schema_version": 1, "blind_prediction_fingerprint": fingerprint,
            "files": inventory,
        }, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    return fingerprint
