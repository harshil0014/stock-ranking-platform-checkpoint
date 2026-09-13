"""Resumable exact-identity bootstrap for missing BSE-only price histories.

This runner does not change ranking formulas, universe identity, or accepted market
snapshots. It only populates the existing ``data/live_market/history_cache`` with
validated Yahoo ``.BO`` histories for exact official BSE scrip codes.

The existing live-market builder already consumes cached BSE histories once a
``BSE-<scrip>.csv`` file exists, so this runner closes the bootstrap gap without
changing core ranking logic.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
import time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_ranker.data_state import (  # noqa: E402
    DataStatePaths,
    acquire_refresh_lock,
    release_refresh_lock,
    resolve_accepted_bundle_root,
)
from stock_ranker.live_market import load_live_market_bundle  # noqa: E402


DEFAULT_STATE_ROOT = ROOT / "data" / "live_market"
DEFAULT_CACHE_ROOT = DEFAULT_STATE_ROOT / "history_cache"
DEFAULT_REPORT_ROOT = DEFAULT_STATE_ROOT / "history_backfill_reports"
MAX_CURRENT_RELATIVE_DIFFERENCE = 0.02
TERMINAL_TOLERANCE_DAYS = 7
IST = ZoneInfo("Asia/Kolkata")


def _atomic_csv(frame: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    frame.to_csv(
        temporary,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        float_format="%.17g",
    )
    temporary.replace(destination)


def bse_provider_code(exchange_security_id: object) -> str:
    """Return Yahoo's exact BSE code form without name guessing."""

    text = str(exchange_security_id).strip()
    if re.fullmatch(r"\d+(?:\.0+)?", text):
        text = text.split(".", 1)[0]
    if not re.fullmatch(r"\d+", text):
        raise ValueError("BSE exchange_security_id must be a numeric official scrip code")
    return f"{text}.BO"


def _cache_covers(path: Path, trade_date: str) -> bool:
    if not path.is_file():
        return False
    try:
        frame = pd.read_csv(path, usecols=["date"])
    except (OSError, UnicodeError, ValueError, pd.errors.ParserError):
        return False
    dates = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="coerce")
    return bool(dates.notna().any() and dates.max().date().isoformat() >= trade_date)


def merge_cached_history(path: Path, incoming: pd.DataFrame) -> pd.DataFrame:
    """Extend a valid accepted series and deterministically update overlaps."""

    required = ["date", "raw_close", "adjusted_close"]
    if not path.is_file():
        return incoming.loc[:, required].copy()
    try:
        existing = pd.read_csv(path)
    except (OSError, UnicodeError, ValueError, pd.errors.ParserError) as exc:
        raise ValueError("existing accepted history is unreadable; refusing replacement") from exc
    if not set(required).issubset(existing.columns):
        raise ValueError("existing accepted history has an invalid schema; refusing replacement")
    existing = existing.loc[:, required].copy()
    for frame in (existing, incoming):
        parsed = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="coerce")
        frame["date"] = parsed.dt.strftime("%Y-%m-%d")
        frame["raw_close"] = pd.to_numeric(frame["raw_close"], errors="coerce")
        frame["adjusted_close"] = pd.to_numeric(frame["adjusted_close"], errors="coerce")
    if (
        existing.isna().any().any()
        or existing["date"].duplicated().any()
        or existing["raw_close"].le(0).any()
        or existing["adjusted_close"].le(0).any()
    ):
        raise ValueError("existing accepted history failed validation; refusing replacement")
    return (
        pd.concat([existing, incoming.loc[:, required]], ignore_index=True)
        .drop_duplicates("date", keep="last")
        .sort_values("date", kind="stable")
        .reset_index(drop=True)
    )


