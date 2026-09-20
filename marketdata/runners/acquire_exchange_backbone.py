"""Acquire bulk official NSE/BSE corporate evidence and normalize it offline.

The runner uses broad exchange catalogues, not company-page scraping.  Raw
responses and linked evidence are retained under an ignored immutable batch.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from pathlib import Path
import shutil
import sys
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot  # noqa: E402
from stock_ranker.data_state import atomic_write_json, resolve_accepted_bundle_root  # noqa: E402
from stock_ranker.exchange_backbone import (  # noqa: E402
    ACTION_COLUMNS, BACKBONE_VERSION, DOCUMENT_COLUMNS, FINANCIAL_COLUMNS,
    SHAREHOLDING_COLUMNS, audit_derived_classifications, canonical_json_bytes,
    normalize_bse_actions, normalize_nse_actions, normalize_nse_documents,
    normalize_nse_shareholding, normalize_oss_shareholding,
    parse_exchange_xbrl, parse_shareholding_inline_xbrl, select_latest_revisions,
    sha256_file,
)
from stock_ranker.live_market import load_live_market_bundle  # noqa: E402


NSE = "https://www.nseindia.com"
BSE_API = "https://api.bseindia.com/BseIndiaAPI/api"
OSS_SHP_URL = (
    "https://raw.githubusercontent.com/aditya-jha/nse-historical-membership/"
    "0e9f58c4d457faf0e7ad3db4f4c1449e697e23e0/"
    "shareholding_history/data/parsed/_flat.csv"
)
OSS_REPOSITORY = "https://github.com/aditya-jha/nse-historical-membership"
OSS_COMMIT = "0e9f58c4d457faf0e7ad3db4f4c1449e697e23e0"


def _headers(referer: str) -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
    }


def fetch_bytes(url: str, *, referer: str, timeout: int = 90) -> bytes:
    request = Request(url, headers=_headers(referer))
    with urlopen(request, timeout=timeout) as response:
        data = response.read()
        if response.status != 200 or not data:
            raise RuntimeError(f"provider returned HTTP {response.status} or empty content: {url}")
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "text/html" in content_type and data.lstrip().lower().startswith(b"<!doctype html") and "/XBRLFILES/" not in url:
            raise RuntimeError(f"provider returned an HTML page instead of data: {url}")
        return data


def fetch_json(url: str, *, referer: str) -> Any:
    data = fetch_bytes(url, referer=referer)
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"provider returned malformed JSON: {url}") from exc


def _write_raw(root: Path, name: str, url: str, payload: Any, retrieved_at: str) -> tuple[Path, str]:
    path = root / "raw" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = canonical_json_bytes(payload)
    path.write_bytes(body)
    digest = sha256(body).hexdigest()
    atomic_write_json(path.with_suffix(".metadata.json"), {
        "retrieved_at": retrieved_at, "source_identifier": name,
        "source_url": url, "sha256": digest, "exchange": "BSE" if name.startswith("bse_") else "NSE",
        "filing_type": name, "parser_version": BACKBONE_VERSION,
    })
    return path, digest


def _nse_url(path: str, params: dict[str, Any]) -> str:
    return NSE + path + "?" + urlencode(params)


def _latest_integrated(rows: list[dict[str, Any]], market: pd.DataFrame) -> list[dict[str, Any]]:
    identity = market.set_index("ticker", drop=False)
    selected = []
    for row in rows:
        if str(row.get("type") or "").strip() != "Integrated Filing- Financials":
            continue
        ticker = str(row.get("symbol") or "")
        url = row.get("xbrl")
        if ticker not in identity.index or not url:
            continue
        record = dict(row)
        record["isin"] = str(identity.loc[ticker, "isin"])
        record["exchange"] = "NSE"
        record["available_at"] = row.get("creation_Date") or row.get("broadcast_Date")
        record["revision_at"] = row.get("revised_Date")
        record["revision_status"] = "REVISED" if str(row.get("type_Sub", "")).lower() == "revision" else "ORIGINAL"
        record["filing_id"] = str(row.get("seq_Id") or "")
        selected.append(record)
    frame = pd.DataFrame(selected)
    if frame.empty:
        return []
    frame["_available"] = pd.to_datetime(frame["available_at"], dayfirst=True, errors="coerce")
    frame["_annual"] = frame["qe_Date"].astype(str).str.upper().str.startswith("31-MAR")
    # Latest annual and latest period for each security/basis: at most four files per issuer.
    annual = frame.loc[frame["_annual"]].sort_values(["symbol", "consolidated", "qe_Date", "_available"], kind="stable").drop_duplicates(["symbol", "consolidated"], keep="last")
    latest = frame.sort_values(["symbol", "consolidated", "qe_Date", "_available"], kind="stable").drop_duplicates(["symbol", "consolidated"], keep="last")
    return pd.concat([annual, latest], ignore_index=True).drop_duplicates("xbrl").sort_values(["symbol", "qe_Date", "consolidated"], kind="stable").drop(columns=["_available", "_annual"], errors="ignore").to_dict("records")


def _download_financial_xbrl(batch: Path, rows: list[dict[str, Any]], limit: int) -> tuple[pd.DataFrame, dict[str, int], pd.DataFrame]:
    targets = rows if limit == 0 else rows[:limit]
    facts, failures = [], []
    counts = {"targeted": len(targets), "downloaded": 0, "parsed": 0, "failed": 0}
    raw = batch / "raw" / "xbrl"
    raw.mkdir(parents=True, exist_ok=True)
    for index, row in enumerate(targets, 1):
        url = str(row["xbrl"])
        filename = url.rsplit("/", 1)[-1]
        path = raw / filename
        try:
            if not path.is_file():
                path.write_bytes(fetch_bytes(url, referer=NSE + "/companies-listing/corporate-filings-financial-results"))
                time.sleep(0.03)
            xbrl_sha = sha256_file(path)
            atomic_write_json(path.with_suffix(path.suffix + ".metadata.json"), {
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "source_identifier": str(row.get("filing_id") or filename),
                "source_url": url, "sha256": xbrl_sha, "exchange": "NSE",
                "filing_type": "INTEGRATED_FINANCIAL_XBRL",
                "reporting_period": row.get("qe_Date"), "company_symbol": row.get("symbol"),
                "isin": row.get("isin"), "broadcast_time": row.get("available_at"),
                "revision_status": row.get("revision_status"),
                "parser_version": BACKBONE_VERSION,
            })
            counts["downloaded"] += 1
            parsed = parse_exchange_xbrl(path.read_bytes(), filename=filename, metadata={**row, "source_url": url})
            if not parsed.empty:
                facts.append(parsed)
                counts["parsed"] += 1
        except (OSError, RuntimeError, ValueError) as exc:
            counts["failed"] += 1
            failures.append({"ticker": row.get("symbol"), "isin": row.get("isin"),
                             "filing_id": row.get("filing_id"), "source_url": url,
                             "error_class": type(exc).__name__, "error": str(exc)[:500]})
        if index % 250 == 0:
            print(json.dumps({"xbrl_progress": index, **counts}, sort_keys=True), flush=True)
    result = pd.concat(facts, ignore_index=True) if facts else pd.DataFrame(columns=FINANCIAL_COLUMNS)
    if not result.empty:
        result = result.sort_values(["ticker", "period_end", "statement_basis", "canonical_concept", "source_concept"], kind="stable")
    return result, counts, pd.DataFrame(failures, columns=(
        "ticker", "isin", "filing_id", "source_url", "error_class", "error"
    ))


def validate_bse_shareholding_identity(data: bytes, expected_isin: str) -> None:
    """An unchanged scrip code does not prove unchanged security identity."""
    observed = set(re.findall(r"\bIN[A-Z0-9]{10}\b", data.decode("utf-8", errors="replace")))
    if observed != {expected_isin}:
        raise ValueError(f"BSE filing ISIN conflict or missing identity: expected {expected_isin}; observed {sorted(observed)}")


def _seed_tree(source: Path, destination: Path) -> None:
    """Reuse immutable raw files cheaply; copy only when hard links are unavailable."""

    def link_or_copy(src: str, dst: str) -> str:
        try:
            return str(Path(dst).hardlink_to(Path(src)))
        except OSError:
            return shutil.copy2(src, dst)

    shutil.copytree(source, destination, copy_function=link_or_copy)


def _bse_shareholding(batch: Path, market: pd.DataFrame, limit: int, *,
                      prioritize_professor: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    # NSE symbols are not BSE scrip codes. Only use an identifier explicitly
    # carried by the accepted BSE identity row; never send a ticker as a code.
    bse_codes = market["exchange_security_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    candidates = market.loc[market["primary_exchange"].eq("BSE") & bse_codes.str.fullmatch(r"\d{6}")].copy()
    strategy_path = ROOT / "data/professor_reference/strategy_current/professor_strategy_comparison.csv"
    professor_isins = (set(pd.read_csv(strategy_path, usecols=["isin"])["isin"].dropna().astype(str))
                       if strategy_path.is_file() else set())
    candidates["_professor_first"] = (~candidates["isin"].astype(str).isin(professor_isins)
                                      if prioritize_professor else True)
    candidates["_bse_first"] = ~candidates["primary_exchange"].eq("BSE")
    candidates = candidates.sort_values(["_professor_first", "_bse_first", "ticker"], kind="stable").head(limit)
    holdings, documents = [], []
    counts = {"targeted": len(candidates), "catalogues": 0, "xbrl_parsed": 0, "failed": 0}
    root = batch / "raw" / "bse_shareholding"
    root.mkdir(parents=True, exist_ok=True)
    for item in candidates.itertuples(index=False):
        code = str(item.exchange_security_id).replace(".0", "")
        url = BSE_API + "/Corp_Shareholding_ng/w?" + urlencode({"scripcode": code, "flag": 0, "indtype": ""})
        try:
            catalogue_path = root / f"{code}.json"
            payload = (json.loads(catalogue_path.read_text(encoding="utf-8"))
                       if catalogue_path.is_file() else
                       fetch_json(url, referer="https://www.bseindia.com/corporates/Sharehold_Searchnew.aspx"))
            rows = payload.get("Table", []) if isinstance(payload, dict) else []
            catalogue_path.write_bytes(canonical_json_bytes(payload))
            counts["catalogues"] += 1
            if not rows:
                continue
            if any(str(row.get("FLD_ScripCode", "")).removesuffix(".0") != code for row in rows):
                raise ValueError("BSE shareholding catalogue identity conflicts with requested exact scrip code")
            latest = max(rows, key=lambda row: str(row.get("EndDate") or ""))
            attachment = str(latest.get("XBRLAttachment") or "")
            if not attachment:
                continue
            xbrl_url = "https://www.bseindia.com" + attachment
            filename = attachment.rsplit("/", 1)[-1]
            xbrl_path = root / filename
            xbrl = (xbrl_path.read_bytes() if xbrl_path.is_file() else
                    fetch_bytes(xbrl_url, referer="https://www.bseindia.com/corporates/Sharehold_Searchnew.aspx"))
            xbrl_path.write_bytes(xbrl)
            validate_bse_shareholding_identity(xbrl, str(item.isin))
            atomic_write_json(xbrl_path.with_suffix(xbrl_path.suffix + ".metadata.json"), {
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "source_identifier": str(latest.get("nqtrid") or filename),
                "source_url": xbrl_url, "sha256": sha256(xbrl).hexdigest(),
                "exchange": "BSE", "filing_type": "SHAREHOLDING_XBRL",
                "reporting_period": latest.get("EndDate"), "company_symbol": item.ticker,
                "isin": item.isin, "broadcast_time": latest.get("D"),
                "revision_status": "ORIGINAL", "parser_version": BACKBONE_VERSION,
            })
            holdings.append(parse_shareholding_inline_xbrl(xbrl, metadata={
                "ticker": item.ticker, "isin": item.isin, "exchange": "BSE",
                "as_of_date": latest.get("EndDate"), "available_at": latest.get("D") or latest.get("broadcastTime"),
                "filing_id": latest.get("nqtrid"), "source_url": xbrl_url,
            }))
            documents.append({
                "ticker": item.ticker, "isin": item.isin, "exchange": "BSE",
                "document_type": "SHAREHOLDING", "subject": "Regulation 31 Shareholding Pattern",
                "available_at": pd.to_datetime(latest.get("D"), errors="coerce").isoformat() if latest.get("D") else None,
                "reporting_period": pd.to_datetime(latest.get("EndDate"), errors="coerce").date().isoformat(),
                "filing_id": str(latest.get("nqtrid") or ""), "source_url": xbrl_url,
                "source_sha256": sha256(xbrl).hexdigest(),
            })
            counts["xbrl_parsed"] += 1
            time.sleep(0.05)
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            counts["failed"] += 1
            atomic_write_json(root / f"{code}.failure.json", {
                "ticker": item.ticker, "isin": item.isin, "scrip_code": code,
                "source_url": url, "error_class": type(exc).__name__,
                "error": str(exc)[:500], "accepted": False,
            })
    return (pd.DataFrame(holdings, columns=SHAREHOLDING_COLUMNS),
            pd.DataFrame(documents, columns=DOCUMENT_COLUMNS), counts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire bulk official exchange evidence.")
    parser.add_argument("--batch-id", default="official-backbone-20260822")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--xbrl-limit", type=int, default=0, help="Zero means all selected latest XBRLs.")
    parser.add_argument("--bse-shareholding-limit", type=int, default=150)
    parser.add_argument("--seed-batch", help="Prior failed/accepted batch whose byte-verified raw catalogues may be reused.")
    parser.add_argument("--offline-seed", action="store_true",
                        help="Require a seed batch and rebuild only from its cached raw evidence.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/company_facts/providers/official_exchange")
    args = parser.parse_args(argv)
    if args.days < 1 or args.xbrl_limit < 0 or args.bse_shareholding_limit < 0:
        parser.error("days must be positive and limits must be nonnegative")
    if args.offline_seed and not args.seed_batch:
        parser.error("offline-seed requires --seed-batch")
    batch = args.output_root / args.batch_id
    if batch.exists():
        raise ValueError("official backbone batch already exists; use a fresh immutable batch ID")
    market_bundle = load_live_market_bundle(resolve_accepted_bundle_root(ROOT / "data/live_market"))
    facts_bundle = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts"))
    end = date.today()
    start = end - timedelta(days=args.days)
    date_params = {"index": "equities", "from_date": start.strftime("%d-%m-%Y"), "to_date": end.strftime("%d-%m-%Y")}
    urls = {
        "nse_shareholding": _nse_url("/api/corporate-share-holdings-master", {"index": "equities"}),
        "nse_actions": _nse_url("/api/corporates-corporateActions", date_params),
        "nse_announcements": _nse_url("/api/corporate-announcements", date_params),
        "nse_financial_legacy": _nse_url("/api/corporates-financial-results", {"index": "equities", "period": "Quarterly"}),
        # NSE currently caps this endpoint at 5,000 rows; larger size values
        # return a misleading empty payload rather than a validation error.
        "nse_financial_integrated": _nse_url("/api/integrated-filing-results", {**date_params, "period": "Quarterly", "page": 1, "size": 5000}),
        "bse_actions": BSE_API + "/DefaultData/w?" + urlencode({"ddlcategorys": "E", "ddlindustrys": "", "segment": 0, "strSearch": "D", "Fdate": start.strftime("%Y%m%d"), "TDate": end.strftime("%Y%m%d")}),
        "oss_nse_shareholding": OSS_SHP_URL,
    }
    if args.dry_run:
        print(json.dumps({"would_write": False, "batch": str(batch), "urls": urls,
                          "xbrl_limit": args.xbrl_limit, "bse_shareholding_limit": args.bse_shareholding_limit}, sort_keys=True))
        return 0
    batch.mkdir(parents=True)
    seed = args.output_root / args.seed_batch if args.seed_batch else None
    if seed is not None and (seed / "raw" / "bse_shareholding").is_dir():
        _seed_tree(seed / "raw" / "bse_shareholding", batch / "raw" / "bse_shareholding")
    if seed is not None and (seed / "raw" / "xbrl").is_dir():
        _seed_tree(seed / "raw" / "xbrl", batch / "raw" / "xbrl")
    retrieved_at = datetime.now(timezone.utc).isoformat()
    payloads, hashes = {}, {}
    referers = {
        "nse_shareholding": NSE + "/companies-listing/corporate-filings-shareholding-pattern",
        "nse_actions": NSE + "/companies-listing/corporate-filings-actions",
        "nse_announcements": NSE + "/companies-listing/corporate-filings-announcements",
        "nse_financial_legacy": NSE + "/companies-listing/corporate-filings-financial-results",
        "nse_financial_integrated": NSE + "/companies-listing/corporate-filings-financial-results",
        "bse_actions": "https://www.bseindia.com/corporates/corporate_act.aspx",
    }
    for name in referers:
        seed_raw = seed / "raw" / f"{name}.json" if seed is not None else None
        if seed_raw is not None and seed_raw.is_file() and args.offline_seed:
            payloads[name] = json.loads(seed_raw.read_text(encoding="utf-8"))
        else:
            if args.offline_seed:
                raise FileNotFoundError(f"offline seed is missing raw catalogue: {name}")
            payloads[name] = fetch_json(urls[name], referer=referers[name])
            if name == "nse_financial_integrated" and isinstance(payloads[name], dict):
                first = payloads[name]
                total = int(first.get("totalCount", len(first.get("data", []))))
                rows = list(first.get("data", []))
                for page_number in range(2, (total + 4999) // 5000 + 1):
                    page_url = _nse_url("/api/integrated-filing-results", {**date_params, "period": "Quarterly", "page": page_number, "size": 5000})
                    page = fetch_json(page_url, referer=referers[name])
                    if not isinstance(page, dict) or int(page.get("totalCount", total)) != total:
                        raise RuntimeError("NSE integrated filing pagination changed during acquisition")
                    rows.extend(page.get("data", []))
                if len(rows) != total:
                    raise RuntimeError(f"NSE integrated filing catalogue incomplete: {len(rows)} of {total}")
                payloads[name] = {"data": rows, "size": len(rows), "page": "ALL", "totalCount": total}
        _, hashes[name] = _write_raw(batch, name, urls[name], payloads[name], retrieved_at)
    seed_oss = seed / "raw" / "nse_shareholding_history_cc_by.csv" if seed is not None else None
    oss_bytes = seed_oss.read_bytes() if seed_oss is not None and seed_oss.is_file() else fetch_bytes(OSS_SHP_URL, referer=OSS_REPOSITORY)
    oss_path = batch / "raw" / "nse_shareholding_history_cc_by.csv"
    oss_path.write_bytes(oss_bytes)
    hashes["oss_nse_shareholding"] = sha256(oss_bytes).hexdigest()
    atomic_write_json(oss_path.with_suffix(".metadata.json"), {
        "retrieved_at": retrieved_at, "source_identifier": "nse_shareholding_history_cc_by",
        "source_url": OSS_SHP_URL, "sha256": hashes["oss_nse_shareholding"],
        "exchange": "NSE", "filing_type": "SHAREHOLDING_DERIVED_FROM_OFFICIAL_XBRL",
        "upstream_commit": OSS_COMMIT, "upstream_code_license": "MIT",
        "upstream_data_license": "CC BY 4.0", "parser_version": BACKBONE_VERSION,
    })

    nse_shp = normalize_nse_shareholding(payloads["nse_shareholding"], source_sha256=hashes["nse_shareholding"])
    oss_shp = normalize_oss_shareholding(pd.read_csv(oss_path, low_memory=False), market_bundle.market,
                                         source_url=OSS_REPOSITORY, source_sha256=hashes["oss_nse_shareholding"])
    bse_shp, bse_docs, bse_shp_counts = _bse_shareholding(
        batch, market_bundle.market, args.bse_shareholding_limit,
        prioritize_professor=not args.offline_seed,
    )
    holdings = pd.concat([oss_shp, nse_shp, bse_shp], ignore_index=True)
    holdings = select_latest_revisions(holdings, key=("isin", "as_of_date"))

    nse_actions = normalize_nse_actions(payloads["nse_actions"], source_sha256=hashes["nse_actions"])
    bse_actions = normalize_bse_actions(payloads["bse_actions"], market_bundle.market, source_sha256=hashes["bse_actions"])
    actions = pd.concat([nse_actions, bse_actions], ignore_index=True).sort_values(["ticker", "ex_date", "action_type"], kind="stable", na_position="last")
    documents = pd.concat([
        normalize_nse_documents(payloads["nse_announcements"], source_sha256=hashes["nse_announcements"]),
        bse_docs,
    ], ignore_index=True).sort_values(["ticker", "available_at", "filing_id"], kind="stable", na_position="last")

    integrated_payload = payloads["nse_financial_integrated"]
    integrated_rows = integrated_payload.get("data", []) if isinstance(integrated_payload, dict) else integrated_payload
    targets = _latest_integrated(integrated_rows, market_bundle.market)
    financial, xbrl_counts, xbrl_failures = _download_financial_xbrl(batch, targets, args.xbrl_limit)
    audit = audit_derived_classifications(facts_bundle.facts)

    output = {
        "financial_facts.csv": financial, "shareholding.csv": holdings,
        "corporate_actions.csv": actions, "documents.csv": documents,
        "classification_audit.csv": audit, "xbrl_failures.csv": xbrl_failures,
    }
    artifacts = {}
    for name, frame in output.items():
        frame.to_csv(batch / name, index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")
        artifacts[name] = sha256_file(batch / name)
    raw_inventory = []
    for path in sorted((batch / "raw").rglob("*")):
        if path.is_file():
            raw_inventory.append({"relative_path": path.relative_to(batch).as_posix(),
                                  "size": path.stat().st_size,
                                  "sha256": sha256_file(path)})
    inventory_path = batch / "raw_evidence_inventory.csv"
    pd.DataFrame(raw_inventory, columns=("relative_path", "size", "sha256")).to_csv(
        inventory_path, index=False, encoding="utf-8", lineterminator="\n"
    )
    artifacts[inventory_path.name] = sha256_file(inventory_path)
    classification_counts = {str(k): int(v) for k, v in audit["confidence_status"].value_counts().sort_index().items()}
    manifest = {
        "schema_version": BACKBONE_VERSION, "batch_id": args.batch_id,
        "retrieved_at": retrieved_at, "window_start": start.isoformat(), "window_end": end.isoformat(),
        "market_fingerprint": market_bundle.fingerprint,
        "input_company_fact_fingerprint": facts_bundle.manifest["fingerprint"],
        "catalogue_counts": {
            "nse_shareholding": len(payloads["nse_shareholding"]),
            "nse_actions": len(payloads["nse_actions"]),
            "nse_announcements": len(payloads["nse_announcements"]),
            "nse_legacy_financial": len(payloads["nse_financial_legacy"]),
            "nse_integrated_financial": len(integrated_rows),
            "bse_actions": len(payloads["bse_actions"]),
        },
        "normalized_counts": {"financial_facts": len(financial), "financial_issuers": int(financial["isin"].nunique()) if not financial.empty else 0,
                              "shareholding_observations": len(holdings), "shareholding_issuers": int(holdings["isin"].nunique()) if not holdings.empty else 0,
                              "corporate_actions": len(actions), "action_issuers": int(actions["isin"].nunique()) if not actions.empty else 0,
                              "documents": len(documents), "document_issuers": int(documents["isin"].nunique()) if not documents.empty else 0},
        "xbrl": xbrl_counts, "bse_shareholding": bse_shp_counts,
        "classification_audit": classification_counts,
        "ranking_grade_derived_count": int(audit["confidence_status"].eq("DERIVED_PRIMARY_EVIDENCE").sum()),
        "upstream_oss": [{"repository": OSS_REPOSITORY, "commit": OSS_COMMIT,
                           "code_license": "MIT", "data_license": "CC BY 4.0"}],
        "raw_catalogue_hashes": hashes, "artifacts": artifacts,
        "raw_evidence_file_count": len(raw_inventory),
    }
    manifest["fingerprint"] = sha256(canonical_json_bytes(manifest)).hexdigest()
    atomic_write_json(batch / "manifest.json", manifest)
    atomic_write_json(args.output_root / "accepted_state.json", {
        "accepted_batch": args.batch_id, "fingerprint": manifest["fingerprint"],
        "accepted_at": datetime.now(timezone.utc).isoformat(),
    })
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
