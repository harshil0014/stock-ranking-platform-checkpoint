from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import pandas as pd
import numpy as np
import pytest

from stock_ranker.data_state import (
    DataStatePaths,
    acquire_refresh_lock,
    data_state_status,
    immutable_evidence_path,
    promote_candidate_bundle,
    read_accepted_state,
    release_refresh_lock,
    resolve_accepted_bundle_root,
    store_immutable_evidence,
    validate_download_payload,
)
from stock_ranker.live_market import (
    LEGACY_LIVE_BUNDLE_VERSION,
    ORDINARY_EQUITY_CONTRACT_VERSION,
    add_bse_traded_securities,
    apply_nse_prior_trade_fallback,
    write_live_bundle,
)
from stock_ranker import webapp


def _market(count: int = 10, *, ready: int = 10, trade_date: str = "2026-08-18") -> pd.DataFrame:
    rows = []
    for index in range(count):
        ticker = f"T{index:03d}"
        rows.append({
            "ticker": ticker, "company": f"Company {index}", "series": "EQ",
            "isin": f"INE{index:03d}A0100{index % 10}", "listing_date": "2010-01-01",
            "universe": "ALL NSE", "universe_source": "official test",
            "size_segment": "LARGE", "sector": "Test Sector", "industry": "Test Sector",
            "basic_industry": "Test Basic", "classification_status": "CLASSIFIED",
            "classification_source": "official test", "trade_date": trade_date,
            "snapshot_status": "AVAILABLE" if index < ready else "PRICE_UNAVAILABLE",
            "latest_price": 100.0 if index < ready else None, "previous_close": 99.0,
            "day_change": 1.0, "day_change_pct": 1.010101, "open": 99.0,
            "high": 101.0, "low": 98.0, "last_price": 100.0,
            "volume": 1000, "traded_value": 100000, "transaction_count": 50,
            "snapshot_source": "official test", "baseline_reason_code": "ELIGIBLE",
            "baseline_reason": "Eligible", "baseline_eligible": True,
            "v2_reason_code": "FUNDAMENTALS_UNAVAILABLE", "v2_reason": "Not in contract",
            "v2_eligible": False,
        })
    return pd.DataFrame(rows)


def _bundle(paths: DataStatePaths, name: str, market: pd.DataFrame, trade_date: str = "2026-08-18") -> Path:
    source = paths.root / f"{name}.source"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("official source\n", encoding="utf-8")
    output = paths.staging / name / "bundle"
    write_live_bundle(
        market, output,
        snapshot_metadata={
            "trade_date": trade_date, "matched_count": int(market["snapshot_status"].eq("AVAILABLE").sum()),
            "missing_count": int(market["snapshot_status"].ne("AVAILABLE").sum()),
            "freshness": "LATEST TRADING SNAPSHOT", "age_calendar_days": 1,
            "source": "official test", "source_filename": source.name,
            "inner_csv_filename": "test.csv", "source_sha256": "0" * 64,
        },
        source_files={"source": source},
        acquisition_started_at=datetime.now(timezone.utc).isoformat(),
        acquisition_completed_at=datetime.now(timezone.utc).isoformat(),
        history_attempted=0, history_acquired=len(market), history_failed=0,
        current_v2_ranking_date=trade_date,
        frozen_v2_evidence_fingerprint="frozen-v2",
    )
    return output


@pytest.mark.parametrize("payload,content_type", [
    (b"<html><title>Access Denied</title>" + b"x" * 100, "text/html"),
    (b"<!DOCTYPE html>error" + b"x" * 100, "application/octet-stream"),
])
def test_download_validation_rejects_html_error_pages(payload: bytes, content_type: str) -> None:
    with pytest.raises(ValueError, match="HTML"):
        validate_download_payload(payload, label="official source", content_type=content_type)


def test_immutable_evidence_is_idempotent_and_conflicts_fail(tmp_path: Path) -> None:
    paths = DataStatePaths.from_root(tmp_path)
    target = immutable_evidence_path(
        paths, provider="NSE", effective_date="2026-08-18", filename="bhavcopy.zip"
    )
    payload = b"valid exchange data" * 10
    assert store_immutable_evidence(target, payload)["status"] == "STORED"
    assert store_immutable_evidence(target, payload)["status"] == "ALREADY_PRESENT"
    with pytest.raises(ValueError, match="immutable evidence conflict"):
        store_immutable_evidence(target, b"different" * 20)


