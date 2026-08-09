"""Acquire bounded Yahoo outcome histories for the frozen matched cohorts."""

from __future__ import annotations

import argparse
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Callable

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.walk_forward_evaluation import (  # noqa: E402
    BLIND_FINGERPRINT, RANKING_DATES, calendar_target,
)


def _normalize(frame: pd.DataFrame, ranking_date: str, ticker: str, provider: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"OUTCOME_UNAVAILABLE: empty provider history for {ticker} {ranking_date}")
    dates = pd.to_datetime(frame.index)
    if dates.tz is not None:
        dates = dates.tz_convert("Asia/Kolkata").tz_localize(None)
    required = {"Close", "Adj Close"}
    if required.difference(frame.columns):
        raise ValueError(f"OUTCOME_UNAVAILABLE: provider columns missing for {ticker}")
    return pd.DataFrame({
        "ranking_date": ranking_date, "ticker": ticker, "provider_symbol": provider,
        "date": dates.strftime("%Y-%m-%d"),
        "close": frame["Close"].to_numpy(), "adj_close": frame["Adj Close"].to_numpy(),
        "dividends": frame.get("Dividends", pd.Series(0.0, index=frame.index)).to_numpy(),
        "stock_splits": frame.get("Stock Splits", pd.Series(0.0, index=frame.index)).to_numpy(),
        "repaired": frame.get("Repaired?", pd.Series(False, index=frame.index)).astype(bool).to_numpy(),
    })


def acquire(
    blind_root: Path, output: Path,
    history_loader: Callable[..., pd.DataFrame] | None = None,
) -> dict[str, object]:
    if output.exists():
        raise ValueError(f"outcome cache already exists: {output}")
    manifest = json.loads((blind_root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("blind_prediction_fingerprint") != BLIND_FINGERPRINT:
        raise ValueError("frozen blind fingerprint mismatch")
    if history_loader is None:
        import yfinance as yf

        def history_loader(provider: str, start: str, end: str) -> pd.DataFrame:
            return yf.Ticker(provider).history(
                start=start, end=end, interval="1d", auto_adjust=False,
                repair=True, actions=True, raise_errors=True,
            )
        yfinance_version = yf.__version__
    else:
        yfinance_version = "injected-test-loader"
    output.mkdir(parents=True)
    panels = []
    requests = []
    for ranking_date in RANKING_DATES:
        v2 = pd.read_csv(blind_root / ranking_date / "research_v2.csv")
        identity = pd.read_csv(blind_root / ranking_date / "identity_resolution.csv")
        identity = identity.set_index("historical_symbol")
        end_inclusive = pd.Timestamp(calendar_target(ranking_date, 12))
        end_exclusive = (end_inclusive + timedelta(days=1)).date().isoformat()
        for ticker in sorted(v2["ticker"].astype(str)):
            if ticker not in identity.index or identity.loc[ticker, "identity_resolution_status"] != "RESOLVED":
                raise ValueError(f"OUTCOME_UNAVAILABLE: frozen provider identity unavailable for {ticker}")
            provider = str(identity.loc[ticker, "provider_symbol"])
            if not provider or provider == "nan":
                raise ValueError(f"OUTCOME_UNAVAILABLE: blank frozen provider identity for {ticker}")
            frame = history_loader(provider, ranking_date, end_exclusive)
            normalized = _normalize(frame, ranking_date, ticker, provider)
            if normalized["date"].gt(end_inclusive.date().isoformat()).any():
                raise ValueError("provider returned observation beyond bounded request")
            panels.append(normalized)
            requests.append({
                "ranking_date": ranking_date, "ticker": ticker, "provider_symbol": provider,
                "start_inclusive": ranking_date, "end_exclusive": end_exclusive,
                "maximum_allowed_observation": end_inclusive.date().isoformat(),
                "interval": "1d", "auto_adjust": False, "repair": True,
            })
    prices = pd.concat(panels, ignore_index=True).sort_values(
        ["ranking_date", "ticker", "date"], kind="stable"
    ).reset_index(drop=True)
    prices.to_csv(
        output / "outcome_prices.csv", index=False, encoding="utf-8", lineterminator="\n",
        float_format="%.17g",
    )
    request = {
        "schema_version": 1, "provider": "Yahoo via yfinance",
        "yfinance_version": yfinance_version, "blind_prediction_fingerprint": BLIND_FINGERPRINT,
        "requests": requests,
    }
    (output / "request_provenance.json").write_text(
        json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    inventory = {
        "outcome_prices_sha256": sha256((output / "outcome_prices.csv").read_bytes()).hexdigest(),
        "request_provenance_sha256": sha256((output / "request_provenance.json").read_bytes()).hexdigest(),
        "company_date_count": len(requests), "price_row_count": len(prices),
        "outcome_data_acquired": True,
    }
    (output / "cache_manifest.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return inventory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire frozen-cohort walk-forward outcomes.")
    parser.add_argument("--blind-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(acquire(args.blind_root, args.output), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"walk-forward outcome acquisition failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
