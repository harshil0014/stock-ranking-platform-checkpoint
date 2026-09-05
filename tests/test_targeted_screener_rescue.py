from pathlib import Path

import pandas as pd
import pytest

from stock_ranker.targeted_screener_rescue import _clock_row


def test_clock_row_requires_official_host_and_preserves_exact_timestamp() -> None:
    row = _clock_row(
        ticker="ABC", isin="INE000A00000", financial_year="2022-2023",
        timestamp="07-Aug-2023 15:30:00", source_url="https://nsearchives.nseindia.com/a.pdf",
        status="EXACT", evidence_path="evidence.json",
    )
    assert row["dissemination_timestamp"] == "2023-08-07T15:30:00+05:30"
    with pytest.raises(ValueError, match="official NSE URL"):
        _clock_row(
            ticker="ABC", isin="INE000A00000", financial_year="2022-2023",
            timestamp="07-Aug-2023 15:30:00", source_url="https://vendor.example/a.pdf",
            status="EXACT", evidence_path="evidence.json",
        )
