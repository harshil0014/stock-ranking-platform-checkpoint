"""Auditable confidence-aware completion of the accepted equity universe.

Observed company facts are never modified in place.  This module produces a
separate completed view, a cell-level estimate-code matrix, and a complete
sector ranking.  Every approximation is therefore distinguishable from the
accepted source snapshot that remains the system of record.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd


COMPLETION_VERSION = "complete_universe_confidence_v1"
ESTIMATE_CODES = {
    0: {"label": "OBSERVED", "confidence": "OBSERVED"},
    1: {"label": "SECTOR_MEDIAN_OR_MODE", "confidence": "MODERATE"},
    2: {"label": "UNIVERSE_MEDIAN_OR_MODE", "confidence": "LOW"},
    3: {"label": "EXPLICIT_MODEL_FALLBACK", "confidence": "VERY_LOW"},
    4: {"label": "INTERNAL_PROXY_FIELD", "confidence": "MODERATE"},
    5: {"label": "CONFLICT_RECONSTRUCTION", "confidence": "LOW"},
    6: {"label": "EXACT_INTERNAL_TAXONOMY_MAPPING", "confidence": "MODERATE"},
    7: {"label": "NAME_TOKEN_TAXONOMY_MODEL", "confidence": "LOW"},
    8: {"label": "COMPLETE_UNIVERSE_DERIVED_RANK", "confidence": "MODEL_DERIVED"},
}
PRICE_FEATURES = (
    ("product_baseline_yoy_growth", True, 0.30),
    ("product_baseline_cagr_3y", True, 0.25),
    ("product_baseline_cagr_5y", True, 0.20),
    ("product_baseline_days_since_recorded_high", False, 0.25),
)
QUALITY_FEATURES = (
    ("screener_roce_pct", True),
    ("screener_roe_pct", True),
    ("screener_profit_growth_pct", True),
    ("screener_sales_growth_pct", True),
    ("screener_debt_to_equity", False),
    ("screener_pledged_pct", False),
    ("screener_cash_conversion_quality", True),
)
FINANCIAL_SECTORS = {
    "Banks", "Finance", "Capital Markets", "Insurance",
    "Financial Technology (Fintech)",
}
TAXONOMY_COLUMNS = (
    "screener_industry_group", "screener_industry", "official_sector",
    "derived_research_sector", "derived_research_industry", "secondary_sector",
    "secondary_industry", "bulk_classification_sector",
    "bulk_classification_industry",
)
DATE_PATTERN = re.compile(r"(?:date|_as_of|_at|period_end)$")
URL_PATTERN = re.compile(r"(?:url|source_url)$")
HASH_PATTERN = re.compile(r"(?:sha256|fingerprint)$")
GENERIC_NAME_TOKENS = {
    "limited", "ltd", "india", "indian", "industries", "industry", "company",
    "corporation", "enterprise", "enterprises", "international", "holdings",
    "private", "products", "services", "solutions", "global", "the",
}
LEARNED_NAME_RULES = (
    (r"pharma|pharmachem|lifescience|drugs?|labs?\b", "Pharmaceuticals & Biotechnology"),
    (r"chemical|indchem|esters?|polymers?|plast\b", "Chemicals & Petrochemicals"),
    (r"securit|stock broker|capital market|finlease|finance|leasing", "Capital Markets"),
    (r"fintech|payment", "Financial Technology (Fintech)"),
    (r"bank\b", "Banks"),
    (r"steel|metals?|loha|ispat|sections", "Ferrous Metals"),
    (r"filament|spinpro|spinner|textile|garment|apparel|fabric|knitter|synthe", "Textiles & Apparels"),
    (r"foods?|baker|agro|agritec|crop|seeds?", "Agricultural Food & other Products"),
    (r"hotel|resort|club", "Leisure Services"),
    (r"media|entertainment", "Media"),
    (r"software|computer|systems?\s*&\s*technolog|tech\b", "IT - Services"),
    (r"electrical|transformer", "Electrical Equipment"),
    (r"renewable|solar|energy", "Power"),
    (r"buildcon|infra\b|infrastructure|projects?|construction", "Construction"),
    (r"maritime|roadways|logitek|logistics|speedex", "Transport Services"),
    (r"coater|engineering|engitech|tools?\b", "Industrial Products"),
    (r"ceramic|mica|glass", "Consumer Durables"),
    (r"oil\b|petro", "Oil"),
    (r"academy|facilitator|services", "Commercial Services & Supplies"),
    (r"ventures|multitrade|commercial|impex|trade udyog|international", "Metals & Minerals Trading"),
    (r"rentomojo|rental", "Other Consumer Services"),
)


@dataclass(frozen=True, slots=True)
class CompletionResult:
    completed: pd.DataFrame
    estimate_codes: pd.DataFrame
    rankings: pd.DataFrame
    resolved_exclusions: pd.DataFrame
    field_summary: pd.DataFrame
    summary: dict[str, Any]


def _missing(frame: pd.DataFrame) -> pd.DataFrame:
    missing = frame.isna()
    objects = frame.select_dtypes(include=["object", "string"]).columns
    for column in objects:
        blank = frame[column].astype("string").str.strip().eq("").fillna(True)
        missing[column] = missing[column] | blank
    return missing


def _mode(values: pd.Series) -> Any | None:
    clean = values.dropna()
    if clean.dtype == object or isinstance(clean.dtype, pd.StringDtype):
        clean = clean.loc[clean.astype(str).str.strip().ne("")]
    if clean.empty:
        return None
    modes = clean.mode(dropna=True)
    return None if modes.empty else modes.iloc[0]


def _taxonomy_maps(facts: pd.DataFrame) -> dict[str, dict[str, tuple[str, int, float]]]:
    known = facts.loc[facts["product_sector"].notna()].copy()
    mappings: dict[str, dict[str, tuple[str, int, float]]] = {}
    for column in TAXONOMY_COLUMNS:
        if column not in known:
            continue
        subset = known.loc[known[column].notna(), [column, "product_sector"]].copy()
        subset[column] = subset[column].astype(str).str.strip().str.casefold()
        table: dict[str, tuple[str, int, float]] = {}
        for value, group in subset.groupby(column, sort=False):
            counts = group["product_sector"].value_counts()
            table[value] = (str(counts.index[0]), int(counts.iloc[0]), float(counts.iloc[0] / len(group)))
        mappings[column] = table
    return mappings


def _token_sector_model(facts: pd.DataFrame) -> dict[str, tuple[str, int, float]]:
    counts: dict[str, dict[str, int]] = {}
    known = facts.loc[facts["product_sector"].notna(), ["company", "ticker", "product_sector"]]
    for row in known.itertuples(index=False):
        tokens = set(re.findall(r"[a-z]{4,}", f"{row.company} {row.ticker}".casefold()))
        for token in tokens.difference(GENERIC_NAME_TOKENS):
            sector_counts = counts.setdefault(token, {})
            sector_counts[str(row.product_sector)] = sector_counts.get(str(row.product_sector), 0) + 1
    result: dict[str, tuple[str, int, float]] = {}
    for token, sector_counts in counts.items():
        ordered = sorted(sector_counts.items(), key=lambda item: (-item[1], item[0]))
        total = sum(sector_counts.values())
        result[token] = (ordered[0][0], ordered[0][1], ordered[0][1] / total)
    return result


def _complete_sectors(facts: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    sectors = facts["product_sector"].copy()
    methods = pd.Series("OBSERVED_PRODUCT_SECTOR", index=facts.index, dtype="object")
    confidences = pd.Series("OBSERVED", index=facts.index, dtype="object")
    mappings = _taxonomy_maps(facts)
    tokens = _token_sector_model(facts)
    for index, row in facts.loc[sectors.isna()].iterrows():
        votes: list[tuple[float, str, str]] = []
        for priority, column in enumerate(TAXONOMY_COLUMNS):
            value = row.get(column)
            if pd.isna(value) or not str(value).strip():
                continue
            match = mappings.get(column, {}).get(str(value).strip().casefold())
            if match is not None and match[2] >= 0.60:
                weight = (len(TAXONOMY_COLUMNS) - priority) * match[1] * match[2]
                votes.append((weight, match[0], column))
        if votes:
            votes.sort(key=lambda item: (-item[0], item[1]))
            sectors.at[index] = votes[0][1]
            methods.at[index] = f"EXACT_INTERNAL_MAPPING:{votes[0][2]}"
            confidences.at[index] = "MODERATE"
            continue
        company_name = f"{row.get('company', '')} {row.get('ticker', '')}".casefold()
        learned = next(
            ((pattern, sector) for pattern, sector in LEARNED_NAME_RULES
             if re.search(pattern, company_name)),
            None,
        )
        if learned is not None:
            sectors.at[index] = learned[1]
            methods.at[index] = f"LEARNED_NAME_HEURISTIC:{learned[0]}"
            confidences.at[index] = "LOW"
            continue
        name_tokens = set(re.findall(
            r"[a-z]{4,}", f"{row.get('company', '')} {row.get('ticker', '')}".casefold()
        )).difference(GENERIC_NAME_TOKENS)
        token_votes = [
            (support * purity, sector, token)
            for token in name_tokens
            if token in tokens
            for sector, support, purity in [tokens[token]]
            if support >= 2 and purity >= 0.65
        ]
        if token_votes:
            token_votes.sort(key=lambda item: (-item[0], item[1], item[2]))
            sectors.at[index] = token_votes[0][1]
            methods.at[index] = f"NAME_TOKEN_MODEL:{token_votes[0][2]}"
            confidences.at[index] = "LOW"
        else:
            sectors.at[index] = "Diversified"
            methods.at[index] = "DIVERSIFIED_FALLBACK_NO_TAXONOMY_SIGNAL"
            confidences.at[index] = "VERY_LOW"
    return sectors.astype(str), methods, confidences


def _sector_fill_numeric(
    values: pd.Series, sectors: pd.Series, missing: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    numeric = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
    result = numeric.copy()
    codes = pd.Series(0, index=values.index, dtype="uint8")
    effective_missing = missing | numeric.isna()
    medians = numeric.groupby(sectors).transform("median")
    sector_mask = effective_missing & medians.notna()
    result.loc[sector_mask] = medians.loc[sector_mask]
    codes.loc[sector_mask] = 1
    global_median = numeric.median()
    global_mask = result.isna() & pd.notna(global_median)
    result.loc[global_mask] = float(global_median)
    codes.loc[global_mask] = 2
    fallback = result.isna()
    result.loc[fallback] = 0.0
    codes.loc[fallback] = 3
    return result, codes


def _complete_all_fields(
    facts: pd.DataFrame, sectors: pd.Series, sector_methods: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    completed = facts.copy()
    missing = _missing(facts)
    codes = pd.DataFrame(0, index=facts.index, columns=facts.columns, dtype="uint8")
    completed["product_sector"] = sectors
    sector_missing = missing["product_sector"]
    codes.loc[sector_missing & sector_methods.str.startswith("EXACT"), "product_sector"] = 6
    codes.loc[
        sector_missing & sector_methods.str.startswith(("NAME", "LEARNED")),
        "product_sector",
    ] = 7
    codes.loc[sector_missing & sector_methods.str.startswith("DIVERSIFIED"), "product_sector"] = 3

    proxies = {
        "official_debt_to_equity": "screener_debt_to_equity",
        "official_revenue_growth": "screener_sales_growth_pct",
        "official_profit_growth_yoy": "screener_profit_growth_pct",
        "product_basic_industry": "product_industry",
        "official_industry": "product_industry",
        "official_basic_industry": "product_industry",
        "derived_research_basic_industry": "product_industry",
        "bulk_classification_industry": "product_industry",
    }
    for target, source in proxies.items():
        if target not in completed or source not in completed:
            continue
        if target not in {
            "official_debt_to_equity", "official_revenue_growth",
            "official_profit_growth_yoy",
        }:
            completed[target] = completed[target].astype("object")
        mask = missing[target] & ~_missing(completed[[source]])[source]
        values = completed.loc[mask, source]
        if target in {"official_revenue_growth", "official_profit_growth_yoy"}:
            values = pd.to_numeric(values, errors="coerce") / 100.0
        completed.loc[mask, target] = values
        codes.loc[mask, target] = 4

    for column in facts.columns:
        remaining = _missing(completed[[column]])[column]
        if not remaining.any():
            continue
        if pd.api.types.is_bool_dtype(facts[column]):
            mode_by_sector = completed[column].groupby(sectors).transform(_mode)
            sector_mask = remaining & mode_by_sector.notna()
            completed.loc[sector_mask, column] = mode_by_sector.loc[sector_mask].astype(bool)
            codes.loc[sector_mask, column] = 1
            completed.loc[remaining & ~sector_mask, column] = False
            codes.loc[remaining & ~sector_mask, column] = 3
        elif pd.api.types.is_numeric_dtype(facts[column]):
            completed[column], numeric_codes = _sector_fill_numeric(
                completed[column], sectors, remaining
            )
            codes[column] = codes[column].where(codes[column].ne(0), numeric_codes)
        else:
            if URL_PATTERN.search(column):
                completed.loc[remaining, column] = [
                    f"estimated://no-observed-source/{ticker}/{column}"
                    for ticker in completed.loc[remaining, "ticker"].astype(str)
                ]
                codes.loc[remaining, column] = 3
                continue
            if HASH_PATTERN.search(column):
                completed.loc[remaining, column] = "ESTIMATED_NO_OBSERVED_HASH"
                codes.loc[remaining, column] = 3
                continue
            if DATE_PATTERN.search(column):
                completed.loc[remaining, column] = completed.loc[remaining, "trade_date"].astype(str)
                codes.loc[remaining, column] = 3
                continue
            if column == "company_profile":
                completed.loc[remaining, column] = [
                    f"Estimated profile: {company} is assigned to {sector} using internal evidence."
                    for company, sector in zip(
                        completed.loc[remaining, "company"], sectors.loc[remaining]
                    )
                ]
                codes.loc[remaining, column] = 3
                continue
            modes = completed[column].groupby(sectors).transform(_mode)
            sector_mask = remaining & modes.notna()
            completed.loc[sector_mask, column] = modes.loc[sector_mask]
            codes.loc[sector_mask, column] = 1
            remaining = _missing(completed[[column]])[column]
            global_mode = _mode(completed[column])
            if global_mode is not None:
                completed.loc[remaining, column] = global_mode
                codes.loc[remaining, column] = 2
            remaining = _missing(completed[[column]])[column]
            completed.loc[remaining, column] = f"ESTIMATED_FROM_INTERNAL_EVIDENCE:{column}"
            codes.loc[remaining, column] = 3
    return completed, codes


def _percentile(frame: pd.DataFrame, column: str, higher: bool) -> pd.Series:
    return frame.groupby("complete_sector", sort=False)[column].rank(
        pct=True, ascending=higher, method="average"
    )


def complete_universe(
    facts: pd.DataFrame, candidate: pd.DataFrame | None = None,
) -> CompletionResult:
    """Complete all accepted rows and assign one confidence-adjusted sector rank."""

    required = {"ticker", "isin", "company", "product_sector", "product_baseline_eligible"}
    missing_required = required.difference(facts.columns)
    if missing_required:
        raise ValueError(f"company facts lack completion columns: {sorted(missing_required)}")
    if facts["ticker"].duplicated().any() or facts["isin"].duplicated().any():
        raise ValueError("completion universe must have unique ticker and ISIN")
    original_missing = _missing(facts)
    sectors, sector_methods, sector_confidence = _complete_sectors(facts)
    completed, codes = _complete_all_fields(facts, sectors, sector_methods)

    # Conflicted one-year histories are reconstructed from the accepted exact-
    # identity reference return when available, otherwise from sector peers.
    conflict = facts["product_baseline_reason_code"].eq("ONE_YEAR_RETURN_REFERENCE_CONFLICT")
    reference = pd.to_numeric(facts.get("screener_return_1y_pct"), errors="coerce") / 100.0
    sector_reference = reference.groupby(sectors).transform("median")
    replacement = reference.where(reference.notna(), sector_reference)
    global_reference = reference.median()
    replacement = replacement.fillna(0.0 if pd.isna(global_reference) else global_reference)
    completed.loc[conflict, "product_baseline_yoy_growth"] = replacement.loc[conflict]
    codes.loc[conflict, "product_baseline_yoy_growth"] = 5

    # The iterative field fills fragment the frame; compact it before adding
    # the model output columns used by the website and export.
    completed = completed.copy()
    completed["complete_sector"] = sectors
    completed["complete_sector_method"] = sector_methods
    completed["complete_sector_confidence"] = sector_confidence
    ranking_input_codes: list[pd.Series] = []
    price_signal = 0.0
    for column, higher, weight in PRICE_FEATURES:
        price_signal = price_signal + weight * _percentile(completed, column, higher)
        ranking_input_codes.append(codes[column])
    completed["complete_price_signal"] = price_signal

    quality_parts = []
    for column, higher in QUALITY_FEATURES:
        values = _percentile(completed, column, higher)
        if column in {"screener_roce_pct", "screener_debt_to_equity"}:
            values = values.mask(sectors.isin(FINANCIAL_SECTORS))
        quality_parts.append(values)
        ranking_input_codes.append(codes[column])
    completed["complete_quality_signal"] = pd.concat(quality_parts, axis=1).mean(axis=1).fillna(0.5)
    completed["complete_value_signal"] = _percentile(
        completed, "screener_earnings_yield_pct", True
    )
    ranking_input_codes.append(codes["screener_earnings_yield_pct"])

    if candidate is not None and not candidate.empty:
        if {"isin", "ensemble_score"}.difference(candidate.columns):
            raise ValueError("candidate ranking lacks ISIN or ensemble score")
        if candidate["isin"].duplicated().any():
            raise ValueError("candidate ranking has duplicate ISIN")
        candidate_values = completed[["isin", "complete_sector"]].merge(
            candidate[["isin", "ensemble_score"]], on="isin", how="left",
            validate="one_to_one",
        )["ensemble_score"]
    else:
        candidate_values = pd.Series(np.nan, index=completed.index)
    candidate_values = pd.to_numeric(candidate_values, errors="coerce")
    candidate_observed = candidate_values.notna()
    candidate_sector_median = candidate_values.groupby(sectors).transform("median")
    candidate_values = candidate_values.fillna(candidate_sector_median).fillna(candidate_values.median()).fillna(0.0)
    completed["_complete_candidate_value"] = candidate_values.to_numpy()
    completed["complete_candidate_signal"] = _percentile(
        completed, "_complete_candidate_value", True
    )

    feature_codes = pd.concat(ranking_input_codes, axis=1)
    observed_count = feature_codes.eq(0).sum(axis=1) + candidate_observed.astype(int)
    total_count = feature_codes.shape[1] + 1
    reliability = observed_count / total_count
    classification_multiplier = sector_confidence.map({
        "OBSERVED": 1.0, "MODERATE": 0.85, "LOW": 0.65, "VERY_LOW": 0.45,
    }).astype(float)
    reliability = (reliability * classification_multiplier).clip(lower=0.10, upper=1.0)
    raw_score = (
        0.55 * completed["complete_price_signal"]
        + 0.20 * completed["complete_candidate_signal"]
        + 0.20 * completed["complete_quality_signal"]
        + 0.05 * completed["complete_value_signal"]
    )
    completed["complete_raw_score"] = raw_score
    completed["complete_reliability"] = reliability
    completed["complete_score"] = 0.5 + reliability * (raw_score - 0.5)
    completed["complete_confidence"] = pd.cut(
        reliability, bins=[-np.inf, 0.40, 0.65, 0.85, np.inf],
        labels=["VERY_LOW_ESTIMATED", "LOW", "MODERATE", "HIGH"],
    ).astype(str)
    completed["complete_observed_ranking_inputs"] = observed_count.astype(int)
    completed["complete_estimated_ranking_inputs"] = (total_count - observed_count).astype(int)
    ordered = completed.sort_values(
        ["complete_sector", "complete_score", "complete_reliability", "ticker"],
        ascending=[True, False, False, True], kind="stable",
    )
    rank_series = ordered.groupby("complete_sector", sort=False).cumcount() + 1
    completed["complete_sector_rank"] = rank_series.reindex(completed.index).astype(int)
    completed["complete_peer_count"] = completed.groupby("complete_sector")["ticker"].transform("size").astype(int)
    completed["complete_eligible"] = True
    completed["complete_rank_scope"] = "sector_complete_accepted_universe"
    completed["complete_method_version"] = COMPLETION_VERSION
    completed["complete_original_reason_code"] = facts["product_baseline_reason_code"].astype(str)

    # Present the completed product model in the completion artifact while the
    # accepted source snapshot remains unchanged and addressable by fingerprint.
    derived_mapping = {
        "product_sector": "complete_sector",
        "product_baseline_score": "complete_score",
        "product_baseline_sector_rank": "complete_sector_rank",
        "product_baseline_confidence": "complete_confidence",
        "product_baseline_rank_scope": "complete_rank_scope",
        "product_baseline_method_version": "complete_method_version",
    }
    for target, source in derived_mapping.items():
        completed[target] = completed[source]
        codes[target] = 8
    completed["product_baseline_eligible"] = True
    completed["product_baseline_reason_code"] = "COMPLETE_CONFIDENCE_ADJUSTED_RANK"
    completed["product_baseline_reason"] = (
        "Complete-universe rank using observed facts plus explicitly coded internal estimates; "
        "weaker evidence is shrunk toward the sector midpoint."
    )
    completed["product_baseline_ranking_tier"] = "COMPLETE_CONFIDENCE_ADJUSTED"
    completed["product_baseline_feature_count"] = total_count
    for target in (
        "product_baseline_eligible", "product_baseline_reason_code",
        "product_baseline_reason", "product_baseline_ranking_tier",
        "product_baseline_feature_count",
    ):
        codes[target] = 8
    if "workbook_strategy_rank" in completed:
        completed["workbook_strategy_rank"] = completed["complete_sector_rank"]
        codes["workbook_strategy_rank"] = 8

    completed = completed.drop(columns=["_complete_candidate_value"])
    if _missing(completed).any(axis=None):
        columns = completed.columns[_missing(completed).any()].tolist()
        raise ValueError(f"completion left missing fields: {columns}")
    if not completed["complete_eligible"].all() or completed["complete_sector_rank"].isna().any():
        raise ValueError("completion left an accepted identity unranked")
    expected_ranks = completed.groupby("complete_sector", sort=False)["complete_sector_rank"].apply(
        lambda values: sorted(values.astype(int).tolist()) == list(range(1, len(values) + 1))
    )
    if not expected_ranks.all():
        raise ValueError("complete sector ranks are not unique and contiguous")
    original_missing_coded = bool(
        (codes.where(original_missing).fillna(1).astype(int) > 0).all(axis=None)
    )
    if not original_missing_coded:
        raise ValueError("an originally missing cell lacks an estimate code")

    rankings = completed[[
        "ticker", "isin", "company", "complete_sector", "complete_sector_method",
        "complete_sector_confidence", "complete_score", "complete_raw_score",
        "complete_sector_rank", "complete_peer_count", "complete_confidence",
        "complete_reliability", "complete_observed_ranking_inputs",
        "complete_estimated_ranking_inputs", "complete_price_signal",
        "complete_candidate_signal", "complete_quality_signal", "complete_value_signal",
        "complete_original_reason_code", "complete_rank_scope", "complete_method_version",
    ]].sort_values(["complete_sector", "complete_sector_rank"], kind="stable")
    formerly_excluded = ~facts["product_baseline_eligible"].fillna(False).astype(bool)
    resolved = rankings.loc[formerly_excluded].copy()
    resolved["audit_disposition"] = np.select(
        [
            resolved["complete_sector_confidence"].eq("VERY_LOW"),
            resolved["complete_confidence"].isin(["VERY_LOW_ESTIMATED", "LOW"]),
        ],
        ["FALLBACK_CLASSIFICATION_AND_CONFIDENCE_ADJUSTED_ESTIMATE",
         "RESOLVED_WITH_CONFIDENCE_ADJUSTED_ESTIMATE"],
        default="RESOLVED_WITH_STRONG_INTERNAL_EVIDENCE",
    )
    resolved["audit_reason"] = (
        "Previously excluded row reviewed against completed sector peers; rank is finite, "
        "sector-scoped, confidence-adjusted, and its estimates remain cell-coded."
    )

    original_missing_count = original_missing.sum().astype(int)
    estimated_count = codes.ne(0).sum().astype(int)
    field_summary = pd.DataFrame({
        "field": facts.columns,
        "observed_count": [int((~original_missing[column]).sum()) for column in facts.columns],
        "original_missing_count": [int(original_missing_count[column]) for column in facts.columns],
        "estimated_or_derived_count": [int(estimated_count[column]) for column in facts.columns],
        "remaining_missing_count": [int(_missing(completed[[column]])[column].sum()) for column in facts.columns],
    })
    summary = {
        "schema_version": COMPLETION_VERSION,
        "universe_count": int(len(facts)),
        "completed_count": int(len(completed)),
        "ranked_count": int(completed["complete_eligible"].sum()),
        "sector_count": int(completed["complete_sector"].nunique()),
        "original_unranked_count": int(formerly_excluded.sum()),
        "resolved_unranked_count": int(len(resolved)),
        "original_unclassified_count": int(facts["product_sector"].isna().sum()),
        "resolved_unclassified_count": int(sectors.notna().sum() - facts["product_sector"].notna().sum()),
        "original_missing_cell_count": int(original_missing.sum().sum()),
        "remaining_missing_cell_count": int(_missing(completed).sum().sum()),
        "estimate_code_cell_count": int(codes.ne(0).sum().sum()),
        "source_field_count": int(len(facts.columns)),
        "completed_output_field_count": int(len(completed.columns)),
        "all_original_missing_cells_coded": original_missing_coded,
        "rank_consistency_error_count": 0,
        "resolved_exclusion_audit_count": int(len(resolved)),
        "all_counts_reconcile": bool(len(facts) == len(completed) == len(rankings)),
        "all_ranked": bool(completed["complete_eligible"].all()),
        "all_sectors_assigned": bool(completed["complete_sector"].notna().all()),
        "observed_snapshot_mutated": False,
        "external_data_accessed": False,
        "outcomes_accessed": False,
    }
    return CompletionResult(
        completed.reset_index(drop=True),
        pd.concat([
            facts[["ticker", "isin"]].reset_index(drop=True),
            codes.rename(columns=lambda column: f"estimate_code__{column}").reset_index(drop=True),
        ], axis=1),
        rankings.reset_index(drop=True), resolved.reset_index(drop=True),
        field_summary, summary,
    )


def validate_completion(root: str | Path) -> dict[str, Any]:
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts", [])
    fingerprint = sha256(json.dumps(
        artifacts, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    if fingerprint != manifest.get("fingerprint"):
        raise ValueError("completion manifest fingerprint mismatch")
    for artifact in artifacts:
        path = root / artifact["path"]
        if (
            not path.is_file()
            or path.stat().st_size != artifact["size"]
            or sha256(path.read_bytes()).hexdigest() != artifact["sha256"]
        ):
            raise ValueError(f"completion artifact changed: {artifact['path']}")
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    if not summary.get("all_ranked") or summary.get("remaining_missing_cell_count") != 0:
        raise ValueError("completion is not complete")
    return summary
