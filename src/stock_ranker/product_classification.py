"""Current-product classification and Baseline coverage expansion.

This module deliberately does not alter the frozen research classifications.
It applies an explicit evidence precedence to the current company-fact view and
uses the unchanged Baseline V1 metric/ranking implementation.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from stock_ranker.config import BaselineConfig
from stock_ranker.ranking import rank_stocks_by_sector


PRODUCT_CLASSIFICATION_VERSION = "product_classification_v2_screener_industry_group"
PRODUCT_BASELINE_METHOD_VERSION = "baseline_v1_equal_rank_mean"

PRODUCT_COLUMNS = (
    "product_classification_version", "product_sector", "product_industry",
    "product_basic_industry", "product_classification_evidence",
    "product_classification_source", "product_classification_as_of",
    "product_baseline_yoy_growth", "product_baseline_cagr_3y",
    "product_baseline_cagr_5y", "product_baseline_days_since_recorded_high",
    "product_baseline_score", "product_baseline_sector_rank",
    "product_baseline_eligible", "product_baseline_reason_code",
    "product_baseline_reason", "product_baseline_ranking_tier",
    "product_baseline_confidence", "product_baseline_feature_count",
    "product_baseline_rank_scope", "product_baseline_method_version",
)

TIER_FEATURES = {
    "PRIMARY_5Y": ("yoy_growth", "cagr_3y", "cagr_5y", "days_since_recorded_high"),
    "REDUCED_3Y": ("yoy_growth", "cagr_3y", "days_since_recorded_high"),
    "REDUCED_1Y": ("yoy_growth", "days_since_recorded_high"),
    "RECENCY_ONLY": ("days_since_recorded_high",),
}
TIER_METADATA = {
    "PRIMARY_5Y": ("PRIMARY", "ELIGIBLE", PRODUCT_BASELINE_METHOD_VERSION),
    "REDUCED_3Y": ("MODERATE", "RANKED_REDUCED_3Y", "baseline_v1_reduced_3y_rank_mean"),
    "REDUCED_1Y": ("LIMITED", "RANKED_REDUCED_1Y", "baseline_v1_reduced_1y_rank_mean"),
    "RECENCY_ONLY": ("MINIMAL", "RANKED_RECENCY_ONLY", "baseline_v1_recency_only"),
}

# The accepted Screener bundle is not used as a replacement ranking source.
# Its independently calculated one-year return is, however, a useful safety
# check for gross-return scale breaks caused by an unreflected split, demerger,
# or cross-provider adjustment mismatch.  A 25% gross-return tolerance is wide
# enough for the small observation-date difference in the current snapshots.
RETURN_REFERENCE_GROSS_RATIO_MIN = 0.8
RETURN_REFERENCE_GROSS_RATIO_MAX = 1.25


def _present(value: Any) -> bool:
    return value is not None and not pd.isna(value) and str(value).strip() != ""


def _one_year_return_reference_conflict(
    row: dict[str, Any], computed_return: Any,
) -> tuple[bool, str]:
    """Detect a material price-basis conflict without substituting vendor data."""

    if str(row.get("screener_current_status")) not in {
        "ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE",
        "ACCEPTED_UNIQUE_EXCHANGE_CODE_CURRENT_REFERENCE",
    }:
        return False, ""
    computed = pd.to_numeric(computed_return, errors="coerce")
    reference_pct = pd.to_numeric(row.get("screener_return_1y_pct"), errors="coerce")
    if pd.isna(computed) or pd.isna(reference_pct):
        return False, ""
    computed_gross = 1.0 + float(computed)
    reference_gross = 1.0 + float(reference_pct) / 100.0
    if computed_gross <= 0 or reference_gross <= 0:
        return False, ""
    ratio = computed_gross / reference_gross
    conflict = not (
        RETURN_REFERENCE_GROSS_RATIO_MIN
        <= ratio
        <= RETURN_REFERENCE_GROSS_RATIO_MAX
    )
    if not conflict:
        return False, ""
    return True, (
        "The ranking history and the accepted exact-identity current reference "
        "imply materially different one-year gross returns "
        f"(ratio {ratio:.6f}, permitted "
        f"{RETURN_REFERENCE_GROSS_RATIO_MIN:.2f}â€“"
        f"{RETURN_REFERENCE_GROSS_RATIO_MAX:.2f}). The value is quarantined "
        "instead of guessing a corporate-action or price basis."
    )


def _select_prior(frame: pd.DataFrame, target: pd.Timestamp, tolerance_days: int = 7) -> pd.Series | None:
    eligible = frame.loc[frame["date"].le(target)].tail(1)
    if eligible.empty or (target - eligible.iloc[0]["date"]).days > tolerance_days:
        return None
    return eligible.iloc[0]


def _secondary_metrics(row: dict[str, Any], history_root: Path) -> tuple[dict[str, Any] | None, str, str]:
    path = history_root / f"{row['ticker']}.csv"
    if not path.is_file():
        return None, "PRICE_HISTORY_UNAVAILABLE", "No accepted adjusted history exists for this exact security identity."
    try:
        frame = pd.read_csv(path, usecols=["date", "adjusted_close"])
    except (OSError, ValueError):
        return None, "PRICE_HISTORY_UNAVAILABLE", "The accepted adjusted-history file is unreadable."
    frame["date"] = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="coerce")
    frame["adjusted_close"] = pd.to_numeric(frame["adjusted_close"], errors="coerce")
    frame = frame.dropna().loc[lambda value: value["adjusted_close"].gt(0)]
    frame = frame.drop_duplicates("date", keep="last").sort_values("date", kind="stable")
    as_of = pd.Timestamp(str(row["trade_date"]))
    frame = frame.loc[frame["date"].le(as_of)]
    if frame.empty:
        return None, "PRICE_HISTORY_UNAVAILABLE", "No accepted adjusted-history observation exists through the trade date."
    selected: dict[str, pd.Series] = {}
    for name, years in (("close_1y", 1), ("close_3y", 3), ("close_5y", 5)):
        target = as_of - pd.DateOffset(years=years)
        observation = _select_prior(frame, target)
        if observation is not None:
            selected[name] = observation
    listing = pd.to_datetime(row.get("listing_date"), format="%Y-%m-%d", errors="coerce")
    high_frame = frame if pd.isna(listing) else frame.loc[frame["date"].ge(listing)]
    if high_frame.empty:
        return None, "RECORDED_HIGH_HISTORY_UNAVAILABLE", "No adjusted history remains after the documented listing boundary."
    terminal = frame.iloc[-1]
    terminal_lag_days = int((as_of - terminal["date"]).days)
    provider_current = float(terminal["adjusted_close"])
    prior_reference = not _present(row.get("latest_price"))
    official_current = float(row["product_price_reference"] if prior_reference else row["latest_price"])
    relative_difference = abs(provider_current - official_current) / official_current
    current = official_current
    current_price_reason = (
        "Accepted exchange current price and exact-identity adjusted history satisfy "
        "the Product Classification v1 continuity gate."
    )
    accepted_screener = str(row.get("screener_current_status")) in {
        "ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE",
        "ACCEPTED_UNIQUE_EXCHANGE_CODE_CURRENT_REFERENCE",
    }
    if terminal_lag_days > 7 or relative_difference > 0.02:
        if prior_reference:
            return None, "CURRENT_PRICE_MISMATCH", (
                "Official prior-trade price is available, but differs from the accepted "
                "adjusted-history terminal by more than 2% or history is stale; "
                "cross-exchange continuity remains unresolved."
            )
        screener_current = pd.to_numeric(row.get("screener_current_price"), errors="coerce")
        if not accepted_screener or pd.isna(screener_current) or float(screener_current) <= 0:
            code = "CURRENT_PRICE_UNAVAILABLE" if terminal_lag_days > 7 else "CURRENT_PRICE_MISMATCH"
            return None, code, (
                "The exact-identity provider history does not supply a current continuity "
                "observation and no accepted Screener Premium current/reference price is available."
            )
        current = float(screener_current)
        current_price_reason = (
            "Provider terminal staleness or exchange-price conflict is retained as provenance; "
            "Screener Premium is authoritative for current/reference price and the "
            "accepted exact-identity adjusted history supplies historical anchors."
        )
    maximum = max(float(high_frame["adjusted_close"].max()), current)
    if current >= float(high_frame["adjusted_close"].max()):
        high_date = pd.Timestamp(row['product_price_date']) if prior_reference else as_of
    else:
        high_date = high_frame.loc[high_frame["adjusted_close"].eq(maximum)].iloc[-1]["date"]
    if prior_reference:
        current_price_reason = (
            f"Official {row['product_price_exchange']} prior-trade price from {row['product_price_date']}; "
            "historical anchors retain the snapshot date and existing continuity rules."
        )
    metrics = {
        "ticker": str(row["ticker"]), "company": str(row["company"]),
        "sector": str(row["product_sector"]), "as_of_date": as_of,
        "current_price": current,
        "close_1y_ago": float(selected["close_1y"]["adjusted_close"]) if "close_1y" in selected else None,
        "close_3y_ago": float(selected["close_3y"]["adjusted_close"]) if "close_3y" in selected else None,
        "close_5y_ago": float(selected["close_5y"]["adjusted_close"]) if "close_5y" in selected else None,
        "ath_date": high_date,
        "yoy_growth": current / float(selected["close_1y"]["adjusted_close"]) - 1 if "close_1y" in selected else None,
        "cagr_3y": (current / float(selected["close_3y"]["adjusted_close"])) ** (1 / 3) - 1 if "close_3y" in selected else None,
        "cagr_5y": (current / float(selected["close_5y"]["adjusted_close"])) ** (1 / 5) - 1 if "close_5y" in selected else None,
        "days_since_recorded_high": int((as_of - high_date).days),
    }
    if all(name in selected for name in ("close_1y", "close_3y", "close_5y")):
        tier = "PRIMARY_5Y"
    elif all(name in selected for name in ("close_1y", "close_3y")):
        tier = "REDUCED_3Y"
    elif "close_1y" in selected:
        tier = "REDUCED_1Y"
    else:
        history_days = int((frame.iloc[-1]["date"] - frame.iloc[0]["date"]).days)
        if len(frame) < 20 or history_days < 30:
            return None, "INSUFFICIENT_RANKING_HISTORY", (
                "Fewer than 20 accepted observations or 30 calendar days exist; even a "
                "recency-only ranking would be unsupported."
            )
        tier = "RECENCY_ONLY"
    confidence, code, method = TIER_METADATA[tier]
    metrics.update({"ranking_tier": tier, "confidence": confidence, "method_version": method})
    return metrics, code, current_price_reason


def _rank_tier(metrics: pd.DataFrame, tier: str) -> pd.DataFrame:
    """Rank one evidence tier without allowing lower-coverage rows to alter primary ranks."""

    selected = metrics.loc[metrics["ranking_tier"].eq(tier)].copy()
    if selected.empty:
        return selected
    if tier == "PRIMARY_5Y":
        canonical = rank_stocks_by_sector(
            selected, BaselineConfig(method_version=PRODUCT_BASELINE_METHOD_VERSION)
        )
        canonical["ranking_tier"] = tier
        canonical["confidence"] = "PRIMARY"
        return canonical
    rank_columns: list[str] = []
    for feature in TIER_FEATURES[tier]:
        rank_name = f"_{feature}_rank"
        selected[rank_name] = selected.groupby("sector", sort=False)[feature].rank(
            ascending=feature == "days_since_recorded_high", method="min"
        )
        rank_columns.append(rank_name)
    selected["baseline_score"] = selected[rank_columns].mean(axis=1)
    selected["sector_rank"] = selected.groupby("sector", sort=False)["baseline_score"].rank(
        ascending=True, method="min"
    ).astype("int64")
    return selected


def add_product_classification_and_baseline(
    facts: pd.DataFrame,
    *,
    history_root: str | Path,
) -> pd.DataFrame:
    """Add current-product grouping and rankings while preserving frozen fields."""

    result = facts.copy()
    for column in PRODUCT_COLUMNS:
        result[column] = None
    result["product_classification_version"] = PRODUCT_CLASSIFICATION_VERSION
    has_screener_contract = "screener_current_status" in facts.columns
    metric_rows: list[dict[str, Any]] = []
    reasons: dict[str, tuple[str, str]] = {}
    for index, source in result.iterrows():
        ticker = str(source["ticker"])
        official = _present(source.get("official_sector"))
        screener_status = str(source.get("screener_current_status"))
        screener_secondary = (
            screener_status in {
                "ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE",
                "ACCEPTED_UNIQUE_EXCHANGE_CODE_CURRENT_REFERENCE",
            }
            and _present(source.get("screener_industry_group"))
        )
        # Use one coherent current-product taxonomy. Mixing official broad
        # sectors, Yahoo sectors and Screener industry groups split a single
        # Screener sector into several tiny peer pools. Source columns remain
        # intact for provenance and frozen research remains untouched.
        if screener_secondary:
            result.at[index, "product_sector"] = source["screener_industry_group"]
            result.at[index, "product_industry"] = source.get("screener_industry")
            result.at[index, "product_basic_industry"] = source.get("official_basic_industry")
            result.at[index, "product_classification_evidence"] = (
                "EXACT_ISIN_SCREENER_CURRENT_REFERENCE"
                if screener_status == "ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE"
                else "UNIQUE_EXCHANGE_CODE_SCREENER_CURRENT_REFERENCE"
            )
            result.at[index, "product_classification_source"] = "Accepted Screener market-wide sector export"
            result.at[index, "product_classification_as_of"] = source.get("screener_source_observed_at")
        elif not has_screener_contract and official:
            # Compatibility for isolated callers/fixtures that predate the
            # accepted Screener provider contract. Production company facts
            # always contain that contract and therefore never mix taxonomies.
            result.at[index, "product_sector"] = source["official_sector"]
            result.at[index, "product_industry"] = source.get("official_industry")
            result.at[index, "product_basic_industry"] = source.get("official_basic_industry")
            result.at[index, "product_classification_evidence"] = "OFFICIAL"
            result.at[index, "product_classification_source"] = source.get("official_classification_source")
            result.at[index, "product_classification_as_of"] = source.get("trade_date")
        elif (
            not has_screener_contract
            and str(source.get("secondary_identity_status")) == "EXCHANGE_SYMBOL_MATCH"
            and _present(source.get("secondary_sector"))
        ):
            result.at[index, "product_sector"] = source["secondary_sector"]
            result.at[index, "product_industry"] = source.get("secondary_industry")
            result.at[index, "product_classification_evidence"] = "EXACT_IDENTITY_SECONDARY_REFERENCE"
            result.at[index, "product_classification_source"] = source.get("secondary_source")
            result.at[index, "product_classification_as_of"] = source.get("secondary_source_as_of")
        elif (
            not has_screener_contract
            and str(source.get("bulk_classification_status")) == "ACCEPTED"
            and _present(source.get("bulk_classification_sector"))
        ):
            result.at[index, "product_sector"] = source["bulk_classification_sector"]
            result.at[index, "product_industry"] = source.get("bulk_classification_industry")
            result.at[index, "product_classification_evidence"] = "EXACT_IDENTITY_SECONDARY_REFERENCE"
            result.at[index, "product_classification_source"] = source.get("bulk_classification_source")
            result.at[index, "product_classification_as_of"] = source.get("bulk_classification_retrieved_at")
        else:
            result.at[index, "product_classification_evidence"] = "UNCLASSIFIED"
            reasons[ticker] = (
                "UNCLASSIFIED",
                "No accepted Screener industry-group value exists for this exact identity. "
                "Other classification fields remain available as provenance but are not mixed "
                "into the current-product peer taxonomy.",
            )
            continue

        row = result.loc[index].to_dict()
        if not _present(row.get("latest_price")):
            if row.get("product_price_status") == "OFFICIAL_PRIOR_TRADE" and _present(row.get("product_price_reference")):
                metrics, code, reason = _secondary_metrics(row, Path(history_root))
                reasons[ticker] = (code, reason)
                if metrics is not None:
                    metric_rows.append(metrics)
            elif row.get("product_price_status") == "OFFICIAL_LAST_TRADE_STALE":
                reasons[ticker] = ("CURRENT_PRICE_STALE", f"Last verified official trade is {row.get('product_price_date')}; outside the existing seven-day continuity window.")
            elif row.get("product_price_status") == "OFFICIAL_PRIOR_TRADE_ACTION_REVIEW_REQUIRED":
                reasons[ticker] = ("CURRENT_PRICE_ACTION_REVIEW_REQUIRED", "An official corporate action follows the last verified trade; its price basis requires review.")
            else:
                reasons[ticker] = ("PRICE_UNAVAILABLE", "No accepted current exchange price exists.")
            continue
        frozen_metrics = (
            "baseline_yoy_growth", "baseline_cagr_3y", "baseline_cagr_5y",
            "baseline_days_since_recorded_high",
        )
        if official and bool(row.get("baseline_eligible")) and all(_present(row.get(name)) for name in frozen_metrics):
            metric_rows.append({
                "ticker": ticker, "company": str(row["company"]),
                "sector": str(row["product_sector"]), "as_of_date": pd.Timestamp(str(row["trade_date"])),
                "current_price": float(row["latest_price"]), "close_1y_ago": 1.0,
                "close_3y_ago": 1.0, "close_5y_ago": 1.0,
                "ath_date": pd.Timestamp(str(row["trade_date"])) - pd.Timedelta(days=int(row["baseline_days_since_recorded_high"])),
                "yoy_growth": float(row["baseline_yoy_growth"]),
                "cagr_3y": float(row["baseline_cagr_3y"]),
                "cagr_5y": float(row["baseline_cagr_5y"]),
                "days_since_recorded_high": int(row["baseline_days_since_recorded_high"]),
                "ranking_tier": "PRIMARY_5Y", "confidence": "PRIMARY",
                "method_version": PRODUCT_BASELINE_METHOD_VERSION,
            })
            reasons[ticker] = ("ELIGIBLE", "Accepted official classification and frozen current Baseline inputs are reused unchanged.")
        elif official and bool(row.get("baseline_eligible")):
            reasons[ticker] = ("BASELINE_METRICS_UNAVAILABLE", "The source row is eligible but does not expose its canonical metric inputs.")
        elif official and str(row.get("baseline_reason_code")) == "CURRENT_PRICE_MISMATCH":
            metrics, code, reason = _secondary_metrics(row, Path(history_root))
            reasons[ticker] = (code, reason)
            if metrics is not None:
                metric_rows.append(metrics)
        else:
            metrics, code, reason = _secondary_metrics(row, Path(history_root))
            reasons[ticker] = (code, reason)
            if metrics is not None:
                metric_rows.append(metrics)

    if metric_rows:
        metrics = pd.DataFrame(metric_rows)
        # Apply the independent return-scale safety gate to every route,
        # including official-sector rows that reuse the frozen Baseline inputs.
        # The reference return never replaces a model input; it can only stop an
        # unsafe row from entering a peer ranking.
        safe_rows: list[dict[str, Any]] = []
        result_by_ticker = result.set_index(result["ticker"].astype(str), drop=False)
        for metric in metric_rows:
            ticker = str(metric["ticker"])
            source = result_by_ticker.loc[ticker].to_dict()
            conflict, conflict_reason = _one_year_return_reference_conflict(
                source, metric.get("yoy_growth")
            )
            if conflict:
                reasons[ticker] = (
                    "ONE_YEAR_RETURN_REFERENCE_CONFLICT", conflict_reason,
                )
            else:
                safe_rows.append(metric)
        metrics = pd.DataFrame(safe_rows)
    if metric_rows and not metrics.empty:
        ranked = pd.concat(
            [_rank_tier(metrics, tier) for tier in TIER_FEATURES], ignore_index=True
        )
        by_ticker = ranked.set_index("ticker")
        for index, ticker in result["ticker"].astype(str).items():
            if ticker not in by_ticker.index:
                continue
            ranked_row = by_ticker.loc[ticker]
            for target, source in (
                ("product_baseline_yoy_growth", "yoy_growth"),
                ("product_baseline_cagr_3y", "cagr_3y"),
                ("product_baseline_cagr_5y", "cagr_5y"),
                ("product_baseline_days_since_recorded_high", "days_since_recorded_high"),
                ("product_baseline_score", "baseline_score"),
                ("product_baseline_sector_rank", "sector_rank"),
                ("product_baseline_ranking_tier", "ranking_tier"),
                ("product_baseline_confidence", "confidence"),
                ("product_baseline_method_version", "method_version"),
            ):
                result.at[index, target] = ranked_row[source]
            result.at[index, "product_baseline_feature_count"] = len(TIER_FEATURES[str(ranked_row["ranking_tier"])])
            result.at[index, "product_baseline_rank_scope"] = "sector_within_evidence_tier"
    for index, ticker in result["ticker"].astype(str).items():
        code, reason = reasons[ticker]
        result.at[index, "product_baseline_reason_code"] = code
        result.at[index, "product_baseline_reason"] = reason
        result.at[index, "product_baseline_eligible"] = code in {item[1] for item in TIER_METADATA.values()}
    result["product_baseline_eligible"] = result["product_baseline_eligible"].astype(bool)
    return result
