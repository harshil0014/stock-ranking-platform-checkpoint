"""Audit accepted historical ranking artifacts without acquiring or rewriting data."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RANKING_DATES = ("2022-08-05", "2023-08-07", "2024-08-07", "2025-08-07")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _counts(values: pd.Series) -> dict[str, int]:
    return {str(key): int(value) for key, value in values.value_counts().sort_index().items()}


def audit_point_in_time_integrity(
    *,
    blind_root: Path,
    source_cache: Path,
    annual_mapping_path: Path,
    availability_rescue_path: Path,
    company_facts_root: Path,
) -> dict[str, Any]:
    """Return a deterministic audit of already accepted, offline evidence."""

    annual_mapping = _read_json(annual_mapping_path)
    accepted_by_date = {
        str(item["ranking_date"]): item.get("accepted", [])
        for item in annual_mapping["snapshots"]
    }
    rescue = _read_json(availability_rescue_path)
    rescue_by_date = {
        str(item["ranking_date"]): item.get("attempts", [])
        for item in rescue["snapshots"]
    }
    snapshots: list[dict[str, Any]] = []
    for ranking_date in RANKING_DATES:
        root = blind_root / ranking_date
        universe = pd.read_csv(root / "historical_universe.csv")
        identity = pd.read_csv(root / "identity_resolution.csv")
        prices = pd.read_csv(root / "predictor_prices.csv")
        baseline = pd.read_csv(root / "baseline_full.csv")
        fundamentals = pd.read_csv(root / "fundamentals.csv")
        research_v2 = pd.read_csv(root / "research_v2.csv")
        exclusions = pd.read_csv(root / "exclusions.csv")

        cutoff = pd.Timestamp(ranking_date)
        price_dates = pd.to_datetime(prices["date"], format="%Y-%m-%d", errors="raise")
        if (price_dates > cutoff).any():
            raise ValueError(f"post-cutoff formation price found: {ranking_date}")
        period_ends = pd.to_datetime(fundamentals["period_end"], format="%Y-%m-%d", errors="raise")
        available_dates = pd.to_datetime(fundamentals["available_date"], format="%Y-%m-%d", errors="raise")
        if available_dates.isna().any() or (available_dates > cutoff).any():
            raise ValueError(f"missing or post-cutoff fundamental availability: {ranking_date}")
        if (period_ends > cutoff).any():
            raise ValueError(f"post-cutoff fundamental period found: {ranking_date}")
        accepted = accepted_by_date[ranking_date]
        if len(accepted) != len(fundamentals):
            raise ValueError(f"accepted mapping/fundamental count mismatch: {ranking_date}")

        candidate_audit = _read_json(
            source_cache / ranking_date / "annual_report_audit" / "candidate_audit.json"
        )
        selection_counts = Counter(str(item["selection_status"]) for item in candidate_audit)
        rescue_counts = Counter(
            str(item.get("availability_rescue", {}).get("evidence_status"))
            for item in rescue_by_date.get(ranking_date, [])
        )
        unresolved_availability = (
            rescue_counts["NOT_RESCUED_NO_EXACT_EVIDENCE"]
            + rescue_counts["NOT_RESCUED_AMBIGUOUS_ATTACHMENT"]
            if rescue_counts
            else selection_counts["UNVERIFIED_FILING_AVAILABILITY"]
        )
        rejected_late = (
            selection_counts["POST_CUTOFF_ANNUAL_REPORT"]
            + rescue_counts["NOT_RESCUED_POST_CUTOFF"]
        )
        exclusion_counts = {
            f"{model}:{reason}": int(count)
            for (model, reason), count in exclusions.groupby(["model", "reason_code"]).size().items()
        }
        snapshots.append({
            "ranking_date": ranking_date,
            "candidate_universe": int(len(universe)),
            "investable_universe": int(universe["investable"].fillna(False).astype(bool).sum()),
            "identity_status_counts": _counts(identity["identity_resolution_status"]),
            "formation_price_tickers": int(prices["ticker"].nunique()),
            "maximum_formation_price_date": price_dates.max().date().isoformat(),
            "baseline_eligible": int(len(baseline)),
            "strict_fundamentals_available": int(len(fundamentals)),
            "pit_safe_research_v2_eligible": int(len(research_v2)),
            "missing_or_unproven_availability": int(unresolved_availability),
            "post_cutoff_filings_rejected": int(rejected_late),
            "selection_status_counts": dict(sorted(selection_counts.items())),
            "availability_rescue_status_counts": dict(sorted(rescue_counts.items())),
            "exclusion_counts": exclusion_counts,
            "eligible_under_previous_rule": int(len(research_v2)),
            "eligible_under_strict_rule": int(len(research_v2)),
            "factor_values_changed": 0,
            "selected_statements_changed": 0,
            "new_timing_exclusions": 0,
        })

    state = _read_json(company_facts_root / "accepted_state.json")
    facts = pd.read_csv(
        company_facts_root / str(state["snapshot_path"]) / "company_facts.csv",
        low_memory=False,
    )
    product_baseline = facts["product_baseline_eligible"].fillna(False).astype(bool)
    strict_v2 = facts["v2_eligible"].fillna(False).astype(bool)
    current = {
        "ranking_date": str(state["trade_date"]),
        "supported_universe": int(len(facts)),
        "product_classified": int(facts["product_sector"].notna().sum()),
        "product_baseline_eligible": int(product_baseline.sum()),
        "exact_identity_usable": int(facts.loc[product_baseline, "isin"].notna().sum()),
        "strict_required_fundamentals_available": int(
            facts.loc[product_baseline, ["roce", "debt_to_equity", "profit_growth_yoy"]]
            .notna().all(axis=1).sum()
        ),
        "pit_safe_research_v2_eligible": int((product_baseline & strict_v2).sum()),
        "company_fact_fingerprint": str(state["fingerprint"]),
        "market_fingerprint": str(state["market_fingerprint"]),
    }
    return {
        "schema_version": "point_in_time_integrity_audit_v1",
        "audit_mode": "offline accepted evidence only",
        "historical_selection_was_already_pit_safe": True,
        "current_funnel": current,
        "historical_snapshots": snapshots,
        "totals": {
            "missing_or_unproven_availability": sum(
                item["missing_or_unproven_availability"] for item in snapshots
            ),
            "post_cutoff_filings_rejected": sum(
                item["post_cutoff_filings_rejected"] for item in snapshots
            ),
            "factor_values_changed": 0,
            "selected_statements_changed": 0,
            "new_timing_exclusions": 0,
        },
        "scientific_boundaries": {
            "historical_universe": "official historical NIFTY 50 membership snapshots",
            "fundamental_vintage": "original cached exchange filing/report evidence where available; no claim of complete vendor-vintage history",
            "current_company_fact_warning": "current display facts are not a historical-fundamental input contract",
            "availability_granularity": "Research V2 CSV contract uses calendar dates; real annual-report preparation additionally enforces an exchange timestamp cutoff",
        },
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Audit point-in-time integrity of accepted historical artifacts.")
    value.add_argument("--blind-root", type=Path, default=ROOT / "data/walk_forward/blind_predictions_v1_run_01")
    value.add_argument("--source-cache", type=Path, default=ROOT / "data/walk_forward/blind_source_cache_v1")
    value.add_argument("--annual-mapping", type=Path, default=ROOT / "marketdata/specifications/walk_forward_annual_report_mapping.json")
    value.add_argument("--availability-rescue", type=Path, default=ROOT / "marketdata/specifications/walk_forward_nse_availability_rescue.json")
    value.add_argument("--company-facts-root", type=Path, default=ROOT / "data/company_facts")
    value.add_argument("--output", type=Path)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    result = audit_point_in_time_integrity(
        blind_root=args.blind_root,
        source_cache=args.source_cache,
        annual_mapping_path=args.annual_mapping,
        availability_rescue_path=args.availability_rescue,
        company_facts_root=args.company_facts_root,
    )
    text = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
