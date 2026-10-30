"""Build the research-only personalized history data-quality enrichment.

This runner never mutates accepted market state, the frozen personalized champion,
or production serving files. It combines the accepted history cache with a
validated recovery overlay and keeps observed and estimated values explicitly
separate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.company_facts import load_company_fact_snapshot
from stock_ranker.history_enrichment import build_current_history_enrichment
from stock_ranker.runtime import validated_release

CUTOFF = "2026-09-18"
PRIMARY = ROOT / "data/live_market/history_cache"
RECOVERY = ROOT / "experiments/history-enrichment-20261002/recovery_overlay_frozen_v1"
RAW_BSE_RISK = ROOT / "experiments/history-enrichment-20261002/bse_api_recovery_frozen_v1/raw"
BSE_AUDIT = ROOT / "experiments/history-enrichment-20261002/bse_adjusted_recovery_frozen_v1_audit/per_code_decision.csv"
DEFAULT_OUTPUT = ROOT / "experiments/history-enrichment-20261002/final-data-quality-v1"

METRICS = (
    "history_months", "strict_cagr_1y", "strict_cagr_3y", "strict_cagr_5y",
    "long_term_growth_value", "recorded_high_price", "days_since_recorded_high",
    "distance_from_recorded_high", "distance_from_52w_high",
    "full_history_max_drawdown", "current_drawdown_duration_days",
    "max_drawdown_duration_days", "recovery_from_worst_trough",
    "realized_volatility_1y", "downside_volatility_1y",
    "realized_volatility_1y_value", "downside_volatility_1y_value",
)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dir_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.glob("*.csv") if p.is_file()):
        digest.update(path.name.encode("utf-8"))
        digest.update(_sha(path).encode("ascii"))
    return digest.hexdigest()


def _coverage(frame: pd.DataFrame) -> dict[str, int]:
    return {
        metric: int(pd.to_numeric(frame.get(metric), errors="coerce").notna().sum())
        for metric in METRICS
    }


def _summary(frame: pd.DataFrame) -> dict:
    quality = frame["history_quality"].value_counts(dropna=False).to_dict()
    sources = frame["history_source"].value_counts(dropna=False).to_dict()
    growth = frame["long_term_growth_source"].value_counts(dropna=False).to_dict()
    return {
        "rows": int(len(frame)),
        "history_source_counts": {str(k): int(v) for k, v in sources.items()},
        "history_quality_counts": {str(k): int(v) for k, v in quality.items()},
        "long_term_growth_source_counts": {str(k): int(v) for k, v in growth.items()},
        "true_5y_count": int(frame["long_term_growth_is_observed"].fillna(False).astype(bool).sum()),
        "estimated_5y_count": int((~frame["long_term_growth_is_observed"].fillna(False).astype(bool)).sum()),
        "no_valid_history_count": int(frame["history_quality"].eq("MISSING").sum()),
        "invalid_history_count": int(frame["history_quality"].eq("INVALID").sum()),
        "raw_risk_only_count": int(frame["history_quality"].eq("RAW_RISK_ONLY").sum()),
        "adjusted_history_unavailable_count": int((~frame["adjusted_history_available"].fillna(False).astype(bool)).sum()),
        "coverage": _coverage(frame),
    }


def run(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    release = validated_release()
    fact_root = ROOT / "data/company_facts/snapshots" / (
        "2026-09-18-" + release["accepted_company_fingerprint"]
    )
    facts_bundle = load_company_fact_snapshot(fact_root)
    if facts_bundle.manifest.get("fingerprint") != release["accepted_company_fingerprint"]:
        raise ValueError("accepted company-fact fingerprint mismatch")
    facts = facts_bundle.facts.copy()

    before = build_current_history_enrichment(
        facts, primary_root=PRIMARY, recovery_root=None, cutoff=CUTOFF
    )
    after = build_current_history_enrichment(
        facts,
        primary_root=PRIMARY,
        recovery_root=RECOVERY,
        cutoff=CUTOFF,
        raw_risk_root=RAW_BSE_RISK,
    )

    before_summary = _summary(before)
    after_summary = _summary(after)

    after.to_csv(output / "history_enrichment.csv.gz", index=False, compression="gzip")
    remaining = after.loc[after["history_quality"].isin(["MISSING", "INVALID"])].copy()
    remaining.to_csv(output / "remaining_no_history.csv", index=False)

    quarantine = pd.read_csv(BSE_AUDIT) if BSE_AUDIT.is_file() else pd.DataFrame()
    if not quarantine.empty:
        quarantine = quarantine.loc[quarantine["status"].eq("QUARANTINED")].copy()
    quarantine.to_csv(output / "quarantined_bse_history.csv", index=False)

    coverage_rows = []
    for metric in METRICS:
        coverage_rows.append({
            "metric": metric,
            "before_present": before_summary["coverage"][metric],
            "after_present": after_summary["coverage"][metric],
            "delta_present": after_summary["coverage"][metric] - before_summary["coverage"][metric],
            "after_missing": len(after) - after_summary["coverage"][metric],
        })
    pd.DataFrame(coverage_rows).to_csv(output / "coverage_before_after.csv", index=False)

    listing = pd.to_datetime(facts.get("listing_date"), errors="coerce")
    exchange = facts.get("primary_exchange", pd.Series("UNKNOWN", index=facts.index)).fillna("UNKNOWN")
    listing_by_exchange = (
        pd.DataFrame({"exchange": exchange, "listing_date_present": listing.notna()})
        .groupby("exchange", dropna=False)["listing_date_present"]
        .agg(["count", "sum"])
        .reset_index()
        .rename(columns={"sum": "present"})
    )
    listing_by_exchange["missing"] = listing_by_exchange["count"] - listing_by_exchange["present"]
    listing_by_exchange.to_csv(output / "listing_date_coverage.csv", index=False)

    nykaa = after.loc[after["ticker"].eq("NYKAA")]
    nykaa_record = nykaa.iloc[0].to_dict() if len(nykaa) else None

    summary = {
        "schema_version": "personalized_history_data_quality_v1",
        "cutoff": CUTOFF,
        "accepted_state_mutated": False,
        "frozen_champion_mutated": False,
        "production_mutated": False,
        "company_fact_fingerprint": facts_bundle.manifest.get("fingerprint"),
        "before": before_summary,
        "after": after_summary,
        "delta": {
            "no_valid_history": after_summary["no_valid_history_count"] - before_summary["no_valid_history_count"],
            "invalid_history": after_summary["invalid_history_count"] - before_summary["invalid_history_count"],
            "raw_risk_only": after_summary["raw_risk_only_count"] - before_summary["raw_risk_only_count"],
            "adjusted_history_unavailable": after_summary["adjusted_history_unavailable_count"] - before_summary["adjusted_history_unavailable_count"],
            "true_5y": after_summary["true_5y_count"] - before_summary["true_5y_count"],
        },
        "listing_date": {
            "present": int(listing.notna().sum()),
            "missing": int(listing.isna().sum()),
            "note": (
                "history_months is observed price-history span, not listing age. "
                "The official BSE ListofScripData_new endpoint does not expose listing date, "
                "so missing BSE listing dates are not fabricated."
            ),
        },
        "remaining_quarantined_bse_count": int(len(quarantine)),
        "nykaa": nykaa_record,
        "source_fingerprints": {
            "history_enrichment_module": _sha(ROOT / "src/stock_ranker/history_enrichment.py"),
            "recovery_overlay": _dir_fingerprint(RECOVERY),
            "bse_quarantine_audit": _sha(BSE_AUDIT) if BSE_AUDIT.is_file() else None,
        },
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    print(json.dumps({
        "rows": after_summary["rows"],
        "before_no_history": before_summary["no_valid_history_count"],
        "after_no_history": after_summary["no_valid_history_count"],
        "after_invalid": after_summary["invalid_history_count"],
        "raw_risk_only": after_summary["raw_risk_only_count"],
        "adjusted_history_unavailable": after_summary["adjusted_history_unavailable_count"],
        "true_5y": after_summary["true_5y_count"],
        "estimated_5y": after_summary["estimated_5y_count"],
        "long_term_growth_present": after_summary["coverage"]["long_term_growth_value"],
        "full_history_drawdown_present": after_summary["coverage"]["full_history_max_drawdown"],
        "days_since_high_present": after_summary["coverage"]["days_since_recorded_high"],
        "volatility_present": after_summary["coverage"]["realized_volatility_1y"],
        "remaining_quarantined_bse": len(quarantine),
        "listing_date_present": int(listing.notna().sum()),
        "listing_date_missing": int(listing.isna().sum()),
    }, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.output)