def test_refresh_lock_is_exclusive_and_owner_checked(tmp_path: Path) -> None:
    paths = DataStatePaths.from_root(tmp_path)
    lock = acquire_refresh_lock(paths)
    with pytest.raises(RuntimeError, match="another refresh"):
        acquire_refresh_lock(paths)
    release_refresh_lock(lock)
    assert not paths.lock.exists()


def test_candidate_promotion_is_atomic_resolvable_and_idempotent(tmp_path: Path) -> None:
    paths = DataStatePaths.from_root(tmp_path)
    candidate = _bundle(paths, "run-01", _market())
    pointer = promote_candidate_bundle(paths, candidate, accepted_at="2026-08-19T00:00:00+00:00")
    assert read_accepted_state(paths) == pointer
    resolved = resolve_accepted_bundle_root(paths.root)
    assert resolved.is_dir() and resolved.parent == paths.snapshots
    status = data_state_status(paths.root)
    assert status["trade_date"] == "2026-08-18"
    assert status["bundle_fingerprint"] == pointer["bundle_fingerprint"]

    repeat = _bundle(paths, "run-02", _market())
    repeated = promote_candidate_bundle(paths, repeat, accepted_at="2026-08-19T01:00:00+00:00")
    assert repeated["bundle_fingerprint"] == pointer["bundle_fingerprint"]
    assert not repeat.exists()


def test_rejected_partial_candidate_cannot_replace_last_known_good(tmp_path: Path) -> None:
    paths = DataStatePaths.from_root(tmp_path)
    accepted = promote_candidate_bundle(paths, _bundle(paths, "good", _market()))
    bad = _bundle(paths, "bad", _market(10, ready=2), trade_date="2026-08-19")
    with pytest.raises(ValueError, match="90% safety floor"):
        promote_candidate_bundle(paths, bad)
    assert read_accepted_state(paths)["bundle_fingerprint"] == accepted["bundle_fingerprint"]
    assert resolve_accepted_bundle_root(paths.root).name.endswith(accepted["bundle_fingerprint"])


