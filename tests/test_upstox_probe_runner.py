from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "marketdata" / "runners" / "run_upstox_v2_probe.py"
SPEC = importlib.util.spec_from_file_location("run_upstox_v2_probe", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_probe_uses_hash_validated_accepted_snapshot_and_never_promotes(monkeypatch, tmp_path):
    accepted_csv = tmp_path / "snapshots" / "accepted" / "company_facts.csv"
    output = tmp_path / "probe"
    captured = {}

    monkeypatch.setattr(
        MODULE,
        "resolve_inputs",
        lambda state_root: (accepted_csv, "2026-09-07"),
    )

    def fake_call(command, cwd):
        captured["command"] = command
        captured["cwd"] = cwd
        return 0

    monkeypatch.setattr(MODULE.subprocess, "call", fake_call)
    result = MODULE.main([
        "--state-root", str(tmp_path / "company_facts"),
        "--output", str(output),
        "--limit", "7",
        "--sleep-seconds", "0",
    ])

    assert result == 0
    command = captured["command"]
    assert "--company-facts" in command
    assert str(accepted_csv) in command
    assert "--limit" in command and "7" in command
    assert "--all" not in command
    assert "--resume" not in command
    assert captured["cwd"] == MODULE.ROOT


def test_existing_probe_output_resumes_instead_of_overwriting(monkeypatch, tmp_path):
    accepted_csv = tmp_path / "accepted" / "company_facts.csv"
    output = tmp_path / "existing"
    output.mkdir()
    captured = {}

    monkeypatch.setattr(
        MODULE,
        "resolve_inputs",
        lambda state_root: (accepted_csv, "2026-09-07"),
    )
    monkeypatch.setattr(
        MODULE.subprocess,
        "call",
        lambda command, cwd: captured.setdefault("command", command) or 0,
    )

    # setdefault returns the list, so use a tiny callable with an explicit status.
    def fake_call(command, cwd):
        captured["command"] = command
        return 0

    monkeypatch.setattr(MODULE.subprocess, "call", fake_call)
    result = MODULE.main(["--output", str(output), "--all", "--sleep-seconds", "0"])

    assert result == 0
    assert "--all" in captured["command"]
    assert "--resume" in captured["command"]
