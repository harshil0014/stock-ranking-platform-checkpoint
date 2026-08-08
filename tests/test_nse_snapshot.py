from __future__ import annotations

import base64
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import pytest

from stock_ranker.nse_snapshot import (
    CANONICAL_COLUMNS,
    load_nse_snapshot,
    parse_nse_snapshot,
)
from stock_ranker.webapp import create_server
from stock_ranker.website import analyze_website_request


REAL_NIFTY = Path(r"C:\Users\Harshil\Downloads\ind_nifty50list.csv")
REAL_BHAVCOPY = Path(
    r"C:\Users\Harshil\Downloads"
    r"\BhavCopy_NSE_CM_0_0_0_20260807_F_0000.csv.zip"
)


def _nifty() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Company Name": "Alpha Limited",
            "Industry": "Technology",
            "Symbol": "ALPHA",
            "Series": "EQ",
            "ISIN Code": "INE000A01001",
        },
        {
            "Company Name": "Beta Limited",
            "Industry": "Financial Services",
            "Symbol": "BETA",
            "Series": "EQ",
            "ISIN Code": "INE000B01001",
        },
    ])


def _bhav() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "TradDt": "2026-08-07", "Sgmt": "CM", "Src": "NSE",
            "ISIN": "INE000A01001", "TckrSymb": "ALPHA", "SctySrs": "EQ",
            "OpnPric": 100, "HghPric": 112, "LwPric": 98, "ClsPric": 110,
            "LastPric": 109, "PrvsClsgPric": 100, "TtlTradgVol": 1000,
            "TtlTrfVal": 105000, "TtlNbOfTxsExctd": 80, "NewBrdLotQty": 1,
        },
        {
            "TradDt": "2026-08-07", "Sgmt": "CM", "Src": "NSE",
            "ISIN": "INE000B01001", "TckrSymb": "BETA", "SctySrs": "EQ",
            "OpnPric": 200, "HghPric": 205, "LwPric": 190, "ClsPric": 195,
            "LastPric": 196, "PrvsClsgPric": 200, "TtlTradgVol": 2500,
            "TtlTrfVal": 490000, "TtlNbOfTxsExctd": 120, "NewBrdLotQty": 1,
        },
    ])


def _csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, lineterminator="\n").encode("utf-8")


def _zip_bytes(
    frame: pd.DataFrame | None = None,
    *,
    members: list[tuple[str, bytes]] | None = None,
) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        selected = members or [(
            "BhavCopy_test.csv",
            _csv_bytes(frame if frame is not None else _bhav()),
        )]
        for name, content in selected:
            archive.writestr(name, content)
    return output.getvalue()


def _parse(
    nifty: pd.DataFrame | None = None,
    bhav: pd.DataFrame | None = None,
    archive: bytes | None = None,
):
    return parse_nse_snapshot(
        _csv_bytes(nifty if nifty is not None else _nifty()),
        archive if archive is not None else _zip_bytes(
            bhav if bhav is not None else _bhav()
        ),
        nifty_filename="ind_nifty50list.csv",
        bhavcopy_filename="BhavCopy_test.csv.zip",
    )


def _website_payload() -> dict[str, object]:
    nifty = _csv_bytes(_nifty())
    archive = _zip_bytes(_bhav())
    return {
        "input_source": "official_nse_snapshot",
        "method": "baseline_v1",
        "files": {
            "nifty_filename": "ind_nifty50list.csv",
            "nifty_base64": base64.b64encode(nifty).decode("ascii"),
            "bhavcopy_filename": "BhavCopy_test.csv.zip",
            "bhavcopy_base64": base64.b64encode(archive).decode("ascii"),
        },
    }


def test_valid_parsing_identity_join_and_canonical_order() -> None:
    result = _parse()
    assert tuple(result.snapshot.columns) == CANONICAL_COLUMNS
    assert result.snapshot["ticker"].tolist() == ["ALPHA", "BETA"]
    assert result.snapshot["company"].tolist() == [
        "Alpha Limited", "Beta Limited"
    ]
    assert result.snapshot["source"].str.contains("Official supplied").all()


def test_daily_change_and_zero_previous_close_are_safe() -> None:
    bhav = _bhav()
    result = _parse(bhav=bhav)
    assert result.snapshot.loc[0, "daily_change"] == pytest.approx(10)
    assert result.snapshot.loc[0, "daily_change_pct"] == pytest.approx(10)
    bhav.loc[0, "PrvsClsgPric"] = 0
    zero = _parse(bhav=bhav)
    assert zero.snapshot.loc[0, "daily_change"] == pytest.approx(110)
    assert pd.isna(zero.snapshot.loc[0, "daily_change_pct"])
    assert any(
        "previous_close=0" in warning
        for warning in zero.provenance["validation_warnings"]
    )


def test_missing_constituent_fails_loudly() -> None:
    with pytest.raises(ValueError, match="missing 1 NIFTY constituent"):
        _parse(bhav=_bhav().iloc[:1].copy())


