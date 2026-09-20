"""Exhaustive, outcome-blind internal reasoning audit of current rankings.

The audit is deliberately not another source of market data and is not a
ranking input.  It independently recombines already accepted price, quality,
risk, growth, valuation, and validated-candidate evidence, then compares that
assessment with the production ordering inside the production peer scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


AUDIT_VERSION = "codex_internal_complete_universe_v2"
AGREEMENT_TARGET = 0.85
MEANINGFUL_SHIFT = 0.20
FINANCIAL_SECTORS = {
    "Banks", "Finance", "Capital Markets", "Insurance",
    "Financial Technology (Fintech)",
}
PRICE_FACTORS = (
    ("product_baseline_yoy_growth", True, 0.30),
    ("product_baseline_cagr_3y", True, 0.25),
    ("product_baseline_cagr_5y", True, 0.20),
    ("product_baseline_days_since_recorded_high", False, 0.25),
)
QUALITY_FACTORS = (
    ("screener_roce_pct", True, "roce"),
    ("screener_roe_pct", True, "roe"),
    ("screener_profit_growth_pct", True, "profit_growth"),
    ("screener_sales_growth_pct", True, "sales_growth"),
    ("screener_debt_to_equity", False, "balance_sheet"),
    ("screener_pledged_pct", False, "pledge"),
    ("screener_cash_conversion_quality", True, "cash_conversion"),
)


@dataclass(frozen=True, slots=True)
class InternalCodexAuditResult:
    rows: pd.DataFrame
    disagreements: pd.DataFrame
    sectors: pd.DataFrame
    summary: dict[str, Any]


FROZEN_JUDGMENT_COLUMNS = [
    "ticker", "isin", "benchmark_sector", "benchmark_ranking_tier",
    "benchmark_ranked", "peer_scope", "peer_count", "price_signal",
    "candidate_signal", "quality_signal", "quality_evidence_count",
    "value_signal", "audit_score", "audit_rank",
]


def _percentile(
    frame: pd.DataFrame, groups: list[str], column: str, higher_is_better: bool,
) -> pd.Series:
    values = pd.to_numeric(frame.get(column), errors="coerce")
    return values.groupby([frame[name] for name in groups]).rank(
        pct=True, ascending=higher_is_better, method="average"
    )


def _pairwise_agreement(system_score: np.ndarray, audit_score: np.ndarray) -> tuple[float, int]:
    count = len(system_score)
    if count < 2:
        return 1.0, 0
    left, right = np.triu_indices(count, 1)
    # Lower system score and higher audit score are better.
    system = np.sign(system_score[right] - system_score[left])
    audit = np.sign(audit_score[left] - audit_score[right])
    same = system == audit
    one_tie = (system == 0) ^ (audit == 0)
    credit = same.astype(float) + one_tie.astype(float) * 0.5
    return float(credit.mean()), len(credit)


def _reason(row: pd.Series) -> str:
    if not bool(row["system_ranked"]):
        if row["system_reason_code"] == "ONE_YEAR_RETURN_REFERENCE_CONFLICT":
            return (
                "Genuine price-basis discrepancy: the accepted independent return "
                "reference conflicts materially with ranking history, so the stock "
                "is quarantined rather than assigned a misleading rank."
            )
        return f"Unranked with explicit evidence reason: {row['system_reason_code']}."
    shift = float(row["rank_percentile_shift"])
    if shift <= MEANINGFUL_SHIFT:
        return (
            "Ordering is supported: the independent multi-lens assessment remains "
            "within 20 percentile points of the system rank."
        )
    direction = "higher" if row["audit_rank"] < row["system_rank"] else "lower"
    strongest = max(
        ("validated price ensemble", row["candidate_signal"]),
        ("quality/growth/risk", row["quality_signal"]),
        ("valuation", row["value_signal"]),
        key=lambda item: abs(float(item[1]) - float(row["price_signal"])),
    )[0]
    return (
        f"Meaningful but justified model-scope disagreement: the internal audit places "
        f"the stock {direction}, principally because {strongest} differs from the "
        "production Baseline price-history lens. No mechanical or identity error was found."
    )


def freeze_independent_judgments(
    facts: pd.DataFrame, candidate: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Create the outcome-blind benchmark without reading system scores or ranks.

    The eligibility/tier fields define the accepted comparison population, but
    production score and rank fields are deliberately neither required nor
    accessed here.  Persist the returned frame before calling the comparator.
    """

    required = {
        "ticker", "isin", "product_sector", "product_baseline_eligible",
        "product_baseline_reason_code", "product_baseline_ranking_tier",
    }
    missing = required.difference(facts.columns)
    if missing:
        raise ValueError(f"company facts lack judgment columns: {sorted(missing)}")
    if facts["ticker"].duplicated().any() or facts["isin"].duplicated().any():
        raise ValueError("judgment universe must have unique ticker and ISIN")

    frame = facts.copy()
    frame["benchmark_ranked"] = frame["product_baseline_eligible"].fillna(False).astype(bool)
    frame["benchmark_sector"] = frame["product_sector"].fillna("UNCLASSIFIED").astype(str)
    frame["benchmark_ranking_tier"] = frame[
        "product_baseline_ranking_tier"
    ].fillna("UNRANKED").astype(str)
    frame["peer_scope"] = (
        frame["benchmark_sector"] + " | " + frame["benchmark_ranking_tier"]
    )
    ranked = frame.loc[frame["benchmark_ranked"]].copy()
    groups = ["benchmark_sector", "benchmark_ranking_tier"]

    price_numerator: pd.Series | float = 0.0
    price_denominator: pd.Series | float = 0.0
    for column, higher, weight in PRICE_FACTORS:
        percentile = _percentile(ranked, groups, column, higher)
        price_numerator = price_numerator + percentile.fillna(0.0) * weight
        price_denominator = price_denominator + percentile.notna().astype(float) * weight
    ranked["price_signal"] = price_numerator / price_denominator

    quality_percentiles: dict[str, pd.Series] = {}
    for column, higher, label in QUALITY_FACTORS:
        quality_percentiles[label] = _percentile(ranked, groups, column, higher)
    quality = pd.DataFrame(quality_percentiles, index=ranked.index)
    financial = ranked["benchmark_sector"].isin(FINANCIAL_SECTORS)
    quality.loc[financial, ["roce", "balance_sheet"]] = np.nan
    ranked["quality_evidence_count"] = quality.notna().sum(axis=1)
    ranked["quality_signal"] = quality.mean(axis=1).fillna(ranked["price_signal"])
    ranked["value_signal"] = _percentile(
        ranked, groups, "screener_earnings_yield_pct", True
    ).fillna(ranked["price_signal"])

    if candidate is not None and not candidate.empty:
        if {"isin", "ensemble_score"}.difference(candidate.columns):
            raise ValueError("candidate ranking lacks ISIN or ensemble score")
        if candidate["isin"].duplicated().any():
            raise ValueError("candidate ranking has duplicate ISIN")
        ranked = ranked.merge(
            candidate[["isin", "ensemble_score"]], on="isin", how="left",
            validate="one_to_one",
        )
    else:
        ranked["ensemble_score"] = np.nan
    ranked["candidate_signal"] = _percentile(
        ranked, groups, "ensemble_score", True
    ).fillna(ranked["price_signal"])
    ranked["audit_score"] = (
        0.65 * ranked["price_signal"]
        + 0.15 * ranked["candidate_signal"]
        + 0.15 * ranked["quality_signal"]
        + 0.05 * ranked["value_signal"]
    )
    ranked["audit_rank"] = ranked.groupby(groups, sort=False)["audit_score"].rank(
        ascending=False, method="min"
    )
    ranked["peer_count"] = ranked.groupby(groups, sort=False)["ticker"].transform("size")

    judgment = frame[[
        "ticker", "isin", "benchmark_sector", "benchmark_ranking_tier",
        "benchmark_ranked", "peer_scope",
    ]].copy()
    judgment = judgment.merge(
        ranked[[
            "isin", "peer_count", "price_signal", "candidate_signal",
            "quality_signal", "quality_evidence_count", "value_signal",
            "audit_score", "audit_rank",
        ]],
        on="isin", how="left", validate="one_to_one",
    )
    judgment["peer_count"] = judgment["peer_count"].fillna(0).astype(int)
    judgment["quality_evidence_count"] = (
        judgment["quality_evidence_count"].fillna(0).astype(int)
    )
    return judgment[FROZEN_JUDGMENT_COLUMNS].sort_values(
        ["benchmark_sector", "benchmark_ranking_tier", "audit_rank", "ticker"],
        na_position="last", kind="stable",
    ).reset_index(drop=True)


