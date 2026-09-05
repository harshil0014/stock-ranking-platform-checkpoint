from __future__ import annotations

from stock_ranker.live_website import live_stock
from stock_ranker.screener_statements import load_screener_statement_history
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
        "reason": "No accepted hash-pinned standalone Screener workbook matches this exact ticker and ISIN.",
    }


def test_latest_accepted_bundle_workbook_is_discovered_outside_legacy_batches() -> None:
    history = load_screener_statement_history("ZSARACOM", "INE967G01019")

    assert history["available"] is True
    assert history["workbook_sha256"] == "d19771b3512abbb48419405b134cc9408c43e82932e067fc997c322753c75c1c"
    assert history["accepted_bundle_fingerprint"] == "3277812548c02d401ab2cf032066203ba4a6234a020d94ae43e3b7f8994552d8"
    assert history["reporting_basis"] == "STANDALONE"


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
