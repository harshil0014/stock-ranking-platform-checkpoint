"""Hash the revised equal-priority current-only professor overlay."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "experiments/professor-current-fallback-20261003"
OUT = BASE / "equal-priority-v2"
MANIFEST = OUT / "manifest.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    files = sorted(p for p in OUT.iterdir() if p.is_file() and p != MANIFEST)
    files += [BASE / "manifest.json", ROOT / "research/reports/professor_current_equal_priority_v2_20261003.md",
              ROOT / "research/runners/promote_professor_current_fallback_v2_20261003.py",
              ROOT / "research/runners/audit_professor_current_fallback_v2_20261003.py", Path(__file__)]
    doc = {
        "schema": "professor_current_equal_priority_v2_manifest",
        "manifest_excludes_itself": True,
        "files": [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)} for p in files],
    }
    MANIFEST.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"{len(files)} files; manifest SHA256 {sha(MANIFEST)}")


if __name__ == "__main__":
    main()