def test_duplicate_constituent_identity_fails() -> None:
    nifty = pd.concat([_nifty(), _nifty().iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        _parse(nifty=nifty)


def test_duplicate_bhavcopy_match_fails() -> None:
    bhav = pd.concat([_bhav(), _bhav().iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate matches"):
        _parse(bhav=bhav)


@pytest.mark.parametrize(
    "archive, message",
    [
        (b"not-a-zip", "valid ZIP"),
        (_zip_bytes(members=[("readme.txt", b"x")]), "exactly one CSV"),
        (_zip_bytes(members=[("a.csv", b"x"), ("b.csv", b"x")]), "exactly one CSV"),
        (_zip_bytes(members=[("../bad.csv", b"x")]), "Unsafe ZIP member"),
        (_zip_bytes(members=[("empty.csv", b"")]), "empty"),
    ],
)
def test_invalid_archives_fail(archive: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _parse(archive=archive)


@pytest.mark.parametrize("kind", ["nifty", "bhavcopy"])
def test_missing_required_columns(kind: str) -> None:
    if kind == "nifty":
        with pytest.raises(ValueError, match="missing required columns"):
            _parse(nifty=_nifty().drop(columns="ISIN Code"))
    else:
        with pytest.raises(ValueError, match="missing required columns"):
            _parse(bhav=_bhav().drop(columns="ClsPric"))


@pytest.mark.parametrize("date", ["07-08-2026", "2026-02-30"])
def test_invalid_trade_date(date: str) -> None:
    bhav = _bhav()
    bhav["TradDt"] = date
    with pytest.raises(ValueError, match="TradDt"):
        _parse(bhav=bhav)


@pytest.mark.parametrize(
    "column, value, message",
    [
        ("ClsPric", "bad", "numeric"),
        ("ClsPric", -1, "OHLC"),
        ("HghPric", 10, "at least low"),
        ("TtlTradgVol", -1, "must not be negative"),
    ],
)
def test_invalid_market_values(column: str, value: object, message: str) -> None:
    bhav = _bhav()
    if isinstance(value, str):
        bhav[column] = bhav[column].astype(object)
    bhav.loc[0, column] = value
    with pytest.raises(ValueError, match=message):
        _parse(bhav=bhav)


def test_provenance_records_mode_counts_hashes_and_limits() -> None:
    nifty = _csv_bytes(_nifty())
    archive = _zip_bytes(_bhav())
    result = parse_nse_snapshot(
        nifty, archive, nifty_filename="nifty.csv", bhavcopy_filename="bhav.zip"
    )
    provenance = result.provenance
    assert provenance["data_mode"] == "REAL CURRENT SNAPSHOT"
    assert provenance["trade_date"] == "2026-08-07"
    assert provenance["constituent_count"] == 2
    assert provenance["matched_count"] == 2
    assert provenance["missing_count"] == 0
    assert provenance["duplicate_match_count"] == 0
    assert provenance["nifty_file_sha256"] == sha256(nifty).hexdigest()
    assert provenance["nse_zip_sha256"] == sha256(archive).hexdigest()
    assert provenance["ranking_available"] is False
    warnings = " ".join(provenance["validation_warnings"])
    assert "one-day market snapshot" in warnings
    assert "YoY" in warnings
    assert "Research V2" in warnings


def test_website_snapshot_serialization_export_and_no_ranking_dispatch() -> None:
    response = analyze_website_request(_website_payload())
    assert response["mode"] == "real_snapshot"
    assert response["analysis_available"] is False
    assert "Ranking unavailable" in response["ranking_notice"]
    assert len(response["snapshot"]) == 2
    assert response["export_filename"] == "nifty50_nse_snapshot_2026-08-07.csv"
    exported = pd.read_csv(StringIO(response["export_csv"]))
    assert tuple(exported.columns) == CANONICAL_COLUMNS
    assert len(exported) == 2
    assert "results" not in response
    json.dumps(response, allow_nan=False)
    for method in ("baseline_v1", "research_v2"):
        payload = _website_payload()
        payload["method"] = method
        assert analyze_website_request(payload)["analysis_available"] is False


def test_website_endpoint_accepts_snapshot_request() -> None:
    server = create_server(port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = json.dumps(_website_payload()).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/analyze",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
        assert payload["mode"] == "real_snapshot"
        assert payload["provenance"]["matched_count"] == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_existing_synthetic_modes_still_dispatch() -> None:
    baseline = analyze_website_request({
        "method": "baseline_v1", "use_synthetic_sample": True
    })
    research_v2 = analyze_website_request({
        "method": "research_v2", "use_synthetic_sample": True,
        "ranking_date": "2026-06-30",
    })
    assert len(baseline["results"]) == 18
    assert sum(row["eligible"] for row in research_v2["results"]) == 17


@pytest.mark.skipif(
    not (REAL_NIFTY.is_file() and REAL_BHAVCOPY.is_file()),
    reason="supplied external NSE/NIFTY files are not present",
)
def test_supplied_real_files_acceptance() -> None:
    result = load_nse_snapshot(REAL_NIFTY, REAL_BHAVCOPY)
    provenance = result.provenance
    assert len(result.snapshot) == 50
    assert provenance["constituent_count"] == 50
    assert provenance["matched_count"] == 50
    assert provenance["missing_count"] == 0
    assert provenance["duplicate_match_count"] == 0
    assert provenance["trade_date"] == "2026-08-07"
    assert provenance["bhavcopy_row_count"] == 3473
