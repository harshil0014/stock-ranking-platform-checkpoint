"""Offline canonical re-extraction and two-build determinism verification.

Run in .venv-recovery. Uses .venv-marketdata only for existing review builders.
Neither process accesses a provider or writes accepted product data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from review_recovery_ixbrl import extract


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--all", action="store_true", help="Re-extract every cached review, not a 12-file sample")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    pack = args.pack.resolve()
    accepted = root / "data/company_facts/accepted_state.json"
    protected = digest(accepted)
    files = [p for p in sorted((pack / "arelle_review_v2").glob("*.json")) if p.name != "summary.json"]
    if not args.all:
        files = files[::max(1, len(files) // 12)]
    verified = []
    for file in files:
        prior = json.loads(file.read_text(encoding="utf-8"))
        if prior["status"] == "PARSE_FAILED":
            raise ValueError("cached parser failure requires review")
        fresh = extract(file.with_suffix(".html"), prior["isin"])
        for key in ("source_sha256", "isin", "facts", "identity_fields", "status", "parser_version"):
            if canonical(prior[key]) != canonical(fresh[key]):
                raise ValueError(f"non-reproducible {key}: {file.name}")
        verified.append(prior["source_sha256"])
    interpreter = root / ".venv-marketdata/Scripts/python.exe"
    builds = []
    artifact_names = ("financial_review_facts.csv", "shareholding_review.csv", "unresolved.csv",
                      "evidence_index.csv", "raw_inventory.json", "issuer_recovery_audit.csv",
                      "recovery_audit.json", "validation_report.json")
    for _ in range(2):
        for runner, extra in (("normalize_recovery_review.py", []),
                              ("financial_recovery_pack.py", ["report"]),
                              ("audit_financial_recovery_pack.py", [])):
            result = subprocess.run([str(interpreter), str(root / "marketdata/runners" / runner),
                                     *extra, "--pack", str(pack)], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stderr or result.stdout)
        builds.append({name: digest(pack / name) for name in artifact_names})
    if builds[0] != builds[1]:
        raise ValueError("review artifacts differ across deterministic rebuilds")
    if digest(accepted) != protected:
        raise ValueError("accepted product pointer changed during verification")
    result = {"passed": True, "network_requested": False, "canonical_reextractions": len(verified),
              "verified_source_hashes": verified, "two_builds_identical": True,
              "artifact_hashes": builds[0], "accepted_pointer_sha256": protected,
              "accepted_new_facts": 0, "parser_logs_excluded_from_comparison": True}
    target = pack / "determinism_verification.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(canonical(result), encoding="utf-8")
    temp.replace(target)
    print(canonical({k: v for k, v in result.items() if k != "verified_source_hashes"}))


if __name__ == "__main__":
    main()
