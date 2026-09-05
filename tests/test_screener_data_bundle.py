from __future__ import annotations

from zipfile import ZipFile

import pandas as pd

from stock_ranker.screener_data_bundle import (
    _identity_indexes,
    _resolve_workbook_identity,
    _safe_members,
    accept_screener_data_bundle,
    build_coverage_audit,
    build_missing_history_and_next_batch,
    load_accepted_screener_data_bundle,
    merge_history_incrementally,
    merge_screener_market_exports,
)
from stock_ranker.screener_historical_fundamentals import sha256_file


def _universe() -> pd.DataFrame:
    return pd.DataFrame([
        {"ticker": "AAA", "company": "Alpha Limited", "isin": "INE000A01001",
         "primary_exchange": "NSE", "exchange_security_id": "AAA"},
        {"ticker": "BBB", "company": "Beta Limited", "isin": "INE000A01002",
         "primary_exchange": "NSE", "exchange_security_id": "BBB"},
    ])


def _vendor(name: str, isin: str, *, industry: str = "Chemicals") -> dict[str, object]:
    return {"Name": name, "BSE Code": "500001", "NSE Code": name.split()[0],
            "ISIN Code": isin, "Industry Group": "Materials", "Industry": industry,
            "Current Price": 100.0}


def test_market_exports_join_only_by_exact_clean_isin_and_quarantine_conflicts() -> None:
    operational = pd.DataFrame([
        _vendor("Alpha Limited", "INE000A01001"),
        _vendor("Outside Limited", "INE999A01001"),
    ])
    snapshot = pd.DataFrame([
        _vendor("Renamed Alpha", "INE000A01001"),
        _vendor("Beta Limited", "INE000A01002"),
    ])
    merged, conflicts = merge_screener_market_exports(_universe(), operational, snapshot)
    assert len(merged) == 2
    assert merged.set_index("isin").loc["INE000A01001", "market_merge_status"] == "CONFLICT_QUARANTINED"
    assert set(conflicts["conflict_type"]) == {
        "CROSS_EXPORT_FIELD_CONFLICT", "OUTSIDE_CLEAN_ORDINARY_EQUITY_UNIVERSE"
    }


def test_numbered_export_filename_resolves_only_through_unique_exact_market_code() -> None:
    market = _universe()
    market["operational__NSE Code"] = ["AAA", "BBB"]
    market["snapshot__NSE Code"] = ["AAA", "BBB"]
    names, checklist, codes, _ = _identity_indexes(market, pd.DataFrame())
    isin, method = _resolve_workbook_identity(
        filename="0042_AAA_Legacy Export Name.xlsx",
        workbook_company="OLDER LEGAL NAME LTD",
        name_index=names,
        checklist_names=checklist,
        code_index=codes,
    )
    assert isin == "INE000A01001"
    assert method == "EXACT_NUMBERED_FILENAME_CODE_TO_ISIN"


def test_incremental_history_ignores_only_serialization_noise_and_quarantines_change() -> None:
    existing = pd.DataFrame([{
        "isin": "INE000A01001", "period_end": "2024-03-31T00:00:00+00:00",
        "prior_period_end": "2023-03-31", "roce": 0.2, "debt_to_equity": 0.3,
        "current_pat": 8241.819999999998, "prior_pat": 7000.0,
        "source_workbook_sha256": "old",
    }])
    harmless = existing.copy()
    harmless["period_end"] = "2024-03-31"
    harmless["current_pat"] = 8241.82
    harmless["source_workbook_sha256"] = "same-data"
    combined, conflicts = merge_history_incrementally(existing, harmless)
    assert len(combined) == 1
    assert conflicts.empty

    changed = harmless.copy()
    changed["current_pat"] = 8242.0
    combined, conflicts = merge_history_incrementally(existing, changed)
    assert len(combined) == 1
    assert conflicts["conflict_type"].tolist() == [
        "INCOMING_DISAGREES_WITH_ACCEPTED_HISTORY"
    ]


def test_next_batch_prioritizes_earliest_dates_and_excludes_supplied_workbooks() -> None:
    market = _universe()
    market["operational__NSE Code"] = ["AAA", "BBB"]
    market["snapshot__NSE Code"] = ["AAA", "BBB"]
    availability = pd.DataFrame([
        {"isin": "INE000A01001", "ranking_date": "2022-08-05", "pit_available": True},
        {"isin": "INE000A01002", "ranking_date": "2022-08-05", "pit_available": True},
        {"isin": "INE000A01002", "ranking_date": "2023-08-07", "pit_available": True},
    ])
    audit = pd.DataFrame([{"isin": "INE000A01002"}])
    missing, next_batch = build_missing_history_and_next_batch(
        market, pd.DataFrame(columns=["isin"]), audit, availability
    )
    assert len(missing) == 2
    assert next_batch["ISIN"].tolist() == ["INE000A01001"]
    assert next_batch["historical_dates_helped"].tolist() == ["2022-08-05"]


def test_recursive_archive_member_validation_rejects_traversal(tmp_path) -> None:
    good = tmp_path / "good.zip"
    with ZipFile(good, "w") as archive:
        archive.writestr("nested/export/company.xlsx", b"safe-placeholder")
    with ZipFile(good) as archive:
        assert [item.filename for item in _safe_members(archive)] == [
            "nested/export/company.xlsx"
        ]
    bad = tmp_path / "bad.zip"
    with ZipFile(bad, "w") as archive:
        archive.writestr("../escape.xlsx", b"unsafe")
    with ZipFile(bad) as archive:
        try:
            _safe_members(archive)
        except ValueError as exc:
            assert "unsafe archive path" in str(exc)
        else:
            raise AssertionError("archive traversal was accepted")


