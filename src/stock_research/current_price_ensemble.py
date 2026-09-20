"""Validation boundary for the current outcome-blind price ensemble."""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import pandas as pd

def validate_current_price_ensemble(root: str|Path) -> dict:
    root=Path(root); manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8")); artifacts=manifest.get("artifacts",[])
    payload=json.dumps(artifacts,sort_keys=True,separators=(",", ":")).encode()
    if sha256(payload).hexdigest()!=manifest.get("fingerprint"): raise ValueError("current ensemble manifest fingerprint mismatch")
    for item in artifacts:
        path=root/item["path"]
        if not path.is_file() or path.stat().st_size!=item["size"] or sha256(path.read_bytes()).hexdigest()!=item["sha256"]: raise ValueError(f"current ensemble artifact changed: {item['path']}")
    summary=json.loads((root/"summary.json").read_text(encoding="utf-8")); rows=pd.read_csv(root/"rankings.csv")
    if summary.get("product_default_changed") is not False or summary.get("outcomes_accessed_for_current_ranking") is not False: raise ValueError("current ensemble scientific boundary violated")
    if rows.duplicated("isin").any() or len(rows)!=summary["ranked"]: raise ValueError("current ensemble identity/count mismatch")
    return summary
