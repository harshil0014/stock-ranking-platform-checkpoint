"""Acquire cutoff-bounded predictor inputs without acquiring outcome data."""

from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from marketdata.runners.acquire_nse_annual_reports import API, _fetch  # noqa: E402
from stock_ranker.walk_forward_blind import (  # noqa: E402
    PROTOCOL_SHA256,
    apply_historical_sector_mapping,
    cutoff_rebased_prices,
    parse_mcwb_archive,
    protocol_fingerprint,
    provider_identity,
    provider_request_window,
)


SNAPSHOTS = (
    {
        "ranking_date": "2022-08-05", "required_fiscal_year": "2021-22",
        "zip": "mcwb_jul22.zip",
        "zip_sha256": "af2bb20cc901eaaa4694f102dc4cd62517397092660bf000b4f03029764e291a",
        "csv_sha256": "85032a234edeb1adb8fbc1bf233b04151a03467961b64c852cb3bd1b53befd65",
    },
    {
        "ranking_date": "2023-08-07", "required_fiscal_year": "2022-23",
        "zip": "mcwb_jul23.zip",
        "zip_sha256": "ce8a335221f222def0ee68b5d2aa6e2cdf500ec171e9c3d100df01a8a4545ac4",
        "csv_sha256": "aa6ecd85791511aef647a546dfaf7db9b956f10c60ae331885e5855e657debbf",
    },
    {
        "ranking_date": "2024-08-07", "required_fiscal_year": "2023-24",
        "zip": "mcwb_jul24.zip",
        "zip_sha256": "5a89a9e0fd709a1b310f03be4b8a4bc8f36c6982a4e83a8746c88af084b700ba",
        "csv_sha256": "b8bb21128768ee8beb74d5fc9072818900e81a8aa7a11787c9990c72baf694b6",
    },
    {
        "ranking_date": "2025-08-07", "required_fiscal_year": "2024-25",
        "zip": "mcwb_jul25.zip",
        "zip_sha256": "0244f8ac658343e07c045eb390f6ac6e42cefc45540a5badcefefdcd284201f4",
        "csv_sha256": "2f4b9ae31c1f840bf15a8f452c77a0d2fc21fc409d2cee03e0851694d903eafd",
    },
)
MAX_METADATA_BYTES = 2_000_000
MAX_PDF_BYTES = 150_000_000


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(
        path, index=False, encoding="utf-8", lineterminator="\n",
        float_format="%.17g",
    )


def _aliases(path: Path) -> dict[str, str]:
    specification = json.loads(path.read_text(encoding="utf-8"))
    aliases = {}
    for row in specification["aliases"]:
        symbol = str(row["historical_symbol"])
        if symbol in aliases:
            raise ValueError(f"duplicate provider alias: {symbol}")
        aliases[symbol] = str(row["provider_symbol"])
    return aliases


def _normalize_yahoo(frame: pd.DataFrame, ticker: str, provider: str) -> pd.DataFrame:
    index = pd.to_datetime(frame.index)
    if index.tz is None:
        dates = index.strftime("%Y-%m-%d")
    else:
        dates = index.tz_convert("Asia/Kolkata").strftime("%Y-%m-%d")
    return pd.DataFrame({
        "ticker": ticker,
        "provider_symbol": provider,
        "date": dates,
        "close": frame["Close"].to_numpy(),
        "adj_close": frame["Adj Close"].to_numpy(),
        "dividends": frame.get("Dividends", pd.Series(0.0, index=frame.index)).to_numpy(),
        "stock_splits": frame.get("Stock Splits", pd.Series(0.0, index=frame.index)).to_numpy(),
        "repaired": frame.get("Repaired?", pd.Series(False, index=frame.index)).astype(bool).to_numpy(),
    })