def test_coverage_audit_uses_clean_universe_as_explicit_denominator() -> None:
    market = _universe()
    market["operational_exact_isin_match"] = [True, False]
    market["snapshot_exact_isin_match"] = [True, True]
    market["market_merge_status"] = ["ACCEPTED", "ACCEPTED"]
    market["operational__Current Price"] = [100.0, None]
    market["snapshot__Current Price"] = [101.0, 50.0]
    audit = pd.DataFrame([{"file_status": "ACCEPTED", "isin": "INE000A01001"}])
    history = pd.DataFrame([{"isin": "INE000A01001"}])
    pit = pd.DataFrame([{"ranking_date": "2022-08-05", "pit_fundamental_count": 1}])
    result = build_coverage_audit(market, audit, history, pit)
    row = result.loc[
        result["category"].eq("FIELD_ANY_EXPORT")
        & result["field"].eq("Current Price")
    ].iloc[0]
    assert row["covered_count"] == 2
    assert row["denominator"] == 2
    assert row["coverage_pct"] == 100.0


def test_accepted_state_is_written_only_after_terminal_hash_validation(tmp_path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    artifact = bundle / "normalized_history.csv"
    artifact.write_text("isin\nINE000A01001\n", encoding="utf-8", newline="\n")
    summary = {
        "artifact_hashes": {artifact.name: sha256_file(artifact)},
        "workbooks_quarantined": 0,
        "history_conflicts": 0,
        "bundle_fingerprint": "a" * 64,
        "clean_universe_count": 1,
        "normalized_history_issuers": 1,
        "pit_counts": {"2022-08-05": 1},
    }
    import json
    (bundle / "bundle_summary.json").write_text(
        json.dumps(summary), encoding="utf-8", newline="\n"
    )
    (bundle / "artifact_inventory.json").write_text("[]\n", encoding="utf-8", newline="\n")
    state_path = tmp_path / "accepted_state.json"
    state = accept_screener_data_bundle(bundle, state_path)
    assert state["bundle_fingerprint"] == "a" * 64
    assert state_path.is_file()

    artifact.write_text("tampered\n", encoding="utf-8", newline="\n")
    try:
        accept_screener_data_bundle(bundle, state_path)
    except ValueError as exc:
        assert "hash mismatch" in str(exc)
    else:
        raise AssertionError("tampered bundle was accepted")


def test_quarantined_workbooks_require_explicit_partial_bundle_acceptance(tmp_path) -> None:
    bundle = tmp_path / "partial-bundle"
    bundle.mkdir()
    artifact = bundle / "normalized_history.csv"
    artifact.write_text("isin\nINE000A01001\n", encoding="utf-8", newline="\n")
    summary = {
        "artifact_hashes": {artifact.name: sha256_file(artifact)},
        "workbooks_quarantined": 2,
        "history_conflicts": 0,
        "bundle_fingerprint": "b" * 64,
        "clean_universe_count": 2,
        "normalized_history_issuers": 1,
        "pit_counts": {"2022-08-05": 1},
    }
    import json
    (bundle / "bundle_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (bundle / "artifact_inventory.json").write_text("[]\n", encoding="utf-8")
    state_path = tmp_path / "accepted_state.json"
    try:
        accept_screener_data_bundle(bundle, state_path)
    except ValueError as exc:
        assert "explicit acceptance" in str(exc)
    else:
        raise AssertionError("partial bundle was accepted without explicit authorization")
    state = accept_screener_data_bundle(
        bundle, state_path, allow_quarantined_workbooks=True
    )
    assert state["quarantined_workbooks"] == 2


def test_accepted_bundle_reader_validates_and_loads_product_artifacts(tmp_path) -> None:
    provider = tmp_path / "provider"
    bundle = provider / "batches" / "accepted"
    bundle.mkdir(parents=True)
    pd.DataFrame([{
        "ticker": "AAA", "company": "Alpha", "isin": "INE000A01001",
        "primary_exchange": "NSE", "market_merge_status": "ACCEPTED",
    }]).to_csv(bundle / "market_master.csv", index=False)
    pd.DataFrame([{"isin": "INE000A01001", "period_end": "2025-03-31"}]).to_csv(bundle / "normalized_history.csv", index=False)
    pd.DataFrame([{"isin": "INE000A01001", "file_status": "ACCEPTED"}]).to_csv(bundle / "workbook_audit.csv", index=False)
    hashes = {name: sha256_file(bundle / name) for name in (
        "market_master.csv", "normalized_history.csv", "workbook_audit.csv",
    )}
    summary = {
        "schema_version": "screener_incremental_exact_isin_bundle_v1",
        "source_observed_at": "2026-09-01T00:00:00+00:00",
        "artifact_hashes": hashes, "workbooks_quarantined": 0,
        "history_conflicts": 0, "bundle_fingerprint": "e" * 64,
        "clean_universe_count": 1, "normalized_history_issuers": 1,
        "pit_counts": {},
    }
    import json
    (bundle / "bundle_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (bundle / "artifact_inventory.json").write_text("[]\n", encoding="utf-8")
    state_path = provider / "accepted_state.json"
    accept_screener_data_bundle(bundle, state_path)
    accepted = load_accepted_screener_data_bundle(state_path)
    assert accepted.fingerprint == "e" * 64
    assert accepted.market_master["isin"].tolist() == ["INE000A01001"]
    assert accepted.normalized_history["period_end"].tolist() == ["2025-03-31"]
