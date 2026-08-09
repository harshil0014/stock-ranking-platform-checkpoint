"""Finalize audited 2022/2023 NSE availability rescues declaratively."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "data/walk_forward"
MAPPING = ROOT / "marketdata/specifications/walk_forward_annual_report_mapping.json"
RESCUE_SPEC = ROOT / "marketdata/specifications/walk_forward_nse_availability_rescue.json"

# ticker: ROCE decimal/page/formula, D/E decimal/page/formula, PAT current/prior/page/unit/warning
DECISIONS = {
    "2022-08-05": {
        "CIPLA": (.1582, 291, "Earnings before interest and taxes / Capital employed", .001, 291, "Total debt / Shareholder's equity", 2957.93, 2468.28, 232, "INR crore", "PAT includes reported discontinuing/restructuring operations; no normalization applied."),
        "DRREDDY": (.123, 151, "Earnings before interest and taxes / (Tangible Net Worth + Total debt)", .12, 151, "Total Debt / Shareholder's Equity", 16232, 21864, 75, "INR million", "Reported annual PAT declined; no normalization applied."),
        "EICHERMOT": (.192, 163, "Earnings before interest and taxes / (Tangible Net Worth + Total Debt + Deferred Tax Liability)", 0.0, 163, "Total Debt / Shareholder's Equity", 1586.22, 1329.70, 136, "INR crore", "Issuer explicitly reports debt-equity as 0.0."),
        "HCLTECH": (.301, 303, "Earnings before interest and taxes / Capital employed", 0.0, 302, "Total debts / Total equity", 10874, 8743, 250, "INR crore", "Issuer explicitly reports debt-equity as 0.0."),
        "HINDUNILVR": (1.078, 106, "Earnings before interest and taxes / Capital employed", 0.0, 106, "Total debt / Equity", 8818, 7954, 72, "INR crore", "Issuer explicitly reports debt-equity as 0.0."),
        "TITAN": (.2903, 235, "Profit before tax and finance cost / (Tangible Net Worth + Total Debt + Deferred Tax Liability)", .15, 235, "Borrowings and lease liabilities / Total equity", 2180, 877, 166, "INR crore", "Includes reported exceptional items; no normalization applied."),
        "UPL": (.1442, 132, "Profit before interest and tax / (Shareholders' Equity + Long term liabilities)", .20, 132, "Total Debt / Equity", 1176, 220, 95, "INR crore", "Auditor describes a qualified goodwill treatment affecting PAT; issuer-reported values retained without normalization."),
        "WIPRO": (.2501, 202, "Earnings before interest and tax / Capital employed", .16, 202, "Debt consisting of borrowings and lease liabilities / Total equity", 121353, 100609, 139, "INR million", ""),
    },
    "2023-08-07": {
        "GRASIM": (.0577, 222, "Earnings before interest and taxes / (Tangible Net Worth + Total Debt + Deferred Tax Liability)", .11, 222, "Total Debt / Total Equity", 2123.73, 3051.27, 174, "INR crore", "Prior PAT includes reported discontinued operations; no normalization applied."),
        "HCLTECH": (.345, 282, "Earnings before interest and taxes / Capital employed", 0.0, 282, "Total debts / Total equity", 11459, 10874, 231, "INR crore", "Issuer explicitly reports debt-equity as 0.0."),
        "HEROMOTOCO": (.2255, 155, "Earnings before interest and taxes / (Tangible net worth + Total debt + Deferred tax liability)", .01, 155, "Total debt including lease liabilities / Shareholder's Equity", 2910.58, 2473.02, 128, "INR crore", ""),
        "M&M": (.1813, 353, "Profit before interest and tax / (Average Total Equity + Average Total Debt)", .11, 353, "(Long term Borrowings + Short term Borrowings) / Total Equity", 6548.64, 4869.88, 293, "INR crore", "Prior comparative was issuer-restated for merger accounting; restated value retained."),
    },
}

FY = {"2022-08-05": "2021-22", "2023-08-07": "2022-23"}
PERIODS = {
    "2022-08-05": ("2021-04-01", "2022-03-31", "2020-04-01", "2021-03-31"),
    "2023-08-07": ("2022-04-01", "2023-03-31", "2021-04-01", "2022-03-31"),
}


def _iso_date(value: str) -> str:
    return datetime.strptime(value, "%d-%b-%Y %H:%M:%S").date().isoformat()


def finalize() -> dict[str, object]:
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    by_date = {row["ranking_date"]: row for row in mapping["snapshots"]}
    rescue_snapshots = []
    rescue_root = GENERATED / "nse_availability_rescue_v1"
    for ranking_date, decisions in DECISIONS.items():
        provenance_path = rescue_root / ranking_date / "availability_rescue_provenance.json"
        attempts = json.loads(provenance_path.read_text(encoding="utf-8"))
        by_ticker = {row["ticker"]: row for row in attempts}
        accepted = []
        current_start, period_end, prior_start, prior_end = PERIODS[ranking_date]
        packet_root = GENERATED / f"fundamental_adjudication_{ranking_date[:4]}"
        for ticker, values in sorted(decisions.items()):
            rescue = by_ticker[ticker]["availability_rescue"]
            if rescue["evidence_status"] != "RESCUED_EXACT_NSE_DISSEMINATION":
                raise ValueError(f"accepted mapping lacks exact NSE rescue: {ranking_date} {ticker}")
            packet_path = packet_root / f"{ticker}.json"
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            boundaries = packet["section_boundaries"]
            if boundaries["standalone_start_page"] is None:
                raise ValueError(f"standalone section not proven: {ranking_date} {ticker}")
            basis = (
                f"Inside audited standalone section pages {boundaries['standalone_start_page']}-"
                f"{boundaries['standalone_end_page']}; consolidated section begins page "
                f"{boundaries['consolidated_start_page']}."
            )
            roce, roce_page, roce_formula, debt, debt_page, debt_formula, current, prior, profit_page, unit, warning = values
            accepted.append({
                "ticker": ticker, "available_date": _iso_date(rescue["exchange_dissemination_timestamp"]),
                "dissemination_timestamp": rescue["exchange_dissemination_timestamp"],
                "financial_year": FY[ranking_date], "period_end": period_end,
                "pdf_sha256": rescue["attachment_sha256"], "reporting_basis": "STANDALONE",
                "review_status": "ACCEPTED",
                "review_reason": "Complete explicit audited standalone disclosure set verified from an exact pre-cutoff NSE announcement attachment.",
                "basis_evidence": basis,
                "availability_rescue": {
                    "annual_report_archive_dissemination": None,
                    "source": rescue["source"], "source_identifier": rescue["source_identifier"],
                    "exchange_dissemination_timestamp": rescue["exchange_dissemination_timestamp"],
                    "attachment_url": rescue["attachment_url"], "attachment_sha256": rescue["attachment_sha256"],
                    "evidence_status": rescue["evidence_status"],
                },
                "roce": {"classification": "DIRECT_DISCLOSURE", "label": "Return on Capital Employed", "canonical_decimal": roce, "page": roce_page, "table": "Standalone statutory financial ratios", "formula": roce_formula, "basis_evidence": basis},
                "debt_to_equity": {"classification": "DIRECT_DISCLOSURE", "label": "Debt-Equity Ratio", "canonical_decimal": debt, "page": debt_page, "table": "Standalone statutory financial ratios", "formula": debt_formula, "basis_evidence": basis},
                "profit": {"classification": "DIRECT_DISCLOSURE", "label": "Profit for the year / Profit after tax", "current_value": current, "prior_value": prior, "page": profit_page, "table": "Standalone Statement of Profit and Loss", "unit": unit, "current_period_start": current_start, "current_period_end": period_end, "current_period_months": 12, "prior_period_start": prior_start, "prior_period_end": prior_end, "prior_period_months": 12, "comparison_status": "COMPARABLE_EXACT_ISSUER_PRIOR_YEAR", "comparability_warning": warning, "basis_evidence": basis},
            })
            packet["review_state"] = "ACCEPTED"
            packet["review_reason"] = accepted[-1]["review_reason"]
            packet["basis_evidence"] = basis
            packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
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
                else:
                    reason = "EXPLICIT_DEBT_EQUITY_VALUE_NOT_NUMERIC"
                packet["review_state"] = "HARD_REJECT"
                packet["review_reason"] = reason
                packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
            row["review_state"] = packet["review_state"]
            row["review_reason"] = packet["review_reason"]
        inventory_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        rescue_snapshots.append({
            "ranking_date": ranking_date, "required_fiscal_year": FY[ranking_date],
            "attempts": [{
                "ticker": row["ticker"],
                "annual_report_archive_dissemination": row["annual_report_archive_dissemination"],
                "original_archive_selection_status": row["original_archive_selection_status"],
                "availability_rescue": row["availability_rescue"],
            } for row in attempts],
        })
    mapping["snapshots"] = sorted(mapping["snapshots"], key=lambda row: row["ranking_date"])
    MAPPING.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    rescue_spec = {
        "schema_version": 1, "source_policy": "OFFICIAL_NSE_ONLY",
        "outcome_data_acquired": False,
        "policy": "A null annual-report archive timestamp remains null. Only an exact official NSE announcement attachment with exchange dissemination at or before the frozen cutoff can rescue canonical availability.",
        "snapshots": rescue_snapshots,
    }
    RESCUE_SPEC.write_text(json.dumps(rescue_spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {"accepted": {date: len(rows) for date, rows in DECISIONS.items()}}


if __name__ == "__main__":
    print(json.dumps(finalize(), sort_keys=True))
