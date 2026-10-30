"""Hash every retained prospective source, intermediate, and result file."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "experiments/personalized-v13-20261002"
OUT = BASE / "prospective-2025-09-30"
MANIFEST = OUT / "artifact_manifest.json"
SCRIPTS = [
    "acquire_v13_prospective_prices.py",
    "acquire_v13_prospective_bse_actions.py",
    "audit_v13_prospective_market_prices.py",
    "prepare_v13_prospective_scores.py",
    "build_v13_prospective_evidence.py",
    "audit_v13_prospective_evidence.py",
    "evaluate_v13_prospective_20250930.py",
    "repair_v13_prospective_september_prices.py",
    "audit_v13_post_reveal_price_repair.py",
    "reevaluate_v13_post_reveal_price_repair.py",
    "finalize_v13_prospective_20250930.py",
    "manifest_v13_prospective_20250930.py",
]


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    paths = [p for p in OUT.rglob("*") if p.is_file() and p != MANIFEST]
    paths += [BASE / "locked_selection.json", BASE / "blind_validation_plan.json", BASE / "decision.json"]
    paths += [ROOT / "research/runners" / name for name in SCRIPTS]
    paths += [ROOT / "research/reports/personalized_v13_prospective_20261003.md"]
    entries = []
    for i, path in enumerate(sorted(set(paths)), 1):
        entries.append({"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": hash_file(path)})
        if i % 5000 == 0:
            print(f"Hashed {i:,}/{len(paths):,} files", flush=True)
    doc = {
        "schema": "v13_prospective_artifact_manifest_v1",
        "file_count": len(entries),
        "total_bytes": sum(x["bytes"] for x in entries),
        "manifest_excludes_itself": True,
        "files": entries,
    }
    MANIFEST.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"Manifest: {len(entries):,} files, {doc['total_bytes']:,} bytes, SHA256 {hash_file(MANIFEST)}", flush=True)


if __name__ == "__main__":
    main()
