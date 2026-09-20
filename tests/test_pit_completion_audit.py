from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_spec = spec_from_file_location("pit_completion_audit", Path(__file__).parents[1] / "marketdata/runners/audit_pit_completion.py")
audit = module_from_spec(_spec)
_spec.loader.exec_module(audit)


@pytest.mark.parametrize("stamp,expected", [
    ("2026-09-07T10:00:00+00:00", True),
    ("2026-09-07T10:00:01+00:00", False),
    ("2026-09-07T15:30:00+05:30", True),
    ("2026-09-07T15:30:01+05:30", False),
    ("2026-09-06T23:59:59+05:30", True),
    ("2026-09-07", False),
    ("2026-09-07T09:00:00", False),
    ("", False),
])
def test_clock_leads_require_explicit_timezone_and_frozen_cutoff(stamp, expected):
    cutoff = datetime(2026, 9, 7, 15, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert audit.clock_before_cutoff(stamp, cutoff) is expected


def test_existing_audit_directory_cannot_be_overwritten(tmp_path):
    with pytest.raises(ValueError, match="fresh"):
        audit.audit(tmp_path, tmp_path)
