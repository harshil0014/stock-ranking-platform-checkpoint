from pathlib import Path

import pandas as pd
import pytest

from marketdata.runners.apply_screener_deadline_overlay import (
    merge_sector_export_directories,
    merge_sector_exports,
)


IDENTITY = {
    "Name": "Example Limited",
    "BSE Code": "500001",
    "NSE Code": "EXAMPLE",
    "ISIN Code": "INE000A01001",
    "Industry Group": "Industrials",
    "Industry": "Industrial Products",
}


def write_export(path: Path, **extra: object) -> None:
    pd.DataFrame([{**IDENTITY, **extra}]).to_csv(path, index=False)


def test_sector_passes_merge_complementary_fields_by_exact_isin(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    supplemental = tmp_path / "supplemental"
    primary.mkdir()
    supplemental.mkdir()
    write_export(primary / "industrials.csv", **{"Return on capital employed": 19.2})
    write_export(supplemental / "industrials.csv", **{"Public holding": 31.5})

    result = merge_sector_export_directories([primary, supplemental])

    assert len(result) == 1
    assert result.loc[0, "ISIN Code"] == IDENTITY["ISIN Code"]
    assert result.loc[0, "Return on capital employed"] == pytest.approx(19.2)
    assert result.loc[0, "Public holding"] == pytest.approx(31.5)


def test_sector_exports_reject_duplicate_isin_across_sectors(tmp_path: Path) -> None:
    write_export(tmp_path / "one.csv")
    write_export(tmp_path / "two.csv", **{"Industry Group": "Technology"})

    with pytest.raises(ValueError, match="duplicate ISINs"):
        merge_sector_exports(sorted(tmp_path.glob("*.csv")))
