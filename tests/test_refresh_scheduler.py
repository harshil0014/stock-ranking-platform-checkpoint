from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_scheduler_is_weekday_local_and_calls_existing_refresh():
    text = (ROOT / "marketdata/scheduling/register_daily_refresh.ps1").read_text(encoding="utf-8")
    assert "Monday,Tuesday,Wednesday,Thursday,Friday" in text
    assert "20:00" in text
    assert "windows_refresh.ps1" in text
    assert "StartWhenAvailable" in text
    assert "IgnoreNew" in text


def test_refresh_retains_last_known_good_boundary():
    text = (ROOT / "marketdata/runners/refresh_company_data.py").read_text(encoding="utf-8")
    assert "ACCEPTED_WITH_PROVIDER_FAILURES_USING_LAST_KNOWN_GOOD" in text
    assert "FACT_BUILD_FAILED_LAST_KNOWN_GOOD_RETAINED" in text
    assert "--seed-batch" in text


def test_weekly_fundamental_discovery_is_metadata_only_and_separate_from_promotion():
    register = (ROOT / "marketdata/scheduling/register_weekly_fundamental_discovery.ps1").read_text(encoding="utf-8")
    runner = (ROOT / "marketdata/scheduling/windows_fundamental_discovery.ps1").read_text(encoding="utf-8")
    assert "-Weekly" in register
    assert "Monday" in register
    assert "Metadata-only" in register
    assert "discover_pit_fundamental_scale.py" in runner
    assert "download_pit_annual_report_batch.py" not in runner
    assert "prepare_real_research_v2" not in runner
