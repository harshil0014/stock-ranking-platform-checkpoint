"""Resumable official evidence collection. Never writes accepted product state.

init freezes the actual four-way gap intersection; collect uses one worker;
report validates stored hashes and emits review/quarantine inventories.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.error import HTTPError
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from stock_ranker.data_state import atomic_write_json
from stock_ranker.exchange_backbone import FINANCIAL_COLUMNS, SHAREHOLDING_COLUMNS
from acquire_exchange_backbone import validate_bse_shareholding_identity, parse_shareholding_inline_xbrl

CATEGORIES = ("annual_financials", "quarterly_financials", "balance_sheet", "cash_flow")
VERSION = "official_recovery_pack_v1"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def official_url(url):
    p = urlsplit(url)
    if (p.scheme != "https" or p.username or p.password or p.port not in (None, 443)
            or not any(p.hostname == d or (p.hostname or "").endswith("." + d)
                       for d in ("bseindia.com", "nseindia.com"))):
        raise ValueError("nonofficial or unsafe source URL")
    return url


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def csv_bytes(rows, columns):
    import io
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def immutable(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"immutable evidence conflict: {path.name}")
        return
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_bytes(data)
    temp.replace(path)


def init_pack(gaps, pack):
    tables = []
    for category in CATEGORIES:
        with (gaps / f"remaining_missing_{category}.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        if len({r["isin"] for r in rows}) != len(rows):
            raise ValueError("duplicate target identity")
        tables.append({r["isin"]: r for r in rows})
    identities = set.intersection(*(set(t) for t in tables))
    targets = []
    for isin in sorted(identities):
        r = tables[0][isin]
        keys = ("ticker", "company", "isin", "primary_exchange", "exchange_security_id")
        if any(any(t[isin][k] != r[k] for k in keys) for t in tables):
            raise ValueError("target identity conflict across gap lists")
        if not re.fullmatch(r"IN[A-Z0-9]{10}", isin):
            raise ValueError("invalid ISIN")
        code = r["exchange_security_id"]
        if r["primary_exchange"] == "BSE":
            if not re.fullmatch(r"\d{6}", code):
                raise ValueError("BSE code is not exactly six digits")
            financial = "https://www.bseindia.com/corporates/Comp_Results.aspx?" + urlencode({"Code": code})
            ownership = "https://api.bseindia.com/BseIndiaAPI/api/Corp_Shareholding_ng/w?" + urlencode({"scripcode": code, "flag": 0, "indtype": ""})
        elif r["primary_exchange"] == "NSE":
            financial = "https://www.nseindia.com/companies-listing/corporate-filings-financial-results?" + urlencode({"symbol": r["ticker"], "tabIndex": "equity"})
            ownership = "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern?" + urlencode({"symbol": r["ticker"], "tabIndex": "equity"})
        else:
            raise ValueError("unsupported exchange")
        targets.append({**{k: r[k] for k in keys}, "financial_url": financial, "shareholding_url": ownership})
    body = csv_bytes(targets, [*keys, "financial_url", "shareholding_url"])
    immutable(pack / "targets.csv", body)
    manifest = {"version": VERSION, "target_sha256": sha(body), "target_count": len(targets),
                "source_hashes": {c: sha((gaps / f"remaining_missing_{c}.csv").read_bytes()) for c in CATEGORIES},
                "auto_promotion": False}
    immutable(pack / "targets_manifest.json", (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode())
    return manifest


def targets(pack):
    manifest = json.loads((pack / "targets_manifest.json").read_text())
    if sha((pack / "targets.csv").read_bytes()) != manifest["target_sha256"]:
        raise ValueError("frozen target hash mismatch")
    with (pack / "targets.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def seed_probe(pack, source):
    """Reuse retained official probe bytes; identity is still checked by collect."""
    imported = 0
    for r in targets(pack):
        if r["primary_exchange"] != "BSE":
            continue
        raw = source / "raw" / "bse_shareholding"
        catalogue = raw / (r["exchange_security_id"] + ".json")
        if not catalogue.is_file():
            continue
        items = [(catalogue, r["shareholding_url"], None, "application/json")]
        for row in json.loads(catalogue.read_text()).get("Table", []):
            attachment = row.get("XBRLAttachment")
            if not attachment:
                continue
            path = raw / Path(urlsplit(attachment).path).name
            meta = path.with_suffix(path.suffix + ".metadata.json")
            if path.is_file() and meta.is_file():
                record = json.loads(meta.read_text())
                if sha(path.read_bytes()) != record["sha256"]:
                    raise ValueError("seed raw hash mismatch")
                items.append((path, record["source_url"], record.get("retrieved_at"), "text/html"))
        for path, url, retrieved, content_type in items:
            official_url(url)
            cache = pack / "requests" / (sha(url.encode()) + ".json")
            if cache.exists():
                continue
            body = path.read_bytes()
            relative = Path("raw") / (sha(body) + ".bin")
            immutable(pack / relative, body)
            atomic_write_json(cache, {"url": url, "final_url": url, "sha256": sha(body),
                "path": relative.as_posix(), "content_type": content_type,
                "retrieved_at": retrieved, "seed_file": str(path.resolve()),
                "retrieval_time_known": retrieved is not None})
            imported += 1
    return {"cached_sources_imported": imported, "auto_promotion": False}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"a", "iframe"}:
            value = attrs.get("href") or attrs.get("src") or ""
            path = urlsplit(value).path.lower()
            if (path.endswith((".xml", ".pdf")) or ("/ixbrl/" in path or "/xbrlfiles/" in path) and path.endswith((".html", ".htm"))) and "/rss/" not in path and "{{" not in value:
                self.urls.append(value)


def fetch(pack, url, *, timeout=30, offline=False):
    official_url(url)
    key = sha(url.encode())
    meta = pack / "requests" / (key + ".json")
    if meta.exists():
        record = json.loads(meta.read_text())
        path = pack / record["path"]
        data = path.read_bytes()
        if sha(data) != record["sha256"]:
            raise ValueError("cached response hash mismatch")
        return data, record
    if offline:
        raise OSError("OFFLINE_CACHE_MISS: no network request made")
    # Serial calls only; successful cached requests incur no network traffic.
    time.sleep(2)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/html,application/xml,*/*",
                                "Referer": "https://www.bseindia.com/" if "bseindia.com" in urlsplit(url).hostname else "https://www.nseindia.com/"})
    with build_opener(OfficialRedirect()).open(req, timeout=timeout) as response:
        official_url(response.url)
        data = response.read(25_000_001)
        if not data or len(data) > 25_000_000:
            raise ValueError("empty or oversized response")
        path = Path("raw") / (sha(data) + ".bin")
        immutable(pack / path, data)
        record = {"url": url, "final_url": response.url, "sha256": sha(data), "path": path.as_posix(),
                  "content_type": response.headers.get("Content-Type", ""), "retrieved_at": utc()}
        atomic_write_json(meta, record)
        return data, record


def collect(pack, limit, offline=False, family_filter=None):
    rows = targets(pack)
    progress_path = pack / "progress.json"
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
    attempted = 0
    for r in sorted(rows, key=lambda x: (x["primary_exchange"] != "BSE", x["isin"])):
        for family in ("financial", "shareholding"):
            if family_filter and family != family_filter:
                continue
            task = r["isin"] + ":" + family
            prior = progress.get(task, {})
            if prior.get("done") or prior.get("attempts", 0) >= 3:
                continue
            if time.time() < prior.get("retry_after", 0):
                continue
            if attempted >= limit:
                return progress
            if offline and not (pack / "requests" / (sha(r[family + "_url"].encode()) + ".json")).exists():
                continue
            attempted += 1
            entry = {"isin": r["isin"], "ticker": r["ticker"], "family": family,
                     "attempts": prior.get("attempts", 0) + 1, "started_at": utc(), "sources": [], "done": False}
            try:
                data, evidence = fetch(pack, r[family + "_url"], offline=offline)
                entry["sources"].append(evidence)
                if family == "shareholding" and r["primary_exchange"] == "BSE":
                    catalogue = json.loads(data)
                    filings = catalogue.get("Table", [])
                    if not isinstance(filings, list):
                        raise ValueError("unexpected catalogue schema")
                    if any(str(x.get("FLD_ScripCode", "")).removesuffix(".0") != r["exchange_security_id"] for x in filings):
                        raise ValueError("QUARANTINED_SECURITY_ID_CONFLICT")
                    if filings:
                        latest = max(filings, key=lambda x: str(x.get("EndDate") or ""))
                        attachment = latest.get("XBRLAttachment")
                        if not attachment:
                            raise ValueError("OFFICIAL_FILING_ATTACHMENT_NOT_EXPOSED")
                        body, source = fetch(pack, urljoin("https://www.bseindia.com", attachment), offline=offline)
                        entry["sources"].append(source)
                        validate_bse_shareholding_identity(body, r["isin"])
                        fact = parse_shareholding_inline_xbrl(body, metadata={"ticker": r["ticker"], "isin": r["isin"],
                            "exchange": "BSE", "as_of_date": latest.get("EndDate"), "available_at": latest.get("D"),
                            "filing_id": latest.get("nqtrid"), "source_url": source["url"]})
                        if not fact["as_of_date"] or not fact["available_at"]:
                            raise ValueError("OFFICIAL_PERIOD_OR_CLOCK_MISSING")
                        entry["candidate_fact"] = fact
                        entry["status"] = "EXACT_IDENTITY_PARSED_ACCOUNTING_REVIEW_REQUIRED"
                    else:
                        entry["status"] = "EMPTY_CATALOGUE_OTHER_ROUTES_NOT_EXHAUSTED"
                else:
                    links = Links()
                    links.feed(data.decode("utf-8", errors="replace"))
                    for link in sorted(set(links.urls))[:8]:
                        url = official_url(urljoin(evidence["final_url"], link))
                        _, source = fetch(pack, url, offline=offline)
                        entry["sources"].append(source)
                    entry["status"] = "RAW_FILINGS_REQUIRE_CONTEXT_VALIDATION" if links.urls else "DYNAMIC_DISCOVERY_OR_MANUAL_CACHE_REQUIRED"
                entry["done"] = True
            except HTTPError as exc:
                entry.update(status="SOURCE_ACCESS_TEMPORARILY_BLOCKED", error=f"HTTP {exc.code}")
                retry = exc.headers.get("Retry-After", "") if exc.headers else ""
                delay = int(retry) if retry.isdigit() else 3600
                entry["retry_after"] = time.time() + max(delay, 3600)
                progress[task] = entry
                atomic_write_json(progress_path, progress)
                # Circuit breaker: do not hammer the next issuer on blocked access.
                return progress
            except (OSError, ValueError, TypeError, KeyError) as exc:
                entry.update(status="QUARANTINED" if isinstance(exc, ValueError) else "SOURCE_TEMPORARILY_UNAVAILABLE",
                             error=f"{type(exc).__name__}: {exc}")
                entry["done"] = isinstance(exc, ValueError)
                entry["retry_after"] = time.time() + 3600
            entry["finished_at"] = utc()
            progress[task] = entry
            atomic_write_json(progress_path, progress)
    return progress


def report(pack):
    rows = targets(pack)
    progress = json.loads((pack / "progress.json").read_text()) if (pack / "progress.json").exists() else {}
    financial = pack / "financial_discovery_v2.json"
    if financial.exists():
        for isin, item in json.loads(financial.read_text()).items():
            progress[isin + ":financial"] = item
    evidence, unresolved, holdings = [], [], []
    for r in rows:
        for family in ("financial", "shareholding"):
            task = progress.get(r["isin"] + ":" + family, {})
            unresolved.append({"ticker": r["ticker"], "isin": r["isin"], "category": family,
                               "status": task.get("status", "NOT_ATTEMPTED"), "details": task.get("error", ""), "accepted": False})
            if task.get("candidate_fact"):
                holdings.append(task["candidate_fact"])
            for source in task.get("sources", []):
                if sha((pack / source["path"]).read_bytes()) != source["sha256"]:
                    raise ValueError("raw evidence changed")
                evidence.append({"isin": r["isin"], "category": family, **source})
    # These are review exports, NEVER an accepted provider batch.
    for name, values, columns in (("financial_facts.csv", [], FINANCIAL_COLUMNS),
            ("shareholding_review.csv", holdings, SHAREHOLDING_COLUMNS),
            ("unresolved.csv", unresolved, ["ticker", "isin", "category", "status", "details", "accepted"]),
            ("evidence_index.csv", evidence, ["isin", "category", "url", "final_url", "sha256", "path", "content_type", "retrieved_at"])):
        target = pack / name
        temp = target.with_suffix(".tmp")
        temp.write_bytes(csv_bytes(values, columns))
        temp.replace(target)
    result = {"version": VERSION, "target_count": len(rows), "attempted_tasks": len(progress),
              "shareholding_review_candidates": len(holdings), "accepted_financial_rows": 0,
              "auto_promotion": False, "raw_sources": len(evidence),
              "states": {s: sum(x["status"] == s for x in unresolved) for s in sorted({x["status"] for x in unresolved})},
              "artifacts": {p.name: sha(p.read_bytes()) for p in sorted(pack.glob("*.csv"))}}
    if (pack / "manual_latest.json").exists():
        from manual_financial_recovery import load_current_reference
        manual = load_current_reference(pack)
        result["accepted_manual_current_reference_rows"] = len(manual)
        result["accepted_manual_current_reference_issuers"] = len({r["isin"] for r in manual})
        result["manual_historical_pit_rows"] = 0
    atomic_write_json(pack / "validation_report.json", result)
    immutable_files = [p for directory in ("raw", "requests") for p in sorted((pack / directory).glob("*")) if p.is_file()]
    inventory = {p.relative_to(pack).as_posix(): {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size} for p in immutable_files}
    atomic_write_json(pack / "raw_inventory.json", inventory)
    return result


def collect_financial(pack, limit, offline=False):
    """BSE route verified from its own corporate-page JavaScript, September 2026.

    A separate progress file preserves the older HTML-discovery attempt.
    Raw filings and catalogue times are candidates, never product facts.
    """
    progress_path = pack / "financial_discovery_v2.json"
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
    attempted = 0
    for target in targets(pack):
        if target["primary_exchange"] != "BSE":
            continue
        key = target["isin"]
        previous = progress.get(key, {})
        if previous.get("done") or previous.get("attempts", 0) >= 3 or time.time() < previous.get("retry_after", 0):
            continue
        if attempted >= limit:
            break
        attempted += 1
        entry = {"isin": key, "ticker": target["ticker"], "attempts": previous.get("attempts", 0) + 1,
                 "sources": [], "filings": [], "done": False}
        url = "https://api.bseindia.com/BseIndiaAPI/api/Corp_FinanceResult_ng_new/w?" + urlencode({
            "SCRIP_CD": target["exchange_security_id"], "FlagDur": 7, "HFQ": "", "ISUBGROUP_CODE": "", "segment": "C"})
        try:
            body, receipt = fetch(pack, url, offline=offline)
            entry["sources"].append(receipt)
            rows = json.loads(body).get("Table", [])
            if not isinstance(rows, list) or any(str(r.get("Scrip_cd", "")).removesuffix(".0") != target["exchange_security_id"] for r in rows):
                raise ValueError("QUARANTINED_SECURITY_ID_CONFLICT")
            seen = set()
            for row in sorted(rows, key=lambda r: str(r.get("Fld_CreateDate") or ""), reverse=True):
                name = row.get("XMLName") or ""
                # The linked HTML is official iXBRL; observed companion XML URLs can 404.
                if not name.lower().endswith((".html", ".htm")) or name in seen:
                    continue
                seen.add(name)
                if len(seen) > 4:
                    break
                filing_url = urljoin("https://www.bseindia.com/XBRLFILES/", name)
                try:
                    raw, source = fetch(pack, filing_url, offline=offline)
                except HTTPError as exc:
                    if exc.code != 404:
                        raise
                    entry.setdefault("missing_attachments", []).append({"url": filing_url, "status": "HTTP_404", "catalogue_row": row})
                    continue
                entry["sources"].append(source)
                filing = {**source, "catalogue_row": row, "status": "IDENTITY_VERIFIED_ACCOUNTING_REVIEW_REQUIRED"}
                try:
                    validate_bse_shareholding_identity(raw, key)
                except ValueError as exc:
                    filing.update(status="QUARANTINED_ISIN_CONFLICT", error=str(exc))
                entry["filings"].append(filing)
            entry["status"] = "RAW_FINANCIALS_COLLECTED" if entry["filings"] else "NO_LINKED_IXBRL_IN_CATALOGUE"
            entry["done"] = True
        except HTTPError as exc:
            entry.update(status="SOURCE_ACCESS_TEMPORARILY_BLOCKED", error=str(exc), retry_after=time.time() + 3600)
            progress[key] = entry
            atomic_write_json(progress_path, progress)
            break
        except (OSError, ValueError, TypeError, KeyError) as exc:
            entry.update(status="QUARANTINED" if isinstance(exc, ValueError) else "SOURCE_TEMPORARILY_UNAVAILABLE",
                         error=str(exc), done=isinstance(exc, ValueError), retry_after=time.time() + 3600)
        progress[key] = entry
        atomic_write_json(progress_path, progress)
        print(json.dumps({"ticker": target["ticker"], "status": entry["status"], "filings": len(entry["filings"])}), flush=True)
    return {"issuers_attempted": len(progress), "filings": sum(len(x["filings"]) for x in progress.values()), "auto_promotion": False}


def collect_nse_catalogue(pack, catalogue_path, limit, offline=False):
    """Use an existing hash-verified NSE catalogue, not guessed issuer URLs.

    Catalogue coverage is bounded by its original request period. An absent
    issuer is not evidence of globally absent filings. Exact filing ISIN is
    required even when the catalogue symbol matches the frozen target.
    """
    body = catalogue_path.read_bytes()
    metadata = json.loads(catalogue_path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    if sha(body) != metadata["sha256"]:
        raise ValueError("NSE catalogue hash mismatch")
    official_url(metadata["source_url"])
    rows = json.loads(body)["data"]
    if not isinstance(rows, list):
        raise ValueError("NSE catalogue schema mismatch")
    relative = "raw/" + sha(body) + ".bin"
    immutable(pack / relative, body)
    receipt = {"url": metadata["source_url"], "final_url": metadata["source_url"],
               "path": relative, "sha256": sha(body), "retrieved_at": metadata.get("retrieved_at"),
               "content_type": "application/json"}
    path = pack / "financial_discovery_v2.json"
    progress = json.loads(path.read_text()) if path.exists() else {}
    attempted = 0
    for target in targets(pack):
        if target["primary_exchange"] != "NSE":
            continue
        key = target["isin"]
        prior = progress.get(key, {})
        if prior.get("done") or prior.get("attempts", 0) >= 3 or time.time() < prior.get("retry_after", 0):
            continue
        if attempted >= limit:
            break
        attempted += 1
        entry = {"isin": key, "ticker": target["ticker"], "attempts": prior.get("attempts", 0) + 1,
                 "sources": [receipt], "filings": [], "done": False}
        selected = [r for r in rows if r.get("symbol") == target["ticker"]
                    and r.get("type") == "Integrated Filing- Financials" and r.get("ixbrl")]
        try:
            seen = set()
            for row in selected:
                url = official_url(row["ixbrl"])
                if url in seen:
                    continue
                seen.add(url)
                if len(seen) > 4:
                    break
                raw, source = fetch(pack, url, offline=offline)
                entry["sources"].append(source)
                filing = {**source, "catalogue_row": row, "status": "IDENTITY_VERIFIED_ACCOUNTING_REVIEW_REQUIRED"}
                try:
                    validate_bse_shareholding_identity(raw, key)
                except ValueError as exc:
                    filing.update(status="QUARANTINED_ISIN_CONFLICT", error=str(exc))
                entry["filings"].append(filing)
            entry.update(done=True, status="RAW_FINANCIALS_COLLECTED" if entry["filings"]
                         else "NO_FINANCIAL_LINK_IN_CACHED_NSE_CATALOGUE")
        except (HTTPError, OSError, ValueError) as exc:
            entry.update(status="SOURCE_OR_VALIDATION_FAILURE", error=str(exc), retry_after=time.time() + 3600)
            progress[key] = entry
            atomic_write_json(path, progress)
            if isinstance(exc, HTTPError):
                break
        progress[key] = entry
        atomic_write_json(path, progress)
    return {"nse_tasks_attempted": attempted, "auto_promotion": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "collect", "report", "seed-probe", "collect-financial", "collect-nse-cached", "ingest-manual"))
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--gaps", type=Path, default=ROOT / "data/diagnostics/completeness_recovery_20260908/promotion")
    parser.add_argument("--limit", type=int, default=10, help="Maximum tasks per invocation; one worker, three lifetime attempts.")
    parser.add_argument("--seed", type=Path)
    parser.add_argument("--catalogue", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--offline", action="store_true", help="Process cached catalogues only; attachments must be cached too.")
    parser.add_argument("--family", choices=("financial", "shareholding"))
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 500:
        parser.error("limit must be 1 through 500")
    if args.action == "init":
        result = init_pack(args.gaps, args.pack)
    elif args.action == "ingest-manual":
        if args.archive is None:
            parser.error("ingest-manual requires --archive")
        from manual_financial_recovery import ingest_archive, validate_batch
        result = validate_batch(args.pack, ingest_archive(args.pack, args.archive))
    elif args.action == "collect-financial":
        result = collect_financial(args.pack, args.limit, args.offline)
    elif args.action == "collect-nse-cached":
        if args.catalogue is None:
            parser.error("collect-nse-cached requires --catalogue")
        result = collect_nse_catalogue(args.pack, args.catalogue, args.limit, args.offline)
    elif args.action == "seed-probe":
        if args.seed is None:
            parser.error("seed-probe requires --seed")
        result = seed_probe(args.pack, args.seed)
    else:
        if args.action == "collect":
            collect(args.pack, args.limit, args.offline, args.family)
        result = report(args.pack)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
