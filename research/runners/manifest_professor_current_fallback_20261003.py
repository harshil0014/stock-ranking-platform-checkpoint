"""Finalize checksums for the isolated professor-current fallback artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments/professor-current-fallback-20261003"
MANIFEST = OUT / "manifest.json"
SOURCE = Path(r"C:\Users\Harshil\Downloads\_Organized\Documents\Copy of OK Strategy - Master Sheet v4.3 (1).xlsx")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    paths = sorted(p for p in OUT.iterdir() if p.is_file() and p != MANIFEST)
    paths += [ROOT / "research/runners/build_professor_current_fallback_20261003.py",
              ROOT / "research/runners/audit_professor_current_fallback_20261003.py",
              Path(__file__), ROOT / "research/reports/professor_current_fallback_20261003.md"]
    manifest = {
        "schema": "professor_current_fallback_manifest_v2",
        "manifest_excludes_itself": True,
        "source_workbook_sha256": sha(SOURCE),
        "accepted_company_facts_sha256": summary["accepted_company_facts_sha256"],
        "accepted_state_sha256": summary["accepted_state_sha256"],
        "files": [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)} for p in paths],
    }
    assert manifest["source_workbook_sha256"] == summary["source_workbook_sha256"]
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{len(paths)} files, manifest SHA256 {sha(MANIFEST)}")


if __name__ == "__main__":
    main()
