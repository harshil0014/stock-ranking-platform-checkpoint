"""Hash every artifact from the research-only current-data champion rerun."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments/professor-current-fallback-20261003/champion-data-refresh-research-v1"
MANIFEST = OUT / "manifest.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    files = sorted(p for p in OUT.iterdir() if p.is_file() and p != MANIFEST)
    files += [ROOT / "research/runners/run_frozen_champion_professor_current_20261003.py",
              ROOT / "research/runners/audit_frozen_champion_professor_current_20261003.py",
              Path(__file__), ROOT / "research/reports/professor_current_champion_data_refresh_20261003.md"]
    doc = {
        "schema": "frozen_d499580_professor_current_manifest_v1",
        "manifest_excludes_itself": True,
        "files": [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)} for p in files],
    }
    MANIFEST.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"{len(files)} files; manifest SHA256 {sha(MANIFEST)}")


if __name__ == "__main__":
    main()
