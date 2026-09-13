from pathlib import Path
import shutil
from datetime import datetime

target = Path("src/stock_ranker/company_facts.py")
if not target.is_file():
    raise SystemExit(f"Missing: {target}")

text = target.read_text(encoding="utf-8")

needle = '''            for target, source_name in (
                ("pe_ratio", "screener_pe_ratio"), ("pb_ratio", "screener_pb_ratio"),
                ("trailing_eps", "screener_eps"),
            ):
                if item[target] is None:
                    item[target] = item[source_name]
'''

insert = '''            for target, source_name in (
                ("pe_ratio", "screener_pe_ratio"), ("pb_ratio", "screener_pb_ratio"),
                ("trailing_eps", "screener_eps"),
            ):
                if item[target] is None:
                    item[target] = item[source_name]

            # Current/reference-only product enrichment from accepted Screener Premium.
            # These fields do not alter Baseline V1 or frozen Research V2/PIT inputs.
            # Accepted official facts later in this build still take precedence.
            if (
                item["dividend_yield"] is None
                and item["screener_dividend_yield_pct"] is not None
            ):
                item["dividend_yield"] = item["screener_dividend_yield_pct"] / 100.0

            if (
                item["book_value"] is None
                and item["screener_current_price"] is not None
                and item["screener_pb_ratio"] is not None
                and item["screener_pb_ratio"] > 0
            ):
                item["book_value"] = (
                    item["screener_current_price"] / item["screener_pb_ratio"]
                )

            if (
                item["shares_outstanding"] is None
                and item["screener_market_cap_crore"] is not None
                and item["screener_market_cap_crore"] > 0
                and item["screener_current_price"] is not None
                and item["screener_current_price"] > 0
            ):
                item["shares_outstanding"] = (
                    item["screener_market_cap_crore"] * 10_000_000
                    / item["screener_current_price"]
                )

            if (
                item["profit_margin"] is None
                and item["screener_profit_after_tax_crore"] is not None
                and item["screener_sales_crore"] not in (None, 0)
            ):
                item["profit_margin"] = (
                    item["screener_profit_after_tax_crore"]
                    / item["screener_sales_crore"]
                )

            for target, source_name in (
                ("promoter_holding_pct", "screener_promoter_holding_pct"),
                ("public_holding_pct", "screener_public_holding_pct"),
                ("fii_holding_pct", "screener_fii_holding_pct"),
                ("dii_holding_pct", "screener_dii_holding_pct"),
                ("promoter_pledge_pct", "screener_pledged_pct"),
            ):
                if item[target] is None:
                    item[target] = item[source_name]
'''

if needle not in text:
    raise SystemExit("Expected Screener valuation mapping block not found; no changes written.")

backup_dir = Path("local_backups") / f"screener_product_fill_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
backup_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(target, backup_dir / target.name)

target.write_text(text.replace(needle, insert, 1), encoding="utf-8")

print("PASS: current/reference Screener fallback mappings added.")
print("Changed:", target)
print("Backup:", backup_dir / target.name)
print("Research V2/PIT fields were not modified.")
