"""Verify the sealed personalized product acceptance artifacts."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path


def verify(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    artifacts = manifest["artifacts"]
    expected = sha256(json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if expected != manifest["artifact_set_sha256"]:
        raise ValueError("acceptance artifact-set fingerprint changed")
    for item in artifacts:
        path = (root / item["path"]).resolve()
        if path.parent != root.resolve() or not path.is_file():
            raise ValueError("missing or unsafe acceptance artifact")
        if path.stat().st_size != item["bytes"] or sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("acceptance artifact changed: " + item["path"])
    acceptance = json.loads((root / "acceptance.json").read_text(encoding="utf-8"))
    browser = json.loads((root / "browser_acceptance.json").read_text(encoding="utf-8"))
    if acceptance["status"] != "PASS" or acceptance["matrix_profiles"] != 162:
        raise ValueError("personalization simulation did not pass")
    if not all(item["passed"] for item in acceptance["frozen_profile_reproduction"]):
        raise ValueError("frozen profile reproduction failed")
    if not all(acceptance["sensitivity"].values()):
        raise ValueError("input-flow sensitivity failed")
    if acceptance["protected_freeze_before"] != acceptance["protected_freeze_after"]:
        raise ValueError("frozen challenger changed")
    if browser["status"] != "PASS" or browser["console_errors"] or browser["page_errors"]:
        raise ValueError("rendered browser acceptance failed")
    return {"status": "PASS", "profiles": acceptance["matrix_profiles"],
            "browser": browser["status"], "champion_commit": acceptance["champion_commit"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    print(json.dumps(verify(parser.parse_args().run), indent=2))
