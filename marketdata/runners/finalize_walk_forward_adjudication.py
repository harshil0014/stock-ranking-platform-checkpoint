"""Finalize reviewed 2024/2025 filing packets and the declarative mapping."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAPPING = ROOT / "marketdata/specifications/walk_forward_annual_report_mapping.json"
GENERATED = ROOT / "data/walk_forward"

# ticker: ROCE decimal/page, debt-equity decimal/page, PAT current/prior/page, unit, warning
DECISIONS = {
    "2025-08-07": {
        "ADANIENT": (.1421, 374, .47, 373, 6040.23, 2844.26, 288, "INR crore", "Includes discontinued operations and an exceptional gain; no normalization applied."),
        "ADANIPORTS": (.0815, 407, 1.69, 407, 2457.15, 1738.35, 342, "INR crore", ""),
        "ASIANPAINT": (.2839, 206, .004, 206, 3584.88, 5315.01, 178, "INR crore", "Includes an exceptional item; no normalization applied."),
        "BAJAJ-AUTO": (.331, 230, .02, 230, 8151.42, 7478.79, 160, "INR crore", "Includes an exceptional deferred-tax item; no normalization applied."),
        "BHARTIARTL": (.102, 193, .79, 193, 235018, 49882, 159, "INR million", "Includes exceptional items and a tax credit; no normalization applied."),
        "HCLTECH": (.422, 372, 0.0, 372, 12266, 11674, 310, "INR crore", "Issuer explicitly reports debt-equity as 0.0."),
        "HEROMOTOCO": (.3002, 149, .01, 149, 4609.95, 3967.96, 122, "INR crore", "Prior year includes a VRS exceptional item; no normalization applied."),
        "HINDUNILVR": (1.082, 179, 0.0, 179, 10644, 10114, 146, "INR crore", "Issuer explicitly reports debt-equity as 0.0; ratio includes lease liabilities."),
        "JSWSTEEL": (.0859, 271, .82, 271, 5837, 8041, 220, "INR crore", "Includes exceptional items; no normalization applied."),
        "M&M": (.2727, 180, .02, 180, 11854.96, 10642.29, 150, "INR crore", "Prior comparative was restated for an amalgamation; issuer-restated value retained."),
        "RELIANCE": (.146, 118, .37, 118, 35262, 42042, 85, "INR crore", ""),
        "TATACONSUM": (.1102, 361, .03, 361, 1254.75, 954.71, 304, "INR crore", "Includes exceptional items; no normalization applied."),
        "TATASTEEL": (.1334, 384, .44, 384, 13969.70, 15661.85, 283, "INR crore", "Prior comparative is issuer-restated and both years include exceptional items; no normalization applied."),
        "TCS": (.76, 308, .1, 308, 48057, 43559, 254, "INR crore", "Prior year includes a legal-settlement exceptional item; no normalization applied."),
        "TECHM": (.2024, 568, .0438, 568, 35061, 20637, 469, "INR million", "Includes impairment of subsidiary investments; no normalization applied."),
        "TRENT": (.3085, 180, .38, 180, 1584.84, 1435.82, 154, "INR crore", "Prior year includes an exceptional gain; no normalization applied."),
    },
    "2024-08-07": {
        "ADANIENT": (.2452, 369, .34, 368, 2844.26, 1622.73, 280, "INR crore", "Includes discontinued operations; no normalization applied."),
        "BHARTIARTL": (.083, 176, 1.24, 176, 49882, -896, 142, "INR million", "Prior comparative is a reported loss; no normalization applied."),
        "DRREDDY": (.2535, 154, .03, 154, 43420, 26128, 114, "INR million", ""),
        "GRASIM": (.0369, 373, .18, 372, 945.39, 2123.73, 277, "INR crore", "Includes exceptional items; no normalization applied."),
        "M&M": (.2675, 190, .03, 190, 10717.80, 6548.64, 159, "INR crore", "Comparative reflects issuer merger accounting; no normalization applied."),
        "TECHM": (.1189, 358, .0202, 358, 21286, 37775, 277, "INR million", "Includes impairment of subsidiary investments; no normalization applied."),
        "TITAN": (.2303, 350, .53, 350, 3544, 3333, 280, "INR crore", ""),
        "WIPRO": (.2109, 255, .09, 255, 91186, 91767, 181, "INR million", ""),
    },
}

FY = {"2024-08-07": "2023-24", "2025-08-07": "2024-25"}
PERIOD_END = {"2024-08-07": "2024-03-31", "2025-08-07": "2025-03-31"}
CURRENT_START = {"2024-08-07": "2023-04-01", "2025-08-07": "2024-04-01"}
PRIOR_START = {"2024-08-07": "2022-04-01", "2025-08-07": "2023-04-01"}
PRIOR_END = {"2024-08-07": "2023-03-31", "2025-08-07": "2024-03-31"}
NONCOMPARABLE_PERIODS = {
    ("2025-08-07", "NESTLEIND"): {
        "current_period_start": "2024-04-01", "current_period_end": "2025-03-31",
        "current_period_months": 12, "prior_period_start": "2023-01-01",
        "prior_period_end": "2024-03-31", "prior_period_months": 15,
        "comparison_status": "NONCOMPARABLE_PERIOD_LENGTH", "annualization_applied": False,
    }
}

ROCE_FORMULAS = {
    "ADANIENT": "Earnings before interest, exceptional items and taxes / Average Capital Employed",
    "ADANIPORTS": "Earnings before interest, taxes and exceptional items / Capital Employed (Tangible Networth + Total Debt)",
    "ASIANPAINT": "Profit before interest, exceptional items and tax / Average Capital Employed",
    "BAJAJ-AUTO": "Profit before tax / Capital employed",
    "BHARTIARTL": "Adjusted EBIT / Average Capital Employed",
    "DRREDDY": "Earnings before interest and taxes / Capital Employed",
    "GRASIM": "EBIT / (Net Worth + Total Debt + Deferred Tax Liability)",
    "HCLTECH": "Earnings before interest and taxes / Capital employed",
    "HEROMOTOCO": "Earnings before interest and taxes / (Tangible net worth + Total debt + Deferred tax liability)",
    "HINDUNILVR": "Earnings before interest and taxes / Capital employed",
    "JSWSTEEL": "Profit before tax after exceptional items and finance cost / Tangible Net Worth + Total Debt + Deferred Tax Liability",
    "M&M": "Profit before interest and tax / (Average Total Equity + Average Total Debt)",
    "NESTLEIND": "Earnings before interest and taxes / Capital Employed",
    "RELIANCE": "Profit after tax + Deferred tax expense/(income) + Finance cost - Other cash-investment income / Average Capital Employed",
    "TATACONSUM": "EBIT / Capital Employed",
    "TATASTEEL": "EBIT / Average Capital Employed",
    "TCS": "Profit before tax and finance costs / (Net worth + Lease liabilities + Deferred tax liabilities)",
    "TECHM": "Earnings before interest and taxes / Average Capital employed",
    "TITAN": "Profit before tax and finance cost / (Tangible Net Worth + Total Debt + Deferred Tax Liability)",
    "TRENT": "Earnings before interest and tax and exceptional gain on reassessment / Average Capital Employed",
    "WIPRO": "Earnings before interest and tax / Capital employed",
}
DEBT_FORMULAS = {
    "ADANIENT": "(Long Term Borrowings + Short Term Borrowings) / Net Worth",
    "ADANIPORTS": "Total Debt / Shareholder's Equity",
    "ASIANPAINT": "Total Debt (Borrowings) / Total Equity",
    "BAJAJ-AUTO": "Total debt / Shareholder's equity",
    "BHARTIARTL": "(Non-current borrowings + Current borrowings - Cash and cash equivalents - Term deposits) / Equity",
    "DRREDDY": "Total Debt / Shareholder's Equity",
    "GRASIM": "Total Debt / Total Equity",
    "HCLTECH": "Total debts / Total equity",
    "HEROMOTOCO": "Total debt including lease liabilities / Shareholder's Equity",
    "HINDUNILVR": "Total debt / Equity",
    "JSWSTEEL": "Total Borrowings / Total Equity",
    "M&M": "(Long term Borrowings + Short term Borrowings) / Total Equity",
    "NESTLEIND": "Total Debt / Equity",
    "RELIANCE": "Total Debt / Total Equity",
    "TATACONSUM": "Total Debt including lease liabilities / Total Equity",
    "TATASTEEL": "Net debt / Average equity",
    "TCS": "Debt consisting of borrowings and lease liabilities / Total equity",
    "TECHM": "Total debt (lease liabilities) / Total shareholders' equity",
    "TITAN": "Borrowings and lease liabilities / Total equity",
    "TRENT": "Total Debt / Shareholder's Equity",
    "WIPRO": "Debt consisting of borrowings and lease liabilities / Total equity",
}


def _available_date(value: str) -> str:
    return datetime.strptime(value.split()[0], "%d-%b-%Y").date().isoformat()


def finalize() -> None:
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    by_date = {row["ranking_date"]: row for row in mapping["snapshots"]}
    for ranking_date, decisions in DECISIONS.items():
        packet_root = GENERATED / f"fundamental_adjudication_{ranking_date[:4]}"
        accepted = []
        for ticker, values in sorted(decisions.items()):
            roce, roce_page, debt, debt_page, current, prior, profit_page, unit, warning = values
            packet = json.loads((packet_root / f"{ticker}.json").read_text(encoding="utf-8"))
            boundaries = packet["section_boundaries"]
            basis = (
                f"Inside audited standalone section pages {boundaries['standalone_start_page']}-"
                f"{boundaries['standalone_end_page']}; consolidated section begins page "
                f"{boundaries['consolidated_start_page']}."
            )
            accepted.append({
                "ticker": ticker,
                "available_date": _available_date(packet["dissemination_timestamp"]),
                "dissemination_timestamp": packet["dissemination_timestamp"],
                "financial_year": FY[ranking_date],
                "period_end": PERIOD_END[ranking_date],
                "pdf_sha256": packet["pdf_sha256"],
                "reporting_basis": "STANDALONE",
                "review_status": "ACCEPTED",
                "review_reason": "Complete explicit audited standalone disclosure set verified from the cached NSE report.",
                "basis_evidence": basis,
                "roce": {"classification": "DIRECT_DISCLOSURE", "label": "Return on Capital Employed", "canonical_decimal": roce, "page": roce_page, "table": "Standalone statutory financial ratios", "formula": ROCE_FORMULAS[ticker], "basis_evidence": basis},
                "debt_to_equity": {"classification": "DIRECT_DISCLOSURE", "label": "Debt-Equity Ratio", "canonical_decimal": debt, "page": debt_page, "table": "Standalone statutory financial ratios", "formula": DEBT_FORMULAS[ticker], "basis_evidence": basis},
                "profit": {"classification": "DIRECT_DISCLOSURE", "label": "Profit for the year / Profit after tax", "current_value": current, "prior_value": prior, "page": profit_page, "table": "Standalone Statement of Profit and Loss", "unit": unit, "current_period_start": CURRENT_START[ranking_date], "current_period_end": PERIOD_END[ranking_date], "current_period_months": 12, "prior_period_start": PRIOR_START[ranking_date], "prior_period_end": PRIOR_END[ranking_date], "prior_period_months": 12, "comparison_status": "COMPARABLE_EXACT_ISSUER_PRIOR_YEAR", "comparability_warning": warning, "basis_evidence": basis},
            })
            packet["review_state"] = "ACCEPTED"
            packet["review_reason"] = accepted[-1]["review_reason"]
            packet["basis_evidence"] = basis
            (packet_root / f"{ticker}.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

        by_date[ranking_date]["accepted"] = accepted
        inventory_path = packet_root / "inventory.json"
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        for row in inventory["rows"]:
            packet_path = packet_root / row["packet"]
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            if row["ticker"] not in decisions:
                if not row["roce_pages"]:
                    reason = "MISSING_EXPLICIT_ROCE"
                elif not row["debt_to_equity_pages"]:
                    reason = "MISSING_EXPLICIT_DEBT_EQUITY"
                elif not row["profit_pages"]:
                    reason = "NO_VALID_STANDALONE_PAT_PAIR"
                elif row["ticker"] == "NESTLEIND" and ranking_date == "2025-08-07":
                    reason = "NO_VALID_STANDALONE_PAT_PAIR"
                    packet["period_audit"] = NONCOMPARABLE_PERIODS[(ranking_date, row["ticker"])]
                elif row["ticker"] == "MARUTI":
                    reason = "SUBSTITUTE_ONLY_NET_DEBT_TO_EQUITY"
                else:
                    reason = "EXPLICIT_DEBT_EQUITY_VALUE_NOT_NUMERIC"
                packet["review_state"] = "HARD_REJECT"
                packet["review_reason"] = reason
                packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
            row["review_state"] = packet["review_state"]
            row["review_reason"] = packet["review_reason"]
        inventory_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    mapping["snapshots"] = sorted(mapping["snapshots"], key=lambda row: row["ranking_date"])
    MAPPING.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    finalize()
