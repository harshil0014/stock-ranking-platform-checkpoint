from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd


ROOT = Path(__file__).parents[1]
AUDIT = ROOT / "marketdata" / "runners" / "audit_website_gap_root_causes.py"
SPEC = importlib.util.spec_from_file_location("audit_website_gap_root_causes", AUDIT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_short_listing_history_is_terminal_not_acquisition_failure() -> None:
    row = pd.Series({
        "ticker": "NEWCO", "company": "New Co", "isin": "INE000A01010",
        "primary_exchange": "NSE", "listing_date": "2026-04-20",
        "history_status": "ACCEPTED_ADJUSTED_HISTORY", "history_5y_usable": False,
    })
    cause, route, terminal = module._cause(row, "history_5y", pd.Timestamp("2026-09-07").date())
    assert cause == "LISTING_HORIZON_TOO_SHORT"
    assert route == "NO_ACQUISITION_NEEDED"
    assert terminal == "INSUFFICIENT_LISTING_HISTORY_5Y"


def test_market_cap_with_price_and_share_count_is_resolver_bug() -> None:
    row = pd.Series({"latest_price": 100.0, "official_total_shares": 1_000_000})
    cause, route, terminal = module._cause(row, "market_cap", pd.Timestamp("2026-09-07").date())
    assert cause == "RESOLVER_BUG"
    assert "DERIVE_MARKET_CAP" in route
    assert terminal == "ACTION_REQUIRED"


def test_structured_profile_counts_as_available_without_provider_prose() -> None:
    row = pd.Series({
        "company": "ABC Limited", "isin": "INE001A01010", "primary_exchange": "BSE",
        "company_profile": None,
    })
    assert module._available(row, "company_profile") is True


def test_display_state_audit_is_total() -> None:
    facts = pd.DataFrame([{
        "ticker": "ABC", "company": "ABC Limited", "isin": "INE001A01010",
        "primary_exchange": "NSE", "exchange_security_id": "ABC",
        "listing_date": "2020-01-01", "latest_price": 100.0,
    }])
    gaps, display, summary = module.build_audit(facts, as_of=pd.Timestamp("2026-09-07").date())
    assert len(display) == len(module.CATEGORIES)
    assert summary["display_state_coverage_pct"] == 100.0
    assert not display["display_state"].astype(str).str.contains("UNAVAILABLE", case=False).any()
    assert len(gaps) > 0


def test_recovery_dry_run_plans_full_residual_pass(tmp_path: Path) -> None:
    runner = ROOT / "marketdata" / "runners" / "recover_website_gaps.py"
    completed = subprocess.run(
        [sys.executable, str(runner), "--dry-run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    plan = json.loads(completed.stdout)
    assert plan["status"] == "PLANNED"
    assert plan["scientific_models"] == "UNCHANGED"
    official = " ".join(plan["steps"]["official_exchange"]["command"])
    bse_history = " ".join(plan["steps"]["bse_history"]["command"])
    assert "--xbrl-limit 0" in official
    assert "--bse-shareholding-limit 100000" in official
    assert "--limit 100000" in bse_history
