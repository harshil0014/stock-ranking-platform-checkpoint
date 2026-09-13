from pathlib import Path
from datetime import datetime
import shutil

path = Path(r"src\stock_ranker\product_classification.py")
text = path.read_text(encoding="utf-8")

old = (
'    provider_current = float(selected["current"]["adjusted_close"])\n'
'    official_current = float(row["latest_price"])\n'
'    relative_difference = abs(provider_current - official_current) / official_current\n'
'    if relative_difference > 0.02:\n'
'        return None, "CURRENT_PRICE_MISMATCH", "Provider history differs from the accepted exchange close by more than the Product Classification v1 two-percent identity/continuity gate."\n'
'    current = official_current\n'
)

new = (
'    provider_current = float(selected["current"]["adjusted_close"])\n'
'    official_current = float(row["latest_price"])\n'
'    relative_difference = abs(provider_current - official_current) / official_current\n'
'    current = official_current\n'
'    current_price_reason = (\n'
'        "Accepted exchange current price and exact-identity adjusted history satisfy "\n'
'        "the Product Classification v1 continuity gate."\n'
'    )\n'
'    if relative_difference > 0.02:\n'
'        screener_current = pd.to_numeric(row.get("screener_current_price"), errors="coerce")\n'
'        if pd.isna(screener_current) or float(screener_current) <= 0:\n'
'            return None, "CURRENT_PRICE_MISMATCH", (\n'
'                "Provider history differs from the accepted exchange close by more than "\n'
'                "the Product Classification v1 two-percent identity/continuity gate and "\n'
'                "no valid Screener Premium current/reference price is available."\n'
'            )\n'
'        current = float(screener_current)\n'
'        current_price_reason = (\n'
'            "Provider/exchange current-price conflict is retained as provenance; "\n'
'            "Screener Premium is authoritative for current/reference price and the "\n'
'            "accepted exact-identity adjusted history supplies historical anchors."\n'
'        )\n'
)

if old not in text:
    raise SystemExit("Expected current-price block not found; no changes made.")

text = text.replace(old, new, 1)

old_return = (
'    }, "ELIGIBLE", "Exact-identity secondary classification and accepted adjusted history satisfy current-product Baseline V1 inputs.")\n'
)
new_return = '    }, "ELIGIBLE", current_price_reason)\n'

if old_return not in text:
    raise SystemExit("Expected _secondary_metrics return line not found; no changes made.")

text = text.replace(old_return, new_return, 1)

old_override = (
'            if metrics is not None:\n'
'                reasons[ticker] = ("ELIGIBLE", "Accepted exchange current price and exact-identity adjusted history pass the Product Classification v1 continuity gate.")\n'
'                metric_rows.append(metrics)\n'
)
new_override = (
'            if metrics is not None:\n'
'                reasons[ticker] = ("ELIGIBLE", reason)\n'
'                metric_rows.append(metrics)\n'
)

if old_override not in text:
    raise SystemExit("Expected official mismatch override block not found; no changes made.")

text = text.replace(old_override, new_override, 1)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_dir = Path("local_backups") / f"screener_price_conflict_policy_{stamp}"
backup_dir.mkdir(parents=True, exist_ok=False)
backup = backup_dir / path.name
shutil.copy2(path, backup)

path.write_text(text, encoding="utf-8", newline="\n")

print(f"Patched: {path}")
print(f"Backup:  {backup}")
print("Policy: valid Screener Premium current/reference price resolves >2% provider/exchange conflicts without blocking.")
print("Research V2 / PIT logic was not touched.")