def test_versioned_ordinary_equity_contract_migration_allows_audited_scope_cleanup(
    tmp_path: Path,
) -> None:
    paths = DataStatePaths.from_root(tmp_path)
    old_market = _market(10)
    old_market.loc[8:, "classification_status"] = "UNCLASSIFIED"
    old_bundle = _bundle(paths, "legacy", old_market)
    old_manifest_path = old_bundle / "bundle_manifest.json"
    old_manifest = json.loads(old_manifest_path.read_text(encoding="utf-8"))
    old_manifest["bundle_version"] = LEGACY_LIVE_BUNDLE_VERSION
    old_manifest_path.write_text(
        json.dumps(old_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    promote_candidate_bundle(paths, old_bundle)

    cleaned = old_market.iloc[:8].copy()
    cleaned["trade_date"] = "2026-08-19"
    cleaned["ranking_instrument_type"] = "ORDINARY_COMPANY_EQUITY"
    cleaned["ranking_universe_eligible"] = True
    cleaned["ranking_universe_reason_code"] = "ELIGIBLE_ORDINARY_EQUITY"
    cleaned["ranking_universe_contract"] = ORDINARY_EQUITY_CONTRACT_VERSION
    exclusions = pd.DataFrame([
        {
            "exchange": "NSE", "ticker": "FUND", "company": "Fund Unit", "series": "EQ",
            "isin": "INF001A01018", "ranking_universe_reason_code": "EXCLUDED_FUND_OR_ETF",
            "ranking_universe_reason": "Fund unit", "ranking_universe_contract": ORDINARY_EQUITY_CONTRACT_VERSION,
        },
        {
            "exchange": "BSE", "ticker": "RIGHT", "company": "Rights", "series": "R",
            "isin": "INE001A20010", "ranking_universe_reason_code": "EXCLUDED_RIGHTS_ENTITLEMENT",
            "ranking_universe_reason": "Rights entitlement", "ranking_universe_contract": ORDINARY_EQUITY_CONTRACT_VERSION,
        },
    ])
    source = paths.root / "clean.source"
    source.write_text("official source\n", encoding="utf-8")
    candidate = paths.staging / "clean" / "bundle"
    write_live_bundle(
        cleaned, candidate,
        snapshot_metadata={
            "trade_date": "2026-08-19", "matched_count": 8, "missing_count": 0,
            "freshness": "LATEST TRADING SNAPSHOT", "age_calendar_days": 1,
            "source": "official test", "source_filename": source.name,
            "inner_csv_filename": "test.csv", "source_sha256": "0" * 64,
        },
        source_files={"source": source},
        acquisition_started_at=datetime.now(timezone.utc).isoformat(),
        acquisition_completed_at=datetime.now(timezone.utc).isoformat(),
        history_attempted=0, history_acquired=8, history_failed=0,
        current_v2_ranking_date="2026-08-19", frozen_v2_evidence_fingerprint="frozen-v2",
        instrument_exclusions=exclusions,
    )
    pointer = promote_candidate_bundle(paths, candidate)
    assert pointer["checks"]["universe_count"] == 8
    resolved = resolve_accepted_bundle_root(paths.root)
    manifest = json.loads((resolved / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert manifest["ranking_universe_contract"] == ORDINARY_EQUITY_CONTRACT_VERSION
    assert (resolved / "ranking_universe_exclusions.csv").is_file()


def test_accepted_pointer_rejects_path_escape(tmp_path: Path) -> None:
    paths = DataStatePaths.from_root(tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.accepted_pointer.write_text(json.dumps({
        "state_version": "indian_equity_data_state_v1", "bundle_path": "../outside"
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="unsafe"):
        resolve_accepted_bundle_root(paths.root)


def test_website_background_refresh_uses_isolated_runner_and_returns_immediately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = tmp_path / "marketdata" / "runners" / "refresh_company_data.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("print('test')\n", encoding="utf-8")
    calls: list[tuple[list[str], dict[str, object]]] = []
    class FakeProcess:
        pid = 1234

        def poll(self):
            return None

        def wait(self):
            return 0

    sentinel = FakeProcess()

    def fake_popen(command: list[str], **kwargs: object):
        calls.append((command, kwargs))
        return sentinel

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    assert webapp.start_background_refresh(tmp_path) is sentinel
    assert len(calls) == 1
    assert str(runner) in calls[0][0]
    assert "--status-file" in calls[0][0]
    assert calls[0][1]["cwd"] == tmp_path.resolve()


def test_autonomous_runner_contains_no_credentials_or_paid_provider_dependency() -> None:
    source = (Path(__file__).parents[1] / "marketdata/runners/refresh_live_market.py").read_text(encoding="utf-8")
    lowered = source.lower()
    assert "api_key" not in lowered and "access_token" not in lowered
    assert "broker" not in lowered and "paid" not in lowered
    assert "nsearchives.nseindia.com" in source
    assert "www.bseindia.com/download/BhavCopy" in source
    assert "promote_candidate_bundle" in source


def test_bse_only_security_is_added_by_exact_isin_without_substitution(tmp_path: Path) -> None:
    nse = _market(1).rename(columns={"trade_date": "ignored_trade_date"})[[
        "ticker", "company", "series", "isin", "listing_date", "universe", "universe_source",
        "size_segment", "sector", "industry", "basic_industry", "classification_status",
        "classification_source",
    ]]
    nse["primary_exchange"] = "NSE"
    nse["exchange_security_id"] = nse["ticker"]
    nse["identity_status"] = "OFFICIAL_NSE_MASTER"
    nse_snapshot = _market(1)[[
        "ticker", "trade_date", "snapshot_status", "latest_price", "previous_close", "day_change",
        "day_change_pct", "open", "high", "low", "last_price", "volume", "traded_value",
        "transaction_count", "snapshot_source",
    ]]
    rows = []
    for scrip, isin, name in ((500001, nse.iloc[0]["isin"], "Dual Listed"), (504240, "INE913A01024", "DELTON CABLES LTD")):
        rows.append({
            "TradDt": "2026-08-18", "Sgmt": "CM", "Src": "BSE", "FinInstrmTp": "STK",
            "FinInstrmId": scrip, "ISIN": isin, "TckrSymb": str(scrip), "SctySrs": "X",
            "FinInstrmNm": name, "OpnPric": 100, "HghPric": 110, "LwPric": 95,
            "ClsPric": 105, "LastPric": 105, "PrvsClsgPric": 100, "TtlTradgVol": 10,
            "TtlTrfVal": 1050, "TtlNbOfTxsExctd": 2,
        })
    path = tmp_path / "bse.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    universe, snapshot, metadata = add_bse_traded_securities(nse, nse_snapshot, path)
    assert len(universe) == 2
    added = universe.loc[universe["primary_exchange"].eq("BSE")].iloc[0]
    assert added["ticker"] == "BSE-504240"
    assert added["isin"] == "INE913A01024"
    assert added["company"] == "DELTON CABLES LTD"
    assert added["identity_status"] == "OFFICIAL_BSE_TRADE_RECORD"
    assert metadata["cross_exchange_isin_overlap"] == 1
    assert snapshot.loc[snapshot["ticker"].eq("BSE-504240"), "latest_price"].iat[0] == 105


def test_bse_expansion_rejects_funds_trusts_government_rights_and_other_classes(tmp_path: Path) -> None:
    nse = _market(1)[[
        "ticker", "company", "series", "isin", "listing_date", "universe", "universe_source",
        "size_segment", "sector", "industry", "basic_industry", "classification_status",
        "classification_source",
    ]].copy()
    nse["primary_exchange"] = "NSE"
    nse["exchange_security_id"] = nse["ticker"]
    nse["identity_status"] = "OFFICIAL_NSE_MASTER"
    snapshot = _market(1)[[
        "ticker", "trade_date", "snapshot_status", "latest_price", "previous_close", "day_change",
        "day_change_pct", "open", "high", "low", "last_price", "volume", "traded_value",
        "transaction_count", "snapshot_source",
    ]].copy()
    identities = [
        (504240, "INE913A01024", "X", "Ordinary Company"),
        (590001, "INF001A01018", "X", "Fund Unit"),
        (590002, "IN0020240088", "G", "Government Security"),
        (590003, "INE183W23014", "IF", "Infrastructure Trust"),
        (590004, "INE0M8920010", "R", "Rights Entitlement"),
        (590005, "INE001A04016", "X", "Preference Security"),
        (590006, "INE224E01036", "X", "Alternate DVR"),
    ]
    rows = [{
        "TradDt": "2026-08-18", "Sgmt": "CM", "Src": "BSE", "FinInstrmTp": "STK",
        "FinInstrmId": scrip, "ISIN": isin, "TckrSymb": "GATECHDVR" if scrip == 590006 else str(scrip),
        "SctySrs": series, "FinInstrmNm": name, "OpnPric": 100, "HghPric": 110,
        "LwPric": 95, "ClsPric": 105, "LastPric": 105, "PrvsClsgPric": 100,
        "TtlTradgVol": 10, "TtlTrfVal": 1050, "TtlNbOfTxsExctd": 2,
    } for scrip, isin, series, name in identities]
    path = tmp_path / "bse_mixed.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    exclusions: list[pd.DataFrame] = []
    universe, _, metadata = add_bse_traded_securities(
        nse, snapshot, path, exclusion_sink=exclusions
    )
    added = universe.loc[universe["primary_exchange"].eq("BSE")]
    assert added["isin"].tolist() == ["INE913A01024"]
    assert metadata["bse_stock_rows"] == 7
    assert metadata["bse_ordinary_equity_rows"] == 1
    assert metadata["bse_excluded_nonordinary_rows"] == 6
    assert len(exclusions) == 1 and len(exclusions[0]) == 6
    assert set(exclusions[0]["ranking_universe_reason_code"]) == {
        "EXCLUDED_FUND_OR_ETF", "EXCLUDED_GOVERNMENT_OR_DEBT",
        "EXCLUDED_LISTED_TRUST_UNIT", "EXCLUDED_RIGHTS_ENTITLEMENT",
        "EXCLUDED_NON_ORDINARY_COMPANY_SECURITY", "EXCLUDED_ALTERNATE_SECURITY_CLASS",
    }


def test_exact_isin_bse_quote_fills_missing_nse_page_price_without_model_substitution(tmp_path: Path) -> None:
    nse = _market(1)[[
        "ticker", "company", "series", "isin", "listing_date", "universe", "universe_source",
        "size_segment", "sector", "industry", "basic_industry", "classification_status",
        "classification_source",
    ]].copy()
    nse["primary_exchange"] = "NSE"
    nse["exchange_security_id"] = nse["ticker"]
    nse["identity_status"] = "OFFICIAL_NSE_MASTER"
    snapshot = _market(1)[[
        "ticker", "trade_date", "snapshot_status", "latest_price", "previous_close", "day_change",
        "day_change_pct", "open", "high", "low", "last_price", "volume", "traded_value",
        "transaction_count", "snapshot_source",
    ]].copy()
    snapshot.loc[:, "latest_price"] = np.nan
    path = tmp_path / "bse.csv"
    pd.DataFrame([{
        "TradDt": "2026-08-18", "Sgmt": "CM", "Src": "BSE", "FinInstrmTp": "STK",
        "FinInstrmId": 500001, "ISIN": nse.iloc[0]["isin"], "TckrSymb": "500001",
        "SctySrs": "A", "FinInstrmNm": "Exact Dual Listing", "OpnPric": 100,
        "HghPric": 110, "LwPric": 95, "ClsPric": 105, "LastPric": 105,
        "PrvsClsgPric": 100, "TtlTradgVol": 10, "TtlTrfVal": 1050,
        "TtlNbOfTxsExctd": 2,
    }]).to_csv(path, index=False)
    _, combined, metadata = add_bse_traded_securities(nse, snapshot, path)
    row = combined.iloc[0]
    assert metadata["cross_exchange_price_fallbacks"] == 1
    assert row["latest_price"] == 105
    assert row["price_exchange"] == "BSE"
    assert row["price_identity_status"] == "EXACT_CROSS_EXCHANGE_ISIN"


def test_prior_nse_trade_fallback_is_exact_dated_and_missing_only(tmp_path: Path) -> None:
    universe = _market(2)[[
        "ticker", "company", "series", "isin", "listing_date", "universe", "universe_source",
        "size_segment", "sector", "industry", "basic_industry", "classification_status",
        "classification_source",
    ]].copy()
    universe["primary_exchange"] = "NSE"
    snapshot = _market(2)[[
        "ticker", "trade_date", "snapshot_status", "latest_price", "previous_close", "day_change",
        "day_change_pct", "open", "high", "low", "last_price", "volume", "traded_value",
        "transaction_count", "snapshot_source",
    ]].copy()
    snapshot.loc[snapshot["ticker"].eq("T001"), "latest_price"] = np.nan
    path = tmp_path / "prior.csv"
    pd.DataFrame([
        {
            "SYMBOL": "T000", "SERIES": "EQ", "DATE1": "17-Aug-2026", "PREV_CLOSE": 90,
            "OPEN_PRICE": 91, "HIGH_PRICE": 102, "LOW_PRICE": 89, "LAST_PRICE": 99,
            "CLOSE_PRICE": 99, "TTL_TRD_QNTY": 50, "TURNOVER_LACS": 1,
            "NO_OF_TRADES": 4,
        },
        {
            "SYMBOL": "T001", "SERIES": "EQ", "DATE1": "17-Aug-2026", "PREV_CLOSE": 70,
            "OPEN_PRICE": 71, "HIGH_PRICE": 82, "LOW_PRICE": 69, "LAST_PRICE": 80,
            "CLOSE_PRICE": 80, "TTL_TRD_QNTY": 60, "TURNOVER_LACS": 2,
            "NO_OF_TRADES": 5,
        },
    ]).to_csv(path, index=False)
    output, metadata = apply_nse_prior_trade_fallback(universe, snapshot, path)
    unchanged = output.loc[output["ticker"].eq("T000")].iloc[0]
    filled = output.loc[output["ticker"].eq("T001")].iloc[0]
    assert unchanged["latest_price"] == 100
    assert unchanged["trade_date"] == "2026-08-18"
    assert filled["latest_price"] == 80
    assert filled["trade_date"] == "2026-08-17"
    assert filled["snapshot_status"] == "AVAILABLE_PRIOR_TRADE"
    assert filled["price_identity_status"] == "EXACT_SYMBOL_SERIES_PRIOR_TRADE"
    assert metadata["fallback_count"] == 1