def validate_downloaded_history(
    fetched: pd.DataFrame,
    *,
    trade_date: str,
    official_price: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Normalize provider history and cross-check identity with accepted BSE close."""

    required = {"Close", "Adj Close"}
    missing = sorted(required.difference(fetched.columns))
    if missing:
        raise ValueError("provider history missing columns: " + ", ".join(missing))
    if fetched.empty:
        raise ValueError("provider returned no history")

    index = pd.to_datetime(fetched.index, errors="coerce", utc=True)
    if index.isna().any():
        raise ValueError("provider history contains malformed dates")

    normalized = pd.DataFrame(
        {
            "date": index.tz_convert(IST).strftime("%Y-%m-%d"),
            "raw_close": pd.to_numeric(fetched["Close"], errors="coerce").to_numpy(),
            "adjusted_close": pd.to_numeric(fetched["Adj Close"], errors="coerce").to_numpy(),
        }
    )
    normalized = normalized.dropna(subset=["raw_close", "adjusted_close"]).copy()
    normalized = normalized.loc[
        normalized["raw_close"].gt(0) & normalized["adjusted_close"].gt(0)
    ].copy()
    normalized = (
        normalized.drop_duplicates("date", keep="last")
        .sort_values("date", kind="stable")
        .reset_index(drop=True)
    )
    normalized = normalized.loc[normalized["date"].le(trade_date)].copy()
    if normalized.empty:
        raise ValueError("provider returned no positive observations through the accepted trade date")

    official = float(official_price)
    if not math.isfinite(official) or official <= 0:
        raise ValueError("accepted BSE current price is unavailable or invalid")

    terminal = normalized.iloc[-1]
    accepted_date = date.fromisoformat(trade_date)
    terminal_date = date.fromisoformat(str(terminal["date"]))
    lag_days = (accepted_date - terminal_date).days
    if lag_days < 0 or lag_days > TERMINAL_TOLERANCE_DAYS:
        raise ValueError(
            f"provider terminal observation is {lag_days} calendar days from accepted trade date"
        )

    provider_raw = float(terminal["raw_close"])
    relative_difference = abs(provider_raw - official) / official
    if relative_difference > MAX_CURRENT_RELATIVE_DIFFERENCE:
        raise ValueError(
            "provider raw close differs from accepted BSE close by "
            f"{relative_difference * 100:.4f}% (> 2.0000%)"
        )

    audit = {
        "rows": int(len(normalized)),
        "first_date": str(normalized.iloc[0]["date"]),
        "last_date": str(terminal["date"]),
        "official_price": official,
        "provider_raw_close": provider_raw,
        "terminal_lag_days": int(lag_days),
        "current_relative_difference": float(relative_difference),
    }
    return normalized, audit


def _fetch_one(
    row: dict[str, Any],
    *,
    cache_root: Path,
    attempts: int,
) -> dict[str, Any]:
    ticker = str(row["ticker"])
    isin = str(row["isin"])
    scrip_code = str(row["exchange_security_id"])
    provider_code = bse_provider_code(scrip_code)
    trade_date = str(row["trade_date"])
    target = cache_root / f"{ticker}.csv"

    base = {
        "ticker": ticker,
        "isin": isin,
        "exchange_security_id": scrip_code,
        "provider_code": provider_code,
        "trade_date": trade_date,
        "cache_path": str(target),
    }

    import yfinance as yf

    error = "provider returned no history"
    for attempt in range(1, attempts + 1):
        try:
            fetched = yf.Ticker(provider_code).history(
                period="max",
                interval="1d",
                auto_adjust=False,
                repair=True,
                actions=True,
                raise_errors=True,
            )
            normalized, audit = validate_downloaded_history(
                fetched,
                trade_date=trade_date,
                official_price=float(row["latest_price"]),
            )
            normalized = merge_cached_history(target, normalized)
            _atomic_csv(normalized, target)
            audit.update({
                "rows": int(len(normalized)),
                "first_date": str(normalized.iloc[0]["date"]),
                "last_date": str(normalized.iloc[-1]["date"]),
            })
            return {
                **base,
                **audit,
                "status": "DOWNLOADED",
                "attempts": attempt,
                "error": "",
            }
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 4))

    return {
        **base,
        "status": "FAILED",
        "attempts": attempts,
        "rows": 0,
        "first_date": "",
        "last_date": "",
        "official_price": row.get("latest_price"),
        "provider_raw_close": None,
        "terminal_lag_days": None,
        "current_relative_difference": None,
        "error": error,
    }


def _eligible_bse_rows(market: pd.DataFrame) -> pd.DataFrame:
    required = {
        "ticker",
        "isin",
        "primary_exchange",
        "exchange_security_id",
        "identity_status",
        "trade_date",
        "latest_price",
    }
    missing = sorted(required.difference(market.columns))
    if missing:
        raise ValueError("accepted live-market bundle missing columns: " + ", ".join(missing))

    rows = market.loc[market["primary_exchange"].astype(str).eq("BSE")].copy()
    if "ranking_universe_eligible" in rows:
        eligible = rows["ranking_universe_eligible"].map(
            lambda value: value is True or str(value).strip().lower() == "true"
        )
        rows = rows.loc[eligible].copy()

    if rows["ticker"].duplicated().any() or rows["isin"].duplicated().any():
        raise ValueError("BSE bootstrap population contains duplicate ticker or ISIN")

    bad_ticker = ~rows["ticker"].astype(str).str.fullmatch(r"BSE-\d+")
    bad_isin = ~rows["isin"].astype(str).str.fullmatch(r"INE[A-Z0-9]{9}")
    bad_identity = ~rows["identity_status"].astype(str).eq("OFFICIAL_BSE_TRADE_RECORD")
    if bad_ticker.any() or bad_isin.any() or bad_identity.any():
        raise ValueError(
            "BSE bootstrap population contains a row outside the exact official BSE identity contract"
        )

    rows["_numeric_scrip"] = pd.to_numeric(rows["exchange_security_id"], errors="coerce")
    if rows["_numeric_scrip"].isna().any():
        raise ValueError("BSE bootstrap population contains a nonnumeric official scrip code")
    rows = rows.sort_values(["_numeric_scrip", "isin"], kind="stable").drop(columns="_numeric_scrip")
    return rows.reset_index(drop=True)


def run(args: argparse.Namespace) -> dict[str, Any]:
    state_root = Path(args.state_root).resolve()
    cache_root = Path(args.cache_root).resolve()
    report_root = Path(args.report_root).resolve()
    paths = DataStatePaths.from_root(state_root)
    lock = acquire_refresh_lock(paths)
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        accepted_root = resolve_accepted_bundle_root(state_root)
        bundle = load_live_market_bundle(accepted_root)
        bse = _eligible_bse_rows(bundle.market)

        already_covered_mask = bse.apply(
            lambda row: _cache_covers(
                cache_root / f"{row['ticker']}.csv",
                str(row["trade_date"]),
            ),
            axis=1,
        )
        pending = bse.loc[~already_covered_mask].copy()
        if not args.all:
            pending = pending.head(args.limit).copy()

        summary: dict[str, Any] = {
            "status": "DRY_RUN" if args.dry_run else "COMPLETED",
            "started_at": started_at,
            "accepted_bundle_fingerprint": bundle.fingerprint,
            "accepted_trade_date": str(bundle.manifest["snapshot"]["trade_date"]),
            "bse_universe_count": int(len(bse)),
            "already_covered_before_run": int(already_covered_mask.sum()),
            "missing_before_run": int((~already_covered_mask).sum()),
            "selected_this_run": int(len(pending)),
            "identity_contract": "OFFICIAL_BSE_TRADE_RECORD + numeric scrip code + exact ISIN",
            "provider_mapping": "official BSE numeric scrip code -> <code>.BO",
            "terminal_validation": "provider raw close within 2% of accepted BSE close and <=7 calendar days",
        }
        if args.dry_run:
            summary["selected"] = pending[
                ["ticker", "isin", "exchange_security_id", "trade_date", "latest_price"]
            ].to_dict("records")
            return summary

        results: list[dict[str, Any]] = []
        if len(pending):
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = {
                    executor.submit(
                        _fetch_one,
                        row,
                        cache_root=cache_root,
                        attempts=args.attempts,
                    ): str(row["ticker"])
                    for row in pending.to_dict("records")
                }
                for index, future in enumerate(as_completed(futures), start=1):
                    ticker = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {
                            "ticker": ticker,
                            "status": "FAILED",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    results.append(result)
                    status = result.get("status", "FAILED")
                    print(f"[{index}/{len(futures)}] {ticker}: {status}", flush=True)

        results_frame = pd.DataFrame(results)
        downloaded = int(results_frame["status"].eq("DOWNLOADED").sum()) if len(results_frame) else 0
        failed = int(results_frame["status"].eq("FAILED").sum()) if len(results_frame) else 0

        after_covered = int(
            bse.apply(
                lambda row: _cache_covers(
                    cache_root / f"{row['ticker']}.csv",
                    str(row["trade_date"]),
                ),
                axis=1,
            ).sum()
        )
        summary.update(
            {
                "downloaded": downloaded,
                "failed": failed,
                "covered_after_run": after_covered,
                "remaining_missing_after_run": int(len(bse) - after_covered),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        report_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        csv_path = report_root / f"bse_history_backfill_{stamp}.csv"
        json_path = report_root / f"bse_history_backfill_{stamp}.json"
        if len(results_frame):
            results_frame.sort_values(["status", "ticker"], kind="stable").to_csv(
                csv_path, index=False, encoding="utf-8", lineterminator="\n"
            )
        else:
            pd.DataFrame(columns=["ticker", "status", "error"]).to_csv(
                csv_path, index=False, encoding="utf-8", lineterminator="\n"
            )
        json_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        summary["report_csv"] = str(csv_path)
        summary["report_json"] = str(json_path)
        return summary
    finally:
        release_refresh_lock(lock)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap missing BSE-only adjusted histories through exact official "
            "BSE scrip-code -> Yahoo .BO mapping, without changing ranking logic."
        )
    )
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    if not 1 <= args.workers <= 6:
        raise SystemExit("--workers must be from 1 through 6")
    if not 1 <= args.attempts <= 5:
        raise SystemExit("--attempts must be from 1 through 5")

    try:
        result = run(args)
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0 if int(result.get("failed", 0)) == 0 else 2
    except Exception as exc:
        print(f"BSE history bootstrap failed safely: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
