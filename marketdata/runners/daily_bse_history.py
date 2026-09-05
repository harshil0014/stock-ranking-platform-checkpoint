"""Daily BSE history maintenance built on the validated backfill core.

This runner reuses ``backfill_bse_history.py`` for exact identity mapping,
provider acquisition, terminal-price validation, and atomic cache writes.

Its only added responsibility is a persistent cooldown registry so known
provider gaps are not retried on every daily refresh.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
RUNNERS = ROOT / "marketdata" / "runners"
for item in (SRC, RUNNERS):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import backfill_bse_history as core  # noqa: E402
from stock_ranker.data_state import (  # noqa: E402
    DataStatePaths,
    acquire_refresh_lock,
    release_refresh_lock,
    resolve_accepted_bundle_root,
)
from stock_ranker.live_market import load_live_market_bundle  # noqa: E402


DEFAULT_STATE_ROOT = ROOT / "data" / "live_market"
DEFAULT_CACHE_ROOT = DEFAULT_STATE_ROOT / "history_cache"
DEFAULT_FAILURE_STATE = (
    DEFAULT_STATE_ROOT / "history_backfill_state" / "bse_daily_failures.csv"
)
DEFAULT_BACKFILL_REPORT_ROOT = DEFAULT_STATE_ROOT / "history_backfill_reports"
DEFAULT_REPORT_ROOT = DEFAULT_BACKFILL_REPORT_ROOT / "daily"

FAILURE_COOLDOWN_DAYS = {
    "NO_PROVIDER_HISTORY": 30,
    "PRICE_MISMATCH": 7,
    "STALE_HISTORY": 7,
    "PROVIDER_ERROR": 1,
}

FAILURE_STATE_COLUMNS = [
    "ticker",
    "isin",
    "exchange_security_id",
    "provider_code",
    "category",
    "first_failed_trade_date",
    "last_failed_trade_date",
    "failure_count",
    "retry_after_trade_date",
    "last_error",
]


def classify_failure(error: str) -> str:
    text = str(error or "").lower()
    if (
        "possibly delisted" in text
        or "no price data" in text
        or "provider returned no history" in text
    ):
        return "NO_PROVIDER_HISTORY"
    if "differs from accepted bse close" in text:
        return "PRICE_MISMATCH"
    if "terminal observation" in text:
        return "STALE_HISTORY"
    return "PROVIDER_ERROR"


def retry_after_trade_date(trade_date: str, category: str) -> str:
    days = FAILURE_COOLDOWN_DAYS.get(category, 1)
    return (date.fromisoformat(trade_date) + timedelta(days=days)).isoformat()


def _empty_failure_state() -> pd.DataFrame:
    return pd.DataFrame(columns=FAILURE_STATE_COLUMNS)


def load_failure_state(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return _empty_failure_state()
    try:
        frame = pd.read_csv(path, dtype=str).fillna("")
    except (OSError, UnicodeError, ValueError, pd.errors.ParserError):
        return _empty_failure_state()
    missing = [column for column in FAILURE_STATE_COLUMNS if column not in frame.columns]
    if missing:
        return _empty_failure_state()
    frame = frame.loc[:, FAILURE_STATE_COLUMNS].copy()
    frame = frame.loc[frame["ticker"].astype(str).str.fullmatch(r"BSE-\d+")].copy()
    frame = frame.drop_duplicates("ticker", keep="last")
    return frame.reset_index(drop=True)



def seed_failure_state_from_latest_backfill(
    report_root: Path,
) -> tuple[pd.DataFrame, str | None]:
    """Seed cooldown state from the newest manual backfill failure report.

    This lets the first automated daily run inherit the evidence already
    collected during the one-time market-wide bootstrap instead of immediately
    retrying the same provider failures.
    """

    candidates = sorted(report_root.glob("bse_history_backfill_*.csv"), reverse=True)
    for path in candidates:
        try:
            frame = pd.read_csv(path, dtype=str).fillna("")
        except (OSError, UnicodeError, ValueError, pd.errors.ParserError):
            continue
        required = {
            "ticker",
            "isin",
            "exchange_security_id",
            "provider_code",
            "trade_date",
            "status",
            "error",
        }
        if not required.issubset(frame.columns):
            continue
        failed = frame.loc[frame["status"].astype(str).eq("FAILED")].copy()
        if failed.empty:
            continue

        rows: list[dict[str, str]] = []
        for row in failed.to_dict("records"):
            trade_date = str(row["trade_date"])
            error = str(row["error"])
            category = classify_failure(error)
            rows.append(
                {
                    "ticker": str(row["ticker"]),
                    "isin": str(row["isin"]),
                    "exchange_security_id": str(row["exchange_security_id"]),
                    "provider_code": str(row["provider_code"]),
                    "category": category,
                    "first_failed_trade_date": trade_date,
                    "last_failed_trade_date": trade_date,
                    "failure_count": "1",
                    "retry_after_trade_date": retry_after_trade_date(
                        trade_date, category
                    ),
                    "last_error": error,
                }
            )
        return (
            pd.DataFrame(rows, columns=FAILURE_STATE_COLUMNS)
            .drop_duplicates("ticker", keep="last")
            .sort_values("ticker", kind="stable")
            .reset_index(drop=True),
            str(path),
        )
    return _empty_failure_state(), None


def _state_map(frame: pd.DataFrame) -> dict[str, dict[str, str]]:
    return {
        str(row["ticker"]): {column: str(row[column]) for column in FAILURE_STATE_COLUMNS}
        for row in frame.to_dict("records")
    }


def _same_identity(state: dict[str, str], row: dict[str, Any]) -> bool:
    return (
        str(state.get("isin", "")) == str(row["isin"])
        and str(state.get("exchange_security_id", "")) == str(row["exchange_security_id"])
    )


def select_pending(
    bse: pd.DataFrame,
    *,
    cache_root: Path,
    failure_state: pd.DataFrame,
    limit: int,
    retry_suppressed: bool,
) -> tuple[pd.DataFrame, dict[str, int]]:
    covered_mask = bse.apply(
        lambda row: core._cache_covers(
            cache_root / f"{row['ticker']}.csv",
            str(row["trade_date"]),
        ),
        axis=1,
    )
    missing = bse.loc[~covered_mask].copy()
    state = _state_map(failure_state)

    selected_indices: list[int] = []
    suppressed = 0
    for index, row in missing.iterrows():
        ticker = str(row["ticker"])
        prior = state.get(ticker)
        blocked = False
        if prior is not None and _same_identity(prior, row.to_dict()):
            retry_after = str(prior.get("retry_after_trade_date", "")).strip()
            try:
                blocked = (
                    bool(retry_after)
                    and date.fromisoformat(str(row["trade_date"]))
                    < date.fromisoformat(retry_after)
                )
            except ValueError:
                blocked = False
        if blocked and not retry_suppressed:
            suppressed += 1
            continue
        selected_indices.append(index)
        if len(selected_indices) >= limit:
            break

    selected = missing.loc[selected_indices].copy()
    return selected.reset_index(drop=True), {
        "covered_before_run": int(covered_mask.sum()),
        "missing_before_run": int((~covered_mask).sum()),
        "suppressed_by_cooldown": int(suppressed),
        "selected_this_run": int(len(selected)),
    }


def _update_failure_state(
    existing: pd.DataFrame,
    *,
    bse: pd.DataFrame,
    results: list[dict[str, Any]],
) -> pd.DataFrame:
    state = _state_map(existing)
    active_tickers = set(bse["ticker"].astype(str))
    state = {ticker: row for ticker, row in state.items() if ticker in active_tickers}

    for result in results:
        ticker = str(result.get("ticker", ""))
        if not ticker:
            continue
        if result.get("status") == "DOWNLOADED":
            state.pop(ticker, None)
            continue

        error = str(result.get("error", ""))
        category = classify_failure(error)
        trade_date = str(result.get("trade_date", ""))
        isin = str(result.get("isin", ""))
        exchange_security_id = str(result.get("exchange_security_id", ""))
        provider_code = str(result.get("provider_code", ""))

        previous = state.get(ticker)
        same = (
            previous is not None
            and previous.get("isin") == isin
            and previous.get("exchange_security_id") == exchange_security_id
        )
        previous_count = int(previous.get("failure_count", "0")) if same else 0
        first_failed = (
            str(previous.get("first_failed_trade_date"))
            if same and previous.get("first_failed_trade_date")
            else trade_date
        )
        state[ticker] = {
            "ticker": ticker,
            "isin": isin,
            "exchange_security_id": exchange_security_id,
            "provider_code": provider_code,
            "category": category,
            "first_failed_trade_date": first_failed,
            "last_failed_trade_date": trade_date,
            "failure_count": str(previous_count + 1),
            "retry_after_trade_date": retry_after_trade_date(trade_date, category),
            "last_error": error,
        }

    rows = [state[key] for key in sorted(state)]
    return pd.DataFrame(rows, columns=FAILURE_STATE_COLUMNS)


def _write_failure_state(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    core._atomic_csv(frame.loc[:, FAILURE_STATE_COLUMNS], path)


def run(args: argparse.Namespace) -> dict[str, Any]:
    state_root = Path(args.state_root).resolve()
    cache_root = Path(args.cache_root).resolve()
    failure_state_path = Path(args.failure_state).resolve()
    report_root = Path(args.report_root).resolve()
    paths = DataStatePaths.from_root(state_root)
    lock = acquire_refresh_lock(paths)
    started_at = datetime.now(timezone.utc).isoformat()

    try:
        accepted_root = resolve_accepted_bundle_root(state_root)
        bundle = load_live_market_bundle(accepted_root)
        bse = core._eligible_bse_rows(bundle.market)
        failure_state = load_failure_state(failure_state_path)
        seeded_from_report: str | None = None
        if failure_state.empty:
            seeded, seeded_from_report = seed_failure_state_from_latest_backfill(
                DEFAULT_BACKFILL_REPORT_ROOT
            )
            if not seeded.empty:
                failure_state = seeded

        pending, selection = select_pending(
            bse,
            cache_root=cache_root,
            failure_state=failure_state,
            limit=args.limit,
            retry_suppressed=args.retry_suppressed,
        )

        summary: dict[str, Any] = {
            "status": "DRY_RUN" if args.dry_run else "COMPLETED",
            "started_at": started_at,
            "accepted_bundle_fingerprint": bundle.fingerprint,
            "accepted_trade_date": str(bundle.manifest["snapshot"]["trade_date"]),
            "bse_universe_count": int(len(bse)),
            "identity_contract": (
                "OFFICIAL_BSE_TRADE_RECORD + numeric scrip code + exact ISIN"
            ),
            "cooldown_policy_days": FAILURE_COOLDOWN_DAYS,
            "failure_state_seeded_from_backfill": seeded_from_report,
            **selection,
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
                        core._fetch_one,
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
                    print(
                        f"[BSE daily {index}/{len(futures)}] "
                        f"{ticker}: {result.get('status', 'FAILED')}",
                        flush=True,
                    )

        updated_state = _update_failure_state(
            failure_state,
            bse=bse,
            results=results,
        )

        # Remove any state entry whose cache is now valid, including a cache
        # populated by another safe process before this write.
        if len(updated_state):
            valid_tickers = set()
            market_by_ticker = bse.set_index("ticker")
            for ticker in updated_state["ticker"].astype(str):
                if ticker not in market_by_ticker.index:
                    continue
                row = market_by_ticker.loc[ticker]
                if core._cache_covers(
                    cache_root / f"{ticker}.csv",
                    str(row["trade_date"]),
                ):
                    valid_tickers.add(ticker)
            updated_state = updated_state.loc[
                ~updated_state["ticker"].isin(valid_tickers)
            ].copy()

        _write_failure_state(updated_state, failure_state_path)

        downloaded = sum(result.get("status") == "DOWNLOADED" for result in results)
        failed = sum(result.get("status") == "FAILED" for result in results)
        categories: dict[str, int] = {}
        for result in results:
            if result.get("status") != "FAILED":
                continue
            category = classify_failure(str(result.get("error", "")))
            categories[category] = categories.get(category, 0) + 1

        covered_after = int(
            bse.apply(
                lambda row: core._cache_covers(
                    cache_root / f"{row['ticker']}.csv",
                    str(row["trade_date"]),
                ),
                axis=1,
            ).sum()
        )

        summary.update(
            {
                "status": (
                    "COMPLETED_WITH_SECURITY_FAILURES" if failed else "COMPLETED"
                ),
                "downloaded": int(downloaded),
                "failed": int(failed),
                "failure_categories": categories,
                "covered_after_run": covered_after,
                "remaining_missing_after_run": int(len(bse) - covered_after),
                "failure_state_rows": int(len(updated_state)),
                "failure_state": str(failure_state_path),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        report_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        csv_path = report_root / f"bse_daily_history_{stamp}.csv"
        json_path = report_root / f"bse_daily_history_{stamp}.json"
        pd.DataFrame(results).to_csv(
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
            "Maintain missing BSE-only histories daily while cooling down "
            "known provider failures."
        )
    )
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--failure-state", type=Path, default=DEFAULT_FAILURE_STATE)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--retry-suppressed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit < 0:
        raise SystemExit("--limit must be nonnegative")
    if not 1 <= args.workers <= 2:
        raise SystemExit("--workers must be 1 or 2 for daily provider maintenance")
    if not 1 <= args.attempts <= 3:
        raise SystemExit("--attempts must be from 1 through 3")

    if args.limit == 0:
        args.dry_run = True

    try:
        result = run(args)
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        # Individual security failures are evidence, not a failed daily job.
        return 0
    except Exception as exc:
        print(
            f"BSE daily history maintenance failed safely: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
