"""Prepare the cached ALL NSE live-market bundle used by the local website."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_ranker.baseline import calculate_baseline_rankings  # noqa: E402
from stock_ranker.historical_baseline import (  # noqa: E402
    calculate_prepared_real_rankings,
    load_historical_baseline_bundle,
    prepare_historical_baseline,
    provider_symbol,
)
from stock_ranker.live_market import (  # noqa: E402
    SEGMENT_FILES,
    apply_official_segments,
    build_latest_snapshot,
    combine_live_market,
    load_index_membership,
    load_official_equity_universe,
    write_live_bundle,
)
from stock_ranker.real_research_v2 import load_real_research_v2_bundle  # noqa: E402


DEFAULT_SOURCE = ROOT / "data/live_market/source"
DEFAULT_OUTPUT = ROOT / "data/live_market/current"
DEFAULT_CACHE = ROOT / "data/live_market/history_cache"
ACCEPTED_BASELINE = ROOT / "data/marketdata/nifty50-baseline-2026-08-07"
ACCEPTED_V2 = ROOT / "data/marketdata/nifty50-research-v2-2026-08-07/standalone-contract-reason-fix-run-01"
AS_OF_DATE = "2026-08-07"
OFFICIAL_SOURCE_URLS = {
    "equity.csv": "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
    "nifty100.csv": "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv",
    "midcap150.csv": "https://www.niftyindices.com/IndexConstituent/ind_niftymidcap150list.csv",
    "smallcap250.csv": "https://www.niftyindices.com/IndexConstituent/ind_niftysmallcap250list.csv",
    "microcap250.csv": "https://www.niftyindices.com/IndexConstituent/ind_niftymicrocap250_list.csv",
}


def _atomic_csv(frame: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    frame.to_csv(temporary, index=False, lineterminator="\n", encoding="utf-8", float_format="%.17g")
    temporary.replace(destination)


def _seed_accepted_cache(cache: Path) -> int:
    """Seed per-security cache from the already accepted NIFTY 50 bundle."""

    panel_path = ACCEPTED_BASELINE / "historical_prices.csv"
    if not panel_path.is_file():
        return 0
    seeded = 0
    panel = pd.read_csv(panel_path)
    for ticker, rows in panel.groupby("ticker", sort=True):
        target = cache / f"{ticker}.csv"
        if target.is_file():
            continue
        columns = [column for column in ("date", "raw_close", "adjusted_close") if column in rows]
        _atomic_csv(rows.loc[:, columns], target)
        seeded += 1
    return seeded


def acquire_official_sources(source: Path, trade_date: str, attempts: int) -> None:
    """Download allowlisted official files with bounded retries and atomic writes."""

    datetime.strptime(trade_date, "%Y-%m-%d")
    source.mkdir(parents=True, exist_ok=True)
    urls = dict(OFFICIAL_SOURCE_URLS)
    compact = trade_date.replace("-", "")
    urls[f"bhavcopy_{compact}.zip"] = (
        "https://nsearchives.nseindia.com/content/cm/"
        f"BhavCopy_NSE_CM_0_0_0_{compact}_F_0000.csv.zip"
    )
    for filename, url in urls.items():
        destination = source / filename
        error = "download failed"
        for attempt in range(1, attempts + 1):
            try:
                request = Request(url, headers={"User-Agent": "stock-ranking-platform/1.0 research"})
                with urlopen(request, timeout=60) as response:
                    payload = response.read()
                if not payload:
                    raise ValueError("official source returned an empty file")
                temporary = destination.with_suffix(destination.suffix + ".tmp")
                temporary.write_bytes(payload)
                temporary.replace(destination)
                break
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                if attempt < attempts:
                    time.sleep(min(2 ** (attempt - 1), 4))
        else:
            raise ValueError(f"could not acquire {filename}: {error}")


def _fetch_one(ticker: str, cache: Path, attempts: int, as_of_date: str = AS_OF_DATE) -> tuple[bool, str]:
    target = cache / f"{ticker}.csv"
    if target.is_file():
        return True, "CACHE_HIT"
    import yfinance as yf
    error = "provider returned no history"
    for attempt in range(1, attempts + 1):
        try:
            fetched = yf.Ticker(provider_symbol(ticker)).history(
                period="max", interval="1d", auto_adjust=False,
                repair=True, actions=True, raise_errors=True,
            )
            if fetched.empty:
                raise ValueError("provider returned no history")
            index = pd.to_datetime(fetched.index, utc=True)
            normalized = pd.DataFrame({
                "date": index.tz_convert("Asia/Kolkata").strftime("%Y-%m-%d"),
                "raw_close": fetched["Close"].to_numpy(),
                "adjusted_close": fetched["Adj Close"].to_numpy(),
            })
            normalized = normalized.loc[normalized["date"] <= as_of_date]
            if normalized.empty:
                raise ValueError("provider returned no observations through the snapshot date")
            _atomic_csv(normalized.sort_values("date", kind="stable"), target)
            return True, "DOWNLOADED"
        except Exception as exc:  # bounded provider failure becomes evidence
            error = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 4))
    return False, error


def prepare(args: argparse.Namespace) -> dict[str, object]:
    started = datetime.now(timezone.utc)
    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    cache = Path(args.cache).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    if args.acquire_sources:
        print("[Sources] acquiring allowlisted official NSE/NSE Indices files", flush=True)
        acquire_official_sources(source, args.trade_date, args.attempts)
    print("[Universe] validating official NSE equity list", flush=True)
    universe = load_official_equity_universe(source / "equity.csv")
    memberships = {
        segment: load_index_membership(source / filename, segment)
        for segment, filename in SEGMENT_FILES.items()
    }
    universe = apply_official_segments(universe, memberships)
    print(f"[Universe] {len(universe)} ordinary main-board equities; "
          f"{int(universe.classification_status.eq('CLASSIFIED').sum())} classified", flush=True)
    bhavcopy_path = source / f"bhavcopy_{args.trade_date.replace('-', '')}.zip"
    snapshot, snapshot_metadata = build_latest_snapshot(universe, bhavcopy_path)
    if snapshot_metadata["trade_date"] != args.trade_date:
        raise ValueError("official bhavcopy trading date does not match --trade-date")
    print(f"[Snapshot] {snapshot_metadata['matched_count']} matched / "
          f"{snapshot_metadata['missing_count']} unavailable as of {snapshot_metadata['trade_date']}", flush=True)

    seeded = _seed_accepted_cache(cache)
    classified = universe.loc[universe["classification_status"].eq("CLASSIFIED")].copy()
    targets = classified["ticker"].tolist()
    missing = [ticker for ticker in targets if not (cache / f"{ticker}.csv").is_file()]
    if args.download_limit is not None:
        missing = missing[:args.download_limit]
    attempted = 0
    downloaded = 0
    failures: dict[str, str] = {}
    if not args.no_download:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            pending = {
                executor.submit(_fetch_one, ticker, cache, args.attempts, args.trade_date): ticker
                for ticker in missing
            }
            for index, future in enumerate(as_completed(pending), start=1):
                ticker = pending[future]
                attempted += 1
                try:
                    ok, status = future.result()
                except Exception as exc:
                    ok, status = False, f"{type(exc).__name__}: {exc}"
                downloaded += int(ok and status == "DOWNLOADED")
                if not ok:
                    failures[ticker] = status
                if index == 1 or index % 25 == 0 or index == len(missing):
                    print(f"[Price history] {index}/{len(missing)} attempted; "
                          f"{downloaded} downloaded; {len(failures)} failed", flush=True)
    histories: dict[str, pd.DataFrame | None] = {}
    for ticker in targets:
        cached = cache / f"{ticker}.csv"
        histories[ticker] = pd.read_csv(cached) if cached.is_file() else None

    identity = classified.rename(columns={
        "ticker": "Symbol", "company": "Company Name", "sector": "Industry",
    })[["Symbol", "Company Name", "Industry"]]
    boundaries = classified.rename(columns={"ticker": "ticker", "listing_date": "valid_from_date"})[
        ["ticker", "valid_from_date"]
    ].copy()
    boundaries["boundary_type"] = "OFFICIAL_NSE_SECURITY_LISTING_DATE"
    boundaries["evidence_source"] = "NSE Securities available for Equity segment DATE OF LISTING"
    print("[Baseline] applying unchanged Baseline V1 preparation and ranking", flush=True)
    prepared = prepare_historical_baseline(
        identity, snapshot.rename(columns={"latest_price": "close"})[["ticker", "close"]],
        histories, as_of_date=args.trade_date, history_start_boundaries=boundaries,
    )
    baseline_rankings = calculate_baseline_rankings(prepared.baseline_input) if not prepared.baseline_input.empty else pd.DataFrame()

    v2 = load_real_research_v2_bundle(ACCEPTED_V2)
    market = combine_live_market(
        universe, snapshot, baseline_rankings=baseline_rankings,
        baseline_eligibility=prepared.eligibility,
        v2_rankings=v2.rankings, v2_eligibility=v2.eligibility,
    )
    completed = datetime.now(timezone.utc)
    source_files = {"equity_universe": source / "equity.csv", "bhavcopy": bhavcopy_path}
    source_files.update({f"segment_{key.lower()}": source / value for key, value in SEGMENT_FILES.items()})
    bundle = write_live_bundle(
        market, output, snapshot_metadata=snapshot_metadata,
        source_files=source_files,
        acquisition_started_at=started.isoformat(), acquisition_completed_at=completed.isoformat(),
        history_attempted=attempted, history_acquired=sum(value is not None for value in histories.values()),
        history_failed=sum(value is None for value in histories.values()),
    )
    report = {
        "bundle_fingerprint": bundle.fingerprint, "universe_count": len(market),
        "snapshot_matched": snapshot_metadata["matched_count"],
        "history_cache_seeded": seeded, "history_attempted": attempted,
        "history_downloaded": downloaded, "history_failures": failures,
        "price_ready": int(market["snapshot_status"].eq("AVAILABLE").sum()),
        "baseline_eligible": int(market["baseline_eligible"].sum()),
        "research_v2_eligible": int(market["v2_eligible"].sum()),
        "output": str(bundle.path), "runtime_seconds": (completed - started).total_seconds(),
    }
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare the cached ALL NSE live-market website bundle.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--trade-date", default=AS_OF_DATE)
    parser.add_argument("--acquire-sources", action="store_true")
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--download-limit", type=int)
    parser.add_argument("--no-download", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        datetime.strptime(args.trade_date, "%Y-%m-%d")
    except ValueError:
        raise SystemExit("--trade-date must use valid ISO YYYY-MM-DD format")
    if args.attempts < 1 or args.attempts > 5:
        raise SystemExit("--attempts must be from 1 through 5")
    if args.download_limit is not None and args.download_limit < 0:
        raise SystemExit("--download-limit must not be negative")
    if args.workers < 1 or args.workers > 8:
        raise SystemExit("--workers must be from 1 through 8")
    try:
        prepare(args)
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"live-market preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
