from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd


RUNNER = Path(__file__).parents[1] / "marketdata" / "runners" / "daily_bse_history.py"
SPEC = importlib.util.spec_from_file_location("daily_bse_history", RUNNER)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_failure_categories_and_retry_windows() -> None:
    assert module.classify_failure(
        "YFPricesMissingError: possibly delisted; no price data found"
    ) == "NO_PROVIDER_HISTORY"
    assert module.classify_failure(
        "ValueError: provider raw close differs from accepted BSE close by 4%"
    ) == "PRICE_MISMATCH"
    assert module.classify_failure(
        "ValueError: provider terminal observation is 12 calendar days from accepted trade date"
    ) == "STALE_HISTORY"
    assert module.classify_failure("TimeoutError: slow provider") == "PROVIDER_ERROR"

    assert (
        module.retry_after_trade_date("2026-09-02", "NO_PROVIDER_HISTORY")
        == "2026-10-02"
    )
    assert (
        module.retry_after_trade_date("2026-09-02", "PRICE_MISMATCH")
        == "2026-09-09"
    )


def test_cooldown_skips_known_failure_without_hiding_new_identity(tmp_path: Path) -> None:
    bse = pd.DataFrame(
        [
            {
                "ticker": "BSE-500001",
                "isin": "INE001A01010",
                "exchange_security_id": "500001",
                "trade_date": "2026-09-05",
            },
            {
                "ticker": "BSE-500002",
                "isin": "INE002A01011",
                "exchange_security_id": "500002",
                "trade_date": "2026-09-05",
            },
        ]
    )
    state = pd.DataFrame(
        [
            {
                "ticker": "BSE-500001",
                "isin": "INE001A01010",
                "exchange_security_id": "500001",
                "provider_code": "500001.BO",
                "category": "NO_PROVIDER_HISTORY",
                "first_failed_trade_date": "2026-09-02",
                "last_failed_trade_date": "2026-09-02",
                "failure_count": "1",
                "retry_after_trade_date": "2026-10-02",
                "last_error": "no price data",
            }
        ],
        columns=module.FAILURE_STATE_COLUMNS,
    )

    selected, audit = module.select_pending(
        bse,
        cache_root=tmp_path,
        failure_state=state,
        limit=10,
        retry_suppressed=False,
    )
    assert selected["ticker"].tolist() == ["BSE-500002"]
    assert audit["suppressed_by_cooldown"] == 1

    changed = bse.copy()
    changed.loc[0, "isin"] = "INE999A01019"
    selected_changed, audit_changed = module.select_pending(
        changed,
        cache_root=tmp_path,
        failure_state=state,
        limit=10,
        retry_suppressed=False,
    )
    assert "BSE-500001" in selected_changed["ticker"].tolist()
    assert audit_changed["suppressed_by_cooldown"] == 0


def test_unified_refresh_dry_run_includes_daily_bse_maintenance(tmp_path: Path) -> None:
    runner = Path(__file__).parents[1] / "marketdata" / "runners" / "refresh_company_data.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(runner),
            "--dry-run",
            "--secondary-limit",
            "0",
            "--bse-history-limit",
            "7",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    plan = json.loads(completed.stdout)
    assert plan["write_free"] is True
    assert plan["bse_history"] is not None
    assert "daily_bse_history.py" in " ".join(plan["bse_history"])
    assert "--limit" in plan["bse_history"]
    assert "7" in plan["bse_history"]
    assert not list(tmp_path.iterdir())


def test_seed_state_uses_latest_manual_backfill_failures(tmp_path: Path) -> None:
    older = tmp_path / "bse_history_backfill_20260905T070616Z.csv"
    newer = tmp_path / "bse_history_backfill_20260905T081458Z.csv"
    pd.DataFrame(
        [
            {
                "ticker": "BSE-500001",
                "isin": "INE001A01010",
                "exchange_security_id": "500001",
                "provider_code": "500001.BO",
                "trade_date": "2026-09-02",
                "status": "FAILED",
                "error": "no price data found",
            }
        ]
    ).to_csv(older, index=False)
    pd.DataFrame(
        [
            {
                "ticker": "BSE-500002",
                "isin": "INE002A01011",
                "exchange_security_id": "500002",
                "provider_code": "500002.BO",
                "trade_date": "2026-09-02",
                "status": "FAILED",
                "error": "YFPricesMissingError: possibly delisted; no price data found",
            }
        ]
    ).to_csv(newer, index=False)

    state, source = module.seed_failure_state_from_latest_backfill(tmp_path)
    assert source is not None and source.endswith(newer.name)
    assert state["ticker"].tolist() == ["BSE-500002"]
    assert state.iloc[0]["category"] == "NO_PROVIDER_HISTORY"
    assert state.iloc[0]["retry_after_trade_date"] == "2026-10-02"
