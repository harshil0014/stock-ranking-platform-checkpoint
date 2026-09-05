"""Explain differences between strict live and expanded product Baseline cohorts."""

from __future__ import annotations

import pandas as pd


def audit_baseline_eligibility(
    earlier_live: pd.DataFrame,
    current_live: pd.DataFrame,
    current_company_facts: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Return a security-level reconciliation without changing eligibility.

    The live bundle is the official-classification/strict terminal-price cohort.
    Company facts contains the separately versioned expanded product cohort.
    """

    required_live = {"ticker", "baseline_eligible", "baseline_reason_code"}
    required_facts = {
        "ticker", "product_baseline_eligible", "product_baseline_reason_code",
        "product_classification_evidence",
    }
    for label, frame, required in (
        ("earlier_live", earlier_live, required_live),
        ("current_live", current_live, required_live),
        ("current_company_facts", current_company_facts, required_facts),
    ):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"{label} missing columns: {missing}")
        if frame["ticker"].duplicated().any():
            raise ValueError(f"{label} contains duplicate tickers")

    old = earlier_live.set_index("ticker")
    new = current_live.set_index("ticker")
    facts = current_company_facts.set_index("ticker")
    old_set = set(old.index[old["baseline_eligible"].astype(bool)])
    strict_set = set(new.index[new["baseline_eligible"].astype(bool)])
    product_set = set(facts.index[facts["product_baseline_eligible"].astype(bool)])
    tickers = sorted(old_set | strict_set | product_set)
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        rows.append({
            "ticker": ticker,
            "earlier_strict_eligible": ticker in old_set,
            "current_strict_eligible": ticker in strict_set,
            "current_product_eligible": ticker in product_set,
            "current_strict_reason_code": new.at[ticker, "baseline_reason_code"] if ticker in new.index else "NOT_IN_STRICT_UNIVERSE",
            "current_product_reason_code": facts.at[ticker, "product_baseline_reason_code"] if ticker in facts.index else "NOT_IN_PRODUCT_UNIVERSE",
            "product_classification_evidence": facts.at[ticker, "product_classification_evidence"] if ticker in facts.index else "",
        })
    detail = pd.DataFrame(rows)
    lost = old_set - strict_set
    gained = strict_set - old_set
    product_only = product_set - strict_set
    evidence_counts = (
        facts.loc[sorted(product_only), "product_classification_evidence"].value_counts().sort_index().to_dict()
        if product_only else {}
    )
    reason_counts = (
        new.loc[sorted(lost), "baseline_reason_code"].value_counts().sort_index().to_dict()
        if lost else {}
    )
    summary: dict[str, object] = {
        "earlier_strict_eligible": len(old_set),
        "current_strict_eligible": len(strict_set),
        "current_product_eligible": len(product_set),
        "strict_product_overlap": len(strict_set & product_set),
        "product_only": len(product_only),
        "strict_only": len(strict_set - product_set),
        "earlier_to_current_strict_lost": len(lost),
        "earlier_to_current_strict_gained": len(gained),
        "lost_reason_counts": reason_counts,
        "product_only_classification_evidence_counts": evidence_counts,
        "interpretation": (
            "The strict live and expanded product Baseline cohorts are different, explicitly "
            "versioned eligibility views; their counts must not be presented as a temporal drop."
        ),
    }
    return detail, summary
