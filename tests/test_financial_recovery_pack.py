"""Fictional collector fixtures never enter product evidence."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

RUNNERS = Path(__file__).resolve().parents[1] / "marketdata/runners"
sys.path.insert(0, str(RUNNERS))
spec = importlib.util.spec_from_file_location("financial_recovery_pack_test", RUNNERS / "financial_recovery_pack.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def create_pack(tmp_path):
    gaps, pack = tmp_path / "gaps", tmp_path / "pack"
    gaps.mkdir()
    row = {"ticker": "BSE-500001", "company": "Fictional", "isin": "INE001A01010", "primary_exchange": "BSE", "exchange_security_id": "500001"}
    for category in module.CATEGORIES:
        (gaps / f"remaining_missing_{category}.csv").write_bytes(module.csv_bytes([row], list(row)))
    module.init_pack(gaps, pack)
    return gaps, pack


def test_target_intersection_frozen_and_no_company_name_matching(tmp_path):
    gaps, pack = create_pack(tmp_path)
    first = (pack / "targets.csv").read_bytes()
    module.init_pack(gaps, pack)
    assert first == (pack / "targets.csv").read_bytes()
    assert len(module.targets(pack)) == 1
    (pack / "targets.csv").write_bytes(first.replace(b"INE001A01010", b"INE002A01010"))
    with pytest.raises(ValueError, match="hash mismatch"):
        module.targets(pack)


@pytest.mark.parametrize("url", ["http://www.bseindia.com/a", "https://bseindia.com.evil.test/a", "https://user@www.bseindia.com/a", "file:///tmp/data", "https://127.0.0.1/a"])
def test_source_allowlist_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        module.official_url(url)


def test_immutable_bytes_reject_overwrite(tmp_path):
    path = tmp_path / "raw.bin"
    module.immutable(path, b"official fixture")
    module.immutable(path, b"official fixture")
    with pytest.raises(ValueError, match="conflict"):
        module.immutable(path, b"changed")


def test_offline_never_fetches_missing_attachment(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "build_opener", lambda *a: pytest.fail("network attempted"))
    with pytest.raises(OSError, match="OFFLINE_CACHE_MISS"):
        module.fetch(tmp_path, "https://www.bseindia.com/a", offline=True)


def test_navigation_links_are_not_company_filings():
    parser = module.Links()
    parser.feed('<a href="/companies-listing/xbrl-information">info</a><a href="/RSS/feed.xml">rss</a><a href="/XBRLFILES/a.html">filing</a><a href="/results.pdf">pdf</a>')
    assert parser.urls == ["/XBRLFILES/a.html", "/results.pdf"]


def test_resume_done_no_network_and_report_deterministic(tmp_path, monkeypatch):
    _, pack = create_pack(tmp_path)
    monkeypatch.setattr(module, "fetch", lambda *a, **k: (b"<html>dynamic form</html>", {"url": "https://www.bseindia.com/a", "path": "raw/test", "sha256": module.sha(b"body")}))
    module.immutable(pack / "raw/test", b"body")
    module.collect(pack, 1)
    # Mark second independent task complete for an isolated resume fixture.
    progress = json.loads((pack / "progress.json").read_text())
    progress["INE001A01010:shareholding"] = {"done": True, "status": "REVIEW_REQUIRED"}
    module.atomic_write_json(pack / "progress.json", progress)
    monkeypatch.setattr(module, "fetch", lambda *a, **k: pytest.fail("completed task repeated"))
    module.collect(pack, 2)
    assert module.report(pack) == module.report(pack)
    assert module.report(pack)["accepted_financial_rows"] == 0
    (pack / "raw/test").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="raw evidence changed"):
        module.report(pack)


def test_quarantine_isin_conflict_without_candidate(tmp_path, monkeypatch):
    _, pack = create_pack(tmp_path)
    target = module.targets(pack)[0]
    catalogue = {"Table": [{"FLD_ScripCode": "500001", "EndDate": "2026-06-30", "XBRLAttachment": "/XBRLFILES/test.html"}]}
    bodies = {target["financial_url"]: b"<html></html>", target["shareholding_url"]: json.dumps(catalogue).encode(),
              "https://www.bseindia.com/XBRLFILES/test.html": b"<td>INE002A01010</td>"}
    def fake_fetch(pack, url, **kwargs):
        body = bodies[url]
        return body, {"url": url, "sha256": module.sha(body), "path": "unused"}
    monkeypatch.setattr(module, "fetch", fake_fetch)
    result = module.collect(pack, 2)
    assert result["INE001A01010:shareholding"]["status"] == "QUARANTINED"
    assert "candidate_fact" not in result["INE001A01010:shareholding"]


def test_financial_catalogue_preserves_clock_without_promoting(tmp_path, monkeypatch):
    _, pack = create_pack(tmp_path)
    catalogue = {"Table": [{"Scrip_cd": 500001, "XMLName": "IF/test.html", "Fld_CreateDate": "2026-08-01T16:00:00"}]}
    def fake_fetch(pack, url, **kwargs):
        data = json.dumps(catalogue).encode() if "Corp_FinanceResult" in url else b"<td>INE001A01010</td>"
        return data, {"url": url, "sha256": module.sha(data), "path": "unused"}
    monkeypatch.setattr(module, "fetch", fake_fetch)
    result = module.collect_financial(pack, 1)
    assert result["filings"] == 1 and not result["auto_promotion"]
    entry = json.loads((pack / "financial_discovery_v2.json").read_text())["INE001A01010"]
    assert entry["filings"][0]["catalogue_row"]["Fld_CreateDate"] == "2026-08-01T16:00:00"
    assert "available_at" not in entry["filings"][0]
    monkeypatch.setattr(module, "fetch", lambda *a, **k: pytest.fail("resume repeated request"))
    assert module.collect_financial(pack, 1) == result


def test_financial_catalogue_code_conflict_quarantined(tmp_path, monkeypatch):
    _, pack = create_pack(tmp_path)
    monkeypatch.setattr(module, "fetch", lambda *a, **k: (b'{"Table":[{"Scrip_cd":500002}]}', {}))
    module.collect_financial(pack, 1)
    row = json.loads((pack / "financial_discovery_v2.json").read_text())["INE001A01010"]
    assert row["status"] == "QUARANTINED" and not row["filings"]


def test_financial_offline_flag_reaches_fetch(tmp_path, monkeypatch):
    _, pack = create_pack(tmp_path)
    calls = []
    def cached(pack, url, **kwargs):
        calls.append(kwargs["offline"])
        return b'{"Table":[]}', {}
    monkeypatch.setattr(module, "fetch", cached)
    module.collect_financial(pack, 1, offline=True)
    assert calls == [True]


def test_period_missing_start_is_unknown_not_imputed():
    from normalize_recovery_review import classify_period
    assert classify_period(None, "2026-03-31", False) == "UNKNOWN"
    assert classify_period(None, "2026-03-31", True) == "INSTANT"
    assert classify_period("2025-04-01", "2026-03-31", False) == "ANNUAL"
    assert classify_period("2026-01-01", "2026-03-31", False) == "QUARTERLY"
    with pytest.raises(ValueError, match="duration"):
        classify_period("2026-04-01", "2026-03-31", False)


def test_independent_numeric_diagnostic_does_not_fill_dashes():
    from check_recovery_numeric_transforms import simple_number
    from decimal import Decimal
    assert simple_number("1,234.50", "5", "-") == Decimal("-123450000")
    assert simple_number("0", "5", None) == 0
    for text in ("-", "", "N/A", "(123)"):
        assert simple_number(text, None, None) is None


def test_nse_exact_catalogue_identity_and_financial_type(tmp_path, monkeypatch):
    gaps, pack = tmp_path / "gaps", tmp_path / "pack"
    gaps.mkdir()
    identity = {"ticker": "TEST", "company": "Fictional", "isin": "INE001A01010", "primary_exchange": "NSE", "exchange_security_id": "TEST"}
    for category in module.CATEGORIES:
        (gaps / f"remaining_missing_{category}.csv").write_bytes(module.csv_bytes([identity], list(identity)))
    module.init_pack(gaps, pack)
    row = {"symbol": "TEST", "type": "Integrated Filing- Financials", "ixbrl": "https://nsearchives.nseindia.com/test.html"}
    catalogue = tmp_path / "catalogue.json"
    catalogue.write_text(json.dumps({"data": [row, {**row, "symbol": "OTHER"}, {**row, "type": "Integrated Filing- Governance"}]}))
    catalogue.with_suffix(".metadata.json").write_text(json.dumps({"sha256": module.sha(catalogue.read_bytes()), "source_url": "https://www.nseindia.com/api/test"}))
    calls = []
    def fake_fetch(pack, url, **kwargs):
        calls.append(url)
        return b"<td>INE002A01010</td>", {"url": url, "sha256": "fixture"}
    monkeypatch.setattr(module, "fetch", fake_fetch)
    module.collect_nse_catalogue(pack, catalogue, 10)
    assert calls == [row["ixbrl"]]
    progress = json.loads((pack / "financial_discovery_v2.json").read_text())
    assert progress[identity["isin"]]["filings"][0]["status"] == "QUARANTINED_ISIN_CONFLICT"
    module.collect_nse_catalogue(pack, catalogue, 10)
    assert len(calls) == 1
    catalogue.write_text("{}")
    with pytest.raises(ValueError, match="catalogue hash"):
        module.collect_nse_catalogue(pack, catalogue, 10)


def test_recovery_audit_is_deterministic_and_never_promotes(tmp_path):
    from audit_financial_recovery_pack import audit
    _, pack = create_pack(tmp_path)
    for name in ("financial_discovery_v2.json", "progress.json", "raw_inventory.json"):
        (pack / name).write_text("{}")
    first = audit(pack)
    assert first == audit(pack)
    assert first["targets"] == 1 and first["accepted_new_facts"] == 0
    assert first["auto_promotion"] is False
    assert first["accounting_validation_complete"] is False
    (pack / "raw_inventory.json").write_text(json.dumps({"../outside": {"bytes": 1, "sha256": "bad"}}))
    with pytest.raises(ValueError, match="escapes"):
        audit(pack)
