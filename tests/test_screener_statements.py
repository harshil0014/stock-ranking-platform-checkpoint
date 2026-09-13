from __future__ import annotations

from pathlib import Path
from stock_ranker.screener_data_bundle import load_accepted_screener_data_bundle

from stock_ranker.live_website import live_stock
from stock_ranker.screener_statements import (
    accepted_screener_workbook_isins,
    load_screener_statement_history,
)
from stock_ranker.web_assets import APP_JS, INDEX_HTML, STYLES_CSS


def test_validated_reliance_screener_history_is_exposed_by_exact_identity() -> None:
    history = load_screener_statement_history("RELIANCE", "INE002A01018")

    assert history["available"] is True
    assert history["reporting_basis"] == "STANDALONE"
    assert history["workbook_version"] == "2.1"
    assert history["workbook_sha256"] == "5ac2fc60f23e4d651d625c0317c1de2f8d10d563c01101fbd01e1902ec3acfcf"
    assert len(history["profit_loss"]["periods"]) == 10
    assert history["profit_loss"]["rows"][0]["label"] == "Sales"
    assert history["profit_loss"]["rows"][0]["values"][-1] == 504026.0
    assert len(history["quarterly_results"]["periods"]) == 10


def test_screener_history_never_substitutes_an_identity() -> None:
    history = load_screener_statement_history("RELIANCE", "INE000000000")

    assert history == {
        "available": False,
        "status": "NO_VALIDATED_SCREENER_HISTORY",
        "reason": "No accepted hash-pinned standalone Screener workbook matches this exact ISIN.",
    }


def test_latest_accepted_bundle_workbook_is_discovered_outside_legacy_batches() -> None:
    history = load_screener_statement_history("ZSARACOM", "INE967G01019")

    assert history["available"] is True
    assert history["workbook_sha256"] == "d19771b3512abbb48419405b134cc9408c43e82932e067fc997c322753c75c1c"
    accepted = load_accepted_screener_data_bundle(Path(__file__).parents[1] / "data/company_facts/providers/screener_bundle/accepted_state.json")
    assert history["accepted_bundle_fingerprint"] == accepted.fingerprint
    assert history["reporting_basis"] == "STANDALONE"


def test_statement_index_includes_every_accepted_exact_isin_workbook() -> None:
    identities = accepted_screener_workbook_isins()

    assert "INE002A01018" in identities
    accepted = load_accepted_screener_data_bundle(Path(__file__).parents[1] / "data/company_facts/providers/screener_bundle/accepted_state.json")
    accepted_rows = accepted.workbook_audit.loc[
        accepted.workbook_audit["file_status"].eq("ACCEPTED")
    ]
    market_isins = frozenset(
        accepted.market_master["isin"].dropna().astype(str)
    )
    expected = frozenset(
        isin
        for row in accepted_rows.to_dict("records")
        if (isin := str(row.get("isin", "")).upper()) in market_isins
        and (
            accepted.root
            / "workbooks"
            / isin
            / f"{row.get('workbook_sha256', '')}.xlsx"
        ).is_file()
    )
    assert expected <= identities


def test_live_stock_includes_same_validated_statement_history() -> None:
    data = live_stock("RELIANCE")

    assert data["screener_financial_history"]["available"] is True
    assert data["screener_financial_history"]["isin"] == data["stock"]["isin"]
    assert data["research_v2"]["score"] is not None


def test_company_page_has_dense_research_terminal_sections() -> None:
    for section in (
        "companySummary", "companyChart", "companyAnalysis", "companyPeers",
        "companyQuarters", "companyProfitLoss", "companyBalanceSheet",
        "companyCashFlow", "companyRatios", "companyShareholding", "companyDocuments",
    ):
        assert f'id="{section}"' in INDEX_HTML
    assert "renderStatementTable" in APP_JS
    assert "Screener Premium standalone history" in APP_JS
    assert "statement-table" in STYLES_CSS
    assert "linear-gradient" not in STYLES_CSS.split("/* Dense, data-first research terminal presentation. */")[-1]