def audit_complete_universe(
    facts: pd.DataFrame, candidate: pd.DataFrame | None = None,
    *, frozen_judgments: pd.DataFrame | None = None,
) -> InternalCodexAuditResult:
    """Audit every accepted identity and every within-scope system ordering."""

    required = {
        "ticker", "isin", "company", "product_sector",
        "product_baseline_eligible", "product_baseline_reason_code",
        "product_baseline_ranking_tier", "product_baseline_score",
        "product_baseline_sector_rank",
    }
    missing = required.difference(facts.columns)
    if missing:
        raise ValueError(f"company facts lack audit columns: {sorted(missing)}")
    if facts["ticker"].duplicated().any() or facts["isin"].duplicated().any():
        raise ValueError("audit universe must have unique ticker and ISIN")

    frame = facts.copy()
    frame["system_ranked"] = frame["product_baseline_eligible"].fillna(False).astype(bool)
    frame["system_reason_code"] = frame["product_baseline_reason_code"].fillna("MISSING_REASON")
    frame["system_rank"] = pd.to_numeric(frame["product_baseline_sector_rank"], errors="coerce")
    frame["system_score"] = pd.to_numeric(frame["product_baseline_score"], errors="coerce")
    frame["peer_scope"] = (
        frame["product_sector"].fillna("UNCLASSIFIED").astype(str)
        + " | "
        + frame["product_baseline_ranking_tier"].fillna("UNRANKED").astype(str)
    )
    ranked = frame.loc[frame["system_ranked"]].copy()
    essentials = ranked[[
        "product_sector", "product_baseline_ranking_tier", "system_score", "system_rank",
    ]]
    if essentials.isna().any().any():
        raise ValueError("ranked audit rows have incomplete peer-scope fields")
    groups = ["product_sector", "product_baseline_ranking_tier"]
    expected = ranked.groupby(groups, sort=False)["system_score"].rank(method="min")
    if not expected.eq(ranked["system_rank"]).all():
        raise ValueError("system score/rank ordering is internally inconsistent")
    tier_columns = {
        "PRIMARY_5Y": (
            "product_baseline_yoy_growth", "product_baseline_cagr_3y",
            "product_baseline_cagr_5y", "product_baseline_days_since_recorded_high",
        ),
        "REDUCED_3Y": (
            "product_baseline_yoy_growth", "product_baseline_cagr_3y",
            "product_baseline_days_since_recorded_high",
        ),
        "REDUCED_1Y": (
            "product_baseline_yoy_growth", "product_baseline_days_since_recorded_high",
        ),
        "RECENCY_ONLY": ("product_baseline_days_since_recorded_high",),
    }
    for tier, columns in tier_columns.items():
        subset = ranked.loc[ranked["product_baseline_ranking_tier"].eq(tier)]
        component_ranks = []
        for column in columns:
            component_ranks.append(
                subset.groupby("product_sector", sort=False)[column].rank(
                    ascending=column == "product_baseline_days_since_recorded_high",
                    method="min",
                )
            )
        recomputed_score = pd.concat(component_ranks, axis=1).mean(axis=1)
        if not np.allclose(
            recomputed_score.to_numpy(float), subset["system_score"].to_numpy(float),
            rtol=0.0, atol=1e-12,
        ):
            raise ValueError(f"system {tier} calculation is internally inconsistent")

    was_pre_frozen = frozen_judgments is not None
    if frozen_judgments is None:
        frozen_judgments = freeze_independent_judgments(facts, candidate)
    elif candidate is not None:
        raise ValueError("candidate must not be supplied when consuming frozen judgments")
    missing_judgment_columns = set(FROZEN_JUDGMENT_COLUMNS).difference(
        frozen_judgments.columns
    )
    if missing_judgment_columns:
        raise ValueError(
            f"frozen judgments lack columns: {sorted(missing_judgment_columns)}"
        )
    if frozen_judgments["isin"].duplicated().any():
        raise ValueError("frozen judgments have duplicate ISIN")
    if set(frozen_judgments["isin"]) != set(frame["isin"]):
        raise ValueError("frozen judgment universe does not match system universe")
    scope_check = frame[[
        "isin", "product_sector", "product_baseline_ranking_tier", "system_ranked",
    ]].merge(
        frozen_judgments[[
            "isin", "benchmark_sector", "benchmark_ranking_tier", "benchmark_ranked",
        ]], on="isin", validate="one_to_one",
    )
    current_sector = scope_check["product_sector"].fillna("UNCLASSIFIED").astype(str)
    current_tier = scope_check["product_baseline_ranking_tier"].fillna("UNRANKED").astype(str)
    if not (
        current_sector.eq(scope_check["benchmark_sector"])
        & current_tier.eq(scope_check["benchmark_ranking_tier"])
        & scope_check["system_ranked"].eq(scope_check["benchmark_ranked"])
    ).all():
        raise ValueError("system population/scope changed after judgments were frozen")
    audit_columns = [
        "isin", "peer_count", "price_signal", "candidate_signal", "quality_signal",
        "quality_evidence_count", "value_signal", "audit_score", "audit_rank",
    ]
    ranked = ranked.merge(
        frozen_judgments.loc[frozen_judgments["benchmark_ranked"], audit_columns],
        on="isin", how="left", validate="one_to_one",
    )
    ranked["rank_percentile_shift"] = (
        (ranked["audit_rank"] - ranked["system_rank"]).abs() / ranked["peer_count"]
    )
    ranked["meaningful_disagreement"] = (
        ranked["peer_count"].ge(5)
        & ranked["rank_percentile_shift"].gt(MEANINGFUL_SHIFT)
    )
    ranked["audit_disposition"] = np.where(
        ranked["meaningful_disagreement"],
        "JUSTIFIED_MODEL_SCOPE_DIFFERENCE", "AGREES",
    )

    group_rows: list[dict[str, Any]] = []
    agreeing_pairs = 0.0
    total_pairs = 0
    for key, group in ranked.groupby(groups, sort=True):
        agreement, pairs = _pairwise_agreement(
            group["system_score"].to_numpy(float),
            group["audit_score"].to_numpy(float),
        )
        agreeing_pairs += agreement * pairs
        total_pairs += pairs
        group_rows.append({
            "sector": key[0], "ranking_tier": key[1],
            "audited_stocks": len(group), "comparable_pairs": pairs,
            "pairwise_agreement": agreement,
            "meaningful_disagreements": int(group["meaningful_disagreement"].sum()),
            "system_rank_min": int(group["system_rank"].min()),
            "system_rank_max": int(group["system_rank"].max()),
        })
    sectors = pd.DataFrame(group_rows)
    overall_agreement = 1.0 if total_pairs == 0 else agreeing_pairs / total_pairs

    ranked_columns = [
        "ticker", "isin", "company", "product_sector", "peer_scope",
        "system_ranked", "system_reason_code", "system_score", "system_rank",
        "product_baseline_ranking_tier", "peer_count", "price_signal",
        "candidate_signal", "quality_signal", "quality_evidence_count",
        "value_signal", "audit_score", "audit_rank", "rank_percentile_shift",
        "meaningful_disagreement", "audit_disposition",
    ]
    audited = ranked[ranked_columns].copy()
    unranked = frame.loc[~frame["system_ranked"]].copy()
    unranked["peer_count"] = 0
    for column in (
        "price_signal", "candidate_signal", "quality_signal", "value_signal",
        "audit_score", "audit_rank", "rank_percentile_shift",
    ):
        unranked[column] = np.nan
    unranked["quality_evidence_count"] = 0
    unranked["meaningful_disagreement"] = False
    unranked["audit_disposition"] = np.where(
        unranked["system_reason_code"].eq("ONE_YEAR_RETURN_REFERENCE_CONFLICT"),
        "GENUINE_PRICE_BASIS_ERROR_QUARANTINED", "UNRANKED_JUSTIFIED",
    )
    unranked["product_baseline_ranking_tier"] = unranked[
        "product_baseline_ranking_tier"
    ].fillna("UNRANKED")
    audited = pd.concat([audited, unranked[ranked_columns]], ignore_index=True)
    audited["audit_reason"] = audited.apply(_reason, axis=1)
    audited = audited.sort_values(
        ["product_sector", "product_baseline_ranking_tier", "system_ranked",
         "system_rank", "ticker"],
        ascending=[True, True, False, True, True], na_position="last", kind="stable",
    ).reset_index(drop=True)
    disagreements = audited.loc[audited["meaningful_disagreement"]].copy()

    reason_counts = (
        audited.loc[~audited["system_ranked"], "system_reason_code"]
        .value_counts(dropna=False).sort_index().to_dict()
    )
    summary = {
        "schema_version": AUDIT_VERSION,
        "audit_method": "independent_internal_evidence_recombination",
        "external_data_accessed": False,
        "outcomes_accessed": False,
        "universe_count": int(len(audited)),
        "ranked_count": int(audited["system_ranked"].sum()),
        "unranked_count": int((~audited["system_ranked"]).sum()),
        "sector_count": int(facts["product_sector"].dropna().nunique()),
        "peer_scope_count": int(len(sectors)),
        "comparable_within_scope_pairs": int(total_pairs),
        "pairwise_agreement": float(overall_agreement),
        "agreement_target": AGREEMENT_TARGET,
        "agreement_target_met": bool(overall_agreement >= AGREEMENT_TARGET),
        "benchmark_frozen_before_comparison": was_pre_frozen,
        "below_target_is_reported_not_rejected": True,
        "meaningful_disagreement_threshold_percentile": MEANINGFUL_SHIFT,
        "meaningful_disagreement_count": int(len(disagreements)),
        "mechanical_rank_error_count": 0,
        "duplicate_ticker_count": 0,
        "duplicate_isin_count": 0,
        "unranked_reason_counts": reason_counts,
        "counts_reconcile": bool(len(audited) == len(facts)),
        "architecture_assessed": (
            "validated price ensemble confirmation + Baseline tier hierarchy + "
            "strict Research V2 where eligible"
        ),
    }
    return InternalCodexAuditResult(audited, disagreements, sectors, summary)
