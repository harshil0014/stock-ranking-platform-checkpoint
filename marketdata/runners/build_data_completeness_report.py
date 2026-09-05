"""Build deterministic coverage, professor-cohort and Screener-parity reports."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot  # noqa: E402
from stock_ranker.data_state import atomic_write_json  # noqa: E402
from stock_ranker.secondary_facts import load_yahoo_secondary_bundle  # noqa: E402
from stock_ranker.exchange_backbone import audit_derived_classifications  # noqa: E402


BEFORE = {
    "identity": 5093, "current_price": 5092, "classification": 750,
    "derived_classification": 257,
    "company_profile": 573, "market_cap": 542, "high_low_52w": 576,
    "annual_financials": 593, "quarterly_financials": 564, "balance_sheet": 571,
    "cash_flow": 571, "shares_outstanding": 542, "pe": 512, "pb": 565, "eps": 571,
    "book_value": 565, "dividend_yield": 575, "roe": 64, "roce": 34,
    "debt_to_equity": 34, "profit_growth": 34, "revenue_growth": 0,
    "shareholding": 0, "annual_report_links": 46, "corporate_actions": 450,
    "history_1y": 2150, "history_3y": 1883, "history_5y": 1676,
    "baseline_eligible": 568, "strict_v2_eligible": 34,
}

OFFICIAL_FIELDS = {
    "annual_financials": "official_annual_period_end",
    "quarterly_financials": "official_quarterly_period_end",
    "balance_sheet": "official_balance_period_end",
    "cash_flow": "official_cash_flow_period_end",
    "shareholding": "shareholding_as_of",
    "documents": "latest_document_url",
    "market_cap": "official_market_cap",
    "pe": "official_pe_ratio",
    "pb": "official_pb_ratio",
    "roe": "official_return_on_equity",
    "debt_to_equity": "official_debt_to_equity",
    "revenue_growth": "official_revenue_growth",
    "profit_growth": "official_profit_growth_yoy",
}

SECONDARY_FIELDS = {
    "company_profile": "company_profile", "market_cap": "market_cap",
    "high_low_52w": "secondary_high_52w", "annual_financials": "secondary_annual_period_end",
    "quarterly_financials": "secondary_quarterly_period_end",
    "balance_sheet": "secondary_balance_period_end", "cash_flow": "secondary_cash_flow_period_end",
    "pe": "pe_ratio", "pb": "pb_ratio", "eps": "trailing_eps",
    "dividend_yield": "dividend_yield", "roe": "return_on_equity",
    "debt_to_equity": "secondary_debt_to_equity", "revenue_growth": "revenue_growth",
    "profit_growth": "secondary_profit_growth",
}


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _cohort_rows(facts: pd.DataFrame, professor: pd.DataFrame) -> dict[str, pd.DataFrame]:
    professor_isins = set(professor["isin"].dropna().astype(str))
    ranked_isins = set(professor.loc[professor["reference_rank"].notna(), "isin"].dropna().astype(str))
    return {
        "FULL_UNIVERSE": facts,
        "NSE": facts.loc[facts["primary_exchange"].eq("NSE")],
        "BSE_ONLY": facts.loc[facts["primary_exchange"].eq("BSE")],
        "PROFESSOR_COHORT": facts.loc[facts["isin"].astype(str).isin(professor_isins)],
        "RANKED_PROFESSOR_14": facts.loc[facts["isin"].astype(str).isin(ranked_isins)],
    }


def _coverage_rows(cohorts: dict[str, pd.DataFrame]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cohort_name, cohort in cohorts.items():
        denominator = len(cohort)
        for evidence, mapping in (("PRIMARY_VERIFIED", OFFICIAL_FIELDS), ("SECONDARY_REFERENCE", SECONDARY_FIELDS)):
            for field, column in mapping.items():
                count = int(cohort[column].notna().sum()) if column in cohort else 0
                rows.append({"cohort": cohort_name, "evidence_class": evidence, "field": field,
                             "count": count, "denominator": denominator,
                             "percent": round(100 * count / denominator, 4) if denominator else 0.0})
        state_counts = cohort["classification_evidence_status"].value_counts()
        for state in ("OFFICIAL", "DERIVED_PRIMARY_EVIDENCE", "DERIVED_SECONDARY_REFERENCE_ONLY", "UNCLASSIFIED"):
            count = int(state_counts.get(state, 0))
            rows.append({"cohort": cohort_name, "evidence_class": state, "field": "classification",
                         "count": count, "denominator": denominator,
                         "percent": round(100 * count / denominator, 4) if denominator else 0.0})
    return rows


FIELD_MAP = {
    "identity": ("ticker",), "current_price": ("latest_price",),
    "classification": ("official_sector",), "company_profile": ("company_profile",),
    "derived_classification": ("derived_research_sector",),
    "market_cap": ("market_cap",), "high_low_52w": ("secondary_high_52w", "secondary_low_52w"),
    "annual_financials": ("secondary_annual_period_end",),
    "quarterly_financials": ("secondary_quarterly_period_end",),
    "balance_sheet": ("secondary_balance_period_end",), "cash_flow": ("secondary_cash_flow_period_end",),
    "shares_outstanding": ("shares_outstanding",), "pe": ("pe_ratio",), "pb": ("pb_ratio",),
    "eps": ("trailing_eps",), "book_value": ("book_value",), "dividend_yield": ("dividend_yield",),
    "roe": ("return_on_equity",), "roce": ("roce",), "debt_to_equity": ("debt_to_equity",),
    "profit_growth": ("profit_growth_yoy",), "revenue_growth": ("revenue_growth",),
    "annual_report_links": ("annual_report_source_url",),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build measured completeness and parity reports.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/company_facts/reports/current")
    parser.add_argument("--professor", type=Path, default=ROOT / "data/professor_reference/strategy_current/professor_strategy_comparison.csv")
    args = parser.parse_args(argv)
    facts_result = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts"))
    facts = facts_result.facts
    yahoo_state = json.loads((ROOT / "data/company_facts/providers/yahoo/accepted_state.json").read_text(encoding="utf-8"))
    yahoo = load_yahoo_secondary_bundle(ROOT / "data/company_facts/providers/yahoo" / yahoo_state["accepted_batch"])
    after: dict[str, int] = {}
    for name, columns in FIELD_MAP.items():
        after[name] = int(facts[list(columns)].notna().all(axis=1).sum())
    measured = facts_result.coverage["metrics"]
    coverage_names = {
        "annual_financials": "annual_financials", "quarterly_financials": "quarterly_financials",
        "balance_sheet": "balance_sheet", "cash_flow": "cash_flow",
        "shareholding": "shareholding", "corporate_actions": "corporate_actions",
        "annual_report_links": "annual_report_or_document_link",
        "history_1y": "history_1y", "history_3y": "history_3y", "history_5y": "history_5y",
        "baseline_eligible": "baseline_eligible", "strict_v2_eligible": "strict_v2_eligible",
    }
    after.update({target: int(measured[source]["count"]) for target, source in coverage_names.items()})
    professor = pd.read_csv(args.professor, low_memory=False)
    cohorts = _cohort_rows(facts, professor)
    selected = ["isin", "ticker", "company", "primary_exchange", "secondary_identity_status",
                "official_sector", "company_profile", "market_cap", "history_1y_usable",
                "history_3y_usable", "history_5y_usable", "quarterly_results_status",
                "balance_sheet_status", "cash_flow_status", "shareholding_status",
                "corporate_actions_status", "annual_report_status", "baseline_eligible",
                "baseline_reason_code", "v2_eligible", "v2_reason_code"]
    cohort = professor.merge(facts[selected], on="isin", how="left", validate="many_to_one")
    cohort["exact_missing_reason"] = cohort.apply(
        lambda row: "OUTSIDE_CURRENT_SUPPORTED_STATE" if pd.isna(row.get("ticker")) else
        (str(row.get("v2_reason_code")) if not bool(row.get("v2_eligible")) else
         (str(row.get("baseline_reason_code")) if not bool(row.get("baseline_eligible")) else "NONE")), axis=1,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cohort.sort_values(["reference_rank", "requested_code"], na_position="last", kind="stable").to_csv(
        args.output_dir / "professor_cohort_completeness.csv", index=False, encoding="utf-8",
        lineterminator="\n", float_format="%.17g",
    )
    parity = {
        "schema_version": "screener_parity_matrix_v1", "screener_acquisition": "POLICY_DISABLED",
        "benchmark_role": "field-category checklist only", "universe_count": len(facts),
        "fields": [{"field": key, "before": BEFORE.get(key, 0), "after": value,
                    "canonical_source": "official/accepted evidence with secondary reference fallback",
                    "parity_status": "AVAILABLE" if value == len(facts) else "PARTIAL" if value else "NOT_IMPLEMENTED"}
                   for key, value in sorted(after.items())],
        "yahoo_benchmark": yahoo.manifest["coverage"],
        "fact_fingerprint": facts_result.manifest["fingerprint"],
        "market_fingerprint": facts_result.manifest["market_fingerprint"],
        "scientific_models_unchanged": True,
    }
    atomic_write_json(args.output_dir / "screener_parity_matrix_v1.json", parity)
    coverage_rows = pd.DataFrame(_coverage_rows(cohorts))
    coverage_rows.to_csv(args.output_dir / "primary_secondary_coverage.csv", index=False,
                         encoding="utf-8", lineterminator="\n", float_format="%.17g")
    classification_audit = audit_derived_classifications(facts)
    classification_audit.to_csv(args.output_dir / "classification_audit_current.csv", index=False,
                                encoding="utf-8", lineterminator="\n")
    classification_audit.loc[classification_audit["confidence_status"].isin([
        "DERIVED_PRIMARY_EVIDENCE", "DERIVED_SECONDARY_REFERENCE_ONLY"
    ])].to_csv(args.output_dir / "derived_classification_audit.csv", index=False,
              encoding="utf-8", lineterminator="\n")
    waterfall = (facts.groupby(["primary_exchange", "baseline_reason_code"], dropna=False)
                 .size().rename("count").reset_index()
                 .sort_values(["primary_exchange", "count", "baseline_reason_code"],
                              ascending=[True, False, True], kind="stable"))
    waterfall.to_csv(args.output_dir / "baseline_exclusion_waterfall.csv", index=False,
                     encoding="utf-8", lineterminator="\n")

    official_state = json.loads((ROOT / "data/company_facts/providers/official_exchange/accepted_state.json").read_text(encoding="utf-8"))
    official_root = ROOT / "data/company_facts/providers/official_exchange" / official_state["accepted_batch"]
    raw_inventory = []
    for path in sorted((official_root / "raw").rglob("*")):
        if path.is_file():
            raw_inventory.append({"relative_path": path.relative_to(official_root).as_posix(),
                                  "size": path.stat().st_size, "sha256": _hash_file(path),
                                  "retained": True})
    pd.DataFrame(raw_inventory).to_csv(args.output_dir / "official_raw_evidence_inventory.csv",
                                       index=False, encoding="utf-8", lineterminator="\n")
    official_manifest = json.loads((official_root / "manifest.json").read_text(encoding="utf-8"))
    acceptance = {
        "schema_version": "official_exchange_acceptance_v1",
        "official_backbone_batch": official_state["accepted_batch"],
        "official_backbone_fingerprint": official_manifest["fingerprint"],
        "company_fact_fingerprint": facts_result.manifest["fingerprint"],
        "market_fingerprint": facts_result.manifest["market_fingerprint"],
        "catalogue_counts": official_manifest["catalogue_counts"],
        "normalized_counts": official_manifest["normalized_counts"],
        "xbrl": official_manifest["xbrl"],
        "bse_shareholding": official_manifest["bse_shareholding"],
        "classification_audit": official_manifest["classification_audit"],
        "current_classification_audit": {
            str(key): int(value) for key, value in
            classification_audit["confidence_status"].value_counts().sort_index().items()
        },
        "raw_evidence_file_count": len(raw_inventory),
        "baseline_exclusions": waterfall.to_dict("records"),
        "scientific_models_unchanged": True,
    }
    atomic_write_json(args.output_dir / "official_exchange_acceptance.json", acceptance)
    summary = {
        "before": BEFORE, "after": after, "universe_count": len(facts),
        "professor_requests": len(cohort), "professor_supported": int(cohort["ticker"].notna().sum()),
        "ranked_14_supported": int(cohort.loc[cohort["reference_rank"].notna(), "ticker"].notna().sum()),
        "yahoo_fingerprint": yahoo.manifest["fingerprint"],
        "fact_fingerprint": facts_result.manifest["fingerprint"],
        "official_backbone_fingerprint": official_manifest["fingerprint"],
    }
    atomic_write_json(args.output_dir / "screening_summary.json", summary)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