def _acquire_prices(
    identity: pd.DataFrame,
    ranking_date: str,
    *,
    repair: bool,
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    import yfinance as yf

    request = provider_request_window(ranking_date)
    panels = []
    status = []
    for row in identity.to_dict("records"):
        ticker = str(row["historical_symbol"])
        provider = row["provider_symbol"]
        if not provider:
            status.append({
                "ticker": ticker, "provider_symbol": "",
                "status": "NON_INVESTABLE_PLACEHOLDER", "reason": row["identity_evidence"],
            })
            continue
        try:
            fetched = yf.Ticker(str(provider)).history(
                start=request["start_inclusive"], end=request["end_exclusive"],
                interval="1d", auto_adjust=False, repair=repair,
                actions=True, raise_errors=True,
            )
            if fetched.empty:
                raise ValueError("empty provider history")
            normalized = _normalize_yahoo(fetched, ticker, str(provider))
            normalized = cutoff_rebased_prices(normalized, ranking_date)
            panels.append(normalized)
            status.append({
                "ticker": ticker, "provider_symbol": str(provider),
                "status": "RESOLVED", "reason": "Exact provider identity returned cutoff-bounded history",
            })
        except Exception as exc:
            status.append({
                "ticker": ticker, "provider_symbol": str(provider),
                "status": "PROVIDER_HISTORY_UNAVAILABLE",
                "reason": f"{type(exc).__name__}: {exc}",
            })
    columns = [
        "ticker", "provider_symbol", "date", "close", "adj_close",
        "dividends", "stock_splits", "repaired",
        "cutoff_adjustment_factor", "pit_adjusted_price",
    ]
    prices = pd.concat(panels, ignore_index=True) if panels else pd.DataFrame(columns=columns)
    return prices.loc[:, columns], status


def _nse_timestamp(value: object) -> datetime:
    return datetime.strptime(str(value), "%d-%b-%Y %H:%M:%S").replace(
        tzinfo=ZoneInfo("Asia/Kolkata")
    )


def _select_report(
    rows: list[dict[str, object]],
    required_fiscal_year: str,
    cutoff: datetime,
) -> tuple[dict[str, object] | None, str, dict[str, int]]:
    start_year, end_year = required_fiscal_year.split("-")
    start_year = "20" + start_year if len(start_year) == 2 else start_year
    end_year = "20" + end_year if len(end_year) == 2 else end_year
    required = [
        row for row in rows
        if str(row.get("fromYr")) == start_year and str(row.get("toYr")) == end_year
    ]
    verified = []
    unverified = 0
    post_cutoff = 0
    for row in required:
        try:
            dissemination = _nse_timestamp(row["disseminationDateTime"])
        except (KeyError, TypeError, ValueError):
            unverified += 1
            continue
        if dissemination > cutoff:
            post_cutoff += 1
            continue
        if str(row.get("fileName", "")).lower().endswith(".pdf"):
            verified.append((row, dissemination))
    counts = {
        "required_fy_records": len(required), "post_cutoff_count": post_cutoff,
        "unverified_availability_count": unverified,
    }
    if verified:
        return max(verified, key=lambda item: (item[1], str(item[0].get("fileName"))))[0], "SELECTED", counts
    if unverified:
        return None, "UNVERIFIED_FILING_AVAILABILITY", counts
    if post_cutoff:
        return None, "POST_CUTOFF_ANNUAL_REPORT", counts
    if required:
        return None, "UNSUPPORTED_ANNUAL_REPORT_FORMAT", counts
    return None, "NO_REQUIRED_FY_ANNUAL_REPORT", counts


def _acquire_annual_reports(
    universe: pd.DataFrame,
    ranking_date: str,
    required_fiscal_year: str,
    metadata_cache: Path,
    output: Path,
    *,
    resume: bool = False,
) -> dict[str, Any]:
    metadata_cache.mkdir(parents=True, exist_ok=True)
    pdf_dir = output / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=resume)
    cutoff = datetime.fromisoformat(f"{ranking_date}T15:30:00+05:30")
    records = []
    for ticker in sorted(universe.loc[universe["investable"], "historical_symbol"]):
        metadata_path = metadata_cache / f"{ticker}.json"
        if metadata_path.is_file():
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata_method = "VERIFIED_SHARED_METADATA_CACHE"
        else:
            url = f"{API}?{urlencode({'index': 'equities', 'symbol': ticker})}"
            payload = json.loads(_fetch(url, accept="application/json", max_bytes=MAX_METADATA_BYTES))
            metadata_path.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8", newline="\n",
            )
            metadata_method = "OFFICIAL_NSE_API"
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            raise ValueError(f"annual-report metadata data is not a list: {ticker}")
        selected, selection_status, counts = _select_report(
            rows, required_fiscal_year, cutoff
        )
        entry: dict[str, Any] = {
            "ticker": ticker,
            "required_fiscal_year": required_fiscal_year,
            "metadata_status": "FETCHED",
            "metadata_method": metadata_method,
            "metadata_record_count": len(rows),
            "metadata_sha256": sha256(metadata_path.read_bytes()).hexdigest(),
            "selection_status": selection_status,
            **counts,
        }
        if selected is not None:
            try:
                source_url = str(selected["fileName"])
                filename = Path(urlparse(source_url).path).name
                destination = pdf_dir / f"{ticker}__{filename}"
                if not destination.is_file():
                    destination.write_bytes(_fetch(
                        source_url, accept="application/pdf", max_bytes=MAX_PDF_BYTES
                    ))
                    acquisition_method = "OFFICIAL_NSE_DOWNLOAD"
                else:
                    acquisition_method = "RESUMED_EXISTING_OFFICIAL_DOWNLOAD"
                content = destination.read_bytes()
                if not content.startswith(b"%PDF-"):
                    raise ValueError("response is not a PDF")
                entry.update({
                    "selected_metadata": selected, "source_url": source_url,
                    "pdf_path": destination.relative_to(output).as_posix(),
                    "pdf_filename": filename, "pdf_sha256": sha256(content).hexdigest(),
                    "pdf_size": len(content), "acquisition_method": acquisition_method,
                })
            except Exception as exc:
                entry.update({
                    "selection_status": "ANNUAL_REPORT_ACQUISITION_FAILED",
                    "failure": f"{type(exc).__name__}: {exc}",
                    "selected_metadata": selected,
                })
        records.append(entry)
    (output / "annual_report_provenance.json").write_text(
        json.dumps(records, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    summary = {
        "required_fiscal_year": required_fiscal_year,
        "requested_count": len(records),
        "reports_discovered": sum(int(row["required_fy_records"]) for row in records),
        "pre_cutoff_selected_count": sum(row["selection_status"] == "SELECTED" for row in records),
        "post_cutoff_count": sum(int(row["post_cutoff_count"]) for row in records),
        "unverified_availability_count": sum(int(row["unverified_availability_count"]) for row in records),
        "selection_status_counts": {
            str(key): int(value) for key, value in
            pd.Series([row["selection_status"] for row in records]).value_counts().sort_index().items()
        },
        "cutoff": cutoff.isoformat(),
    }
    (output / "acquisition_summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    return summary


def acquire(
    downloads: Path, output: Path, protocol: Path, aliases_path: Path,
    sector_mapping_path: Path,
    *, resume: bool = False,
) -> dict[str, Any]:
    from marketdata.runners.audit_nse_annual_reports import audit

    if output.exists() and not resume:
        raise ValueError(f"blind source cache already exists: {output}")
    if protocol_fingerprint(protocol) != PROTOCOL_SHA256:
        raise ValueError("frozen walk-forward protocol hash mismatch")
    output.mkdir(parents=True, exist_ok=resume)
    aliases = _aliases(aliases_path)
    sector_mapping = json.loads(sector_mapping_path.read_text(encoding="utf-8"))
    metadata_cache = output / "annual_metadata"
    summaries = []
    for specification in SNAPSHOTS:
        ranking_date = specification["ranking_date"]
        snapshot_root = output / ranking_date
        snapshot_root.mkdir(exist_ok=resume)
        universe_path = snapshot_root / "historical_universe.csv"
        identity_path = snapshot_root / "identity_resolution_requested.csv"
        true_path = snapshot_root / "prices_repair_true.csv"
        false_path = snapshot_root / "prices_repair_false.csv"
        if resume and universe_path.is_file():
            universe = pd.read_csv(universe_path)
        else:
            universe = parse_mcwb_archive(
                downloads / specification["zip"],
                expected_zip_sha256=specification["zip_sha256"],
                expected_csv_sha256=specification["csv_sha256"],
            )
        universe = apply_historical_sector_mapping(universe, sector_mapping, ranking_date)
        if int(universe["investable"].sum()) != 50:
            raise ValueError(f"historical investable universe is not 50: {ranking_date}")
        identity = pd.read_csv(identity_path) if resume and identity_path.is_file() else provider_identity(universe, aliases)
        if "historical_sector" not in identity.columns:
            taxonomy_columns = [
                "historical_sector", "official_sector_code", "classification_document_id",
            ]
            identity = identity.merge(
                universe[["historical_symbol", *taxonomy_columns]],
                on="historical_symbol", how="left", validate="one_to_one",
            )
        if not universe_path.is_file():
            _write_csv(universe, universe_path)
        if not identity_path.is_file():
            _write_csv(identity, identity_path)
        if resume and true_path.is_file() and false_path.is_file():
            repair_true = pd.read_csv(true_path)
            repair_false = pd.read_csv(false_path)
        else:
            repair_true, true_status = _acquire_prices(identity, ranking_date, repair=True)
            repair_false, false_status = _acquire_prices(identity, ranking_date, repair=False)
            _write_csv(repair_true, true_path)
            _write_csv(repair_false, false_path)
            _write_csv(pd.DataFrame(true_status), snapshot_root / "price_status_repair_true.csv")
            _write_csv(pd.DataFrame(false_status), snapshot_root / "price_status_repair_false.csv")
        request = provider_request_window(ranking_date)
        if not (snapshot_root / "price_request.json").is_file():
            (snapshot_root / "price_request.json").write_text(
            json.dumps({
                "ranking_date": ranking_date, "request_window": request,
                "options": {"interval": "1d", "auto_adjust": False, "actions": True},
                "repair_modes": [True, False], "future_outcome_data_requested": False,
            }, sort_keys=True, indent=2) + "\n",
            encoding="utf-8", newline="\n",
        )
        annual_root = snapshot_root / "annual_reports"
        annual_root.mkdir(exist_ok=resume)
        if resume and (annual_root / "acquisition_summary.json").is_file():
            annual_summary = json.loads(
                (annual_root / "acquisition_summary.json").read_text(encoding="utf-8")
            )
        else:
            annual_summary = _acquire_annual_reports(
                universe, ranking_date, specification["required_fiscal_year"],
                metadata_cache, annual_root, resume=resume,
            )
        audit_root = snapshot_root / "annual_report_audit"
        if resume and (audit_root / "audit_summary.json").is_file():
            audit_summary = json.loads(
                (audit_root / "audit_summary.json").read_text(encoding="utf-8")
            )
        else:
            audit_summary = audit(annual_root, audit_root, resume=resume and audit_root.exists())
        summaries.append({
            "ranking_date": ranking_date,
            "official_source_rows": len(universe),
            "investable_rows": int(universe["investable"].sum()),
            "provider_resolved_repair_true": len(repair_true["ticker"].unique()),
            "provider_resolved_repair_false": len(repair_false["ticker"].unique()),
            "required_fiscal_year": specification["required_fiscal_year"],
            "annual_reports": annual_summary,
            "annual_report_audit": audit_summary,
        })
    (output / "acquisition_summary.json").write_text(
        json.dumps({
            "protocol_sha256": PROTOCOL_SHA256,
            "outcome_data_acquired": False,
            "snapshots": summaries,
        }, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    return {"output": str(output), "snapshots": summaries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire blind walk-forward predictor inputs only.")
    parser.add_argument("--downloads", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=ROOT / "experiments/walk_forward/protocol_v1.json")
    parser.add_argument("--aliases", type=Path, default=ROOT / "marketdata/specifications/walk_forward_provider_aliases.json")
    parser.add_argument("--sector-mapping", type=Path, default=ROOT / "marketdata/specifications/walk_forward_nse_sector_mapping.json")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(acquire(
            args.downloads, args.output, args.protocol, args.aliases,
            args.sector_mapping,
            resume=args.resume,
        ), sort_keys=True, indent=2))
        return 0
    except Exception as exc:
        print(f"blind predictor acquisition failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
