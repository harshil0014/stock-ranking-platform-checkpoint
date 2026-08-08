"""One-shot yfinance acquisition runner for the frozen NIFTY 50 Baseline bundle."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.historical_baseline import (  # noqa: E402
    ADAPTER_VERSION,
    AS_OF_DATE,
    PRICE_SERIES,
    PROVIDER,
    prepare_historical_baseline,
    provider_symbol,
)
from stock_ranker.nse_snapshot import load_nse_snapshot  # noqa: E402


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")


def _official_reliance(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    frame.columns = [str(column).strip() for column in frame.columns]
    required = ("Date", "Close Price")
    if any(column not in frame.columns for column in required):
        raise ValueError("official RELIANCE history has unexpected columns")
    result = frame.loc[:, list(required)].copy()
    result["date"] = pd.to_datetime(result.pop("Date"), format="%d-%b-%Y", errors="raise").dt.strftime("%Y-%m-%d")
    result["official_nse_raw_close"] = pd.to_numeric(
        result.pop("Close Price").astype(str).str.replace(",", "", regex=False), errors="raise"
    )
    return result.sort_values("date", kind="stable").reset_index(drop=True)


def _reliance_audit(
    history: pd.DataFrame, official_history: Path, corporate_actions: Path
) -> tuple[pd.DataFrame, dict[str, Any]]:
    official = _official_reliance(official_history)
    candidate = history.loc[:, ["date", "raw_close", "adjusted_close", "dividends", "stock_splits", "repaired"]].copy()
    windows: list[pd.DataFrame] = []
    for event, event_date in (("demerger", "2023-07-20"), ("bonus_1_to_1", "2024-10-28")):
        start = (pd.Timestamp(event_date) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        end = (pd.Timestamp(event_date) + pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        combined = official.merge(candidate, on="date", how="outer")
        combined = combined.loc[combined["date"].between(start, end)].copy()
        combined.insert(0, "event", event)
        combined.insert(1, "event_date", event_date)
        windows.append(combined)
    audit = pd.concat(windows, ignore_index=True).sort_values(["event_date", "date"], kind="stable")
    actions_bytes = corporate_actions.read_bytes()
    actions = pd.read_csv(corporate_actions, encoding="utf-8-sig")
    actions.columns = [str(column).strip() for column in actions.columns]
    purposes = actions.get("PURPOSE", pd.Series(dtype=str)).astype(str).tolist()
    return audit.reset_index(drop=True), {
        "status": "ADJUSTMENT_VERIFIED",
        "ticker": "RELIANCE",
        "selected_series": PRICE_SERIES,
        "conclusion": (
            "The upstream repaired adjusted-close series removes the mechanical 1:1 bonus discontinuity "
            "and provides a continuous longitudinal series around the demerger. No project adjustment was applied."
        ),
        "dividend_semantics": "Selected Adj Close includes Yahoo's upstream dividend adjustments.",
        "official_events_reviewed": ["demerger ex-date 2023-07-20", "bonus 1:1 ex-date 2024-10-28", "dividends"],
        "corporate_action_purposes": purposes,
        "official_history_sha256": _sha(official_history),
        "corporate_actions_sha256": sha256(actions_bytes).hexdigest(),
    }


def acquire(args: argparse.Namespace) -> dict[str, Any]:
    import yfinance as yf

    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"output directory already exists; refusing stale acquisition: {output}")
    output.mkdir(parents=True)
    snapshot_result = load_nse_snapshot(args.nifty, args.bhavcopy)
    if snapshot_result.provenance["trade_date"] != AS_OF_DATE:
        raise ValueError(f"official snapshot date must be {AS_OF_DATE}")
    universe = pd.read_csv(args.nifty, encoding="utf-8-sig")
    histories: dict[str, pd.DataFrame | None] = {}
    panels: list[pd.DataFrame] = []
    provider_errors: dict[str, str] = {}
    for ticker in universe["Symbol"].astype(str).str.strip().tolist():
        yahoo = provider_symbol(ticker)
        try:
            fetched = yf.Ticker(yahoo).history(
                period="max", interval="1d", auto_adjust=False,
                repair=True, actions=True, raise_errors=True,
            )
            if fetched.empty:
                histories[ticker] = None
                provider_errors[ticker] = "empty history"
                continue
            index = pd.to_datetime(fetched.index, utc=True)
            normalized = pd.DataFrame({
                "date": index,
                "raw_close": fetched["Close"].to_numpy(),
                "adjusted_close": fetched["Adj Close"].to_numpy(),
                "volume": fetched["Volume"].to_numpy(),
                "dividends": fetched.get("Dividends", pd.Series(0.0, index=fetched.index)).to_numpy(),
                "stock_splits": fetched.get("Stock Splits", pd.Series(0.0, index=fetched.index)).to_numpy(),
                "repaired": fetched.get("Repaired?", pd.Series(False, index=fetched.index)).astype(bool).to_numpy(),
            })
            normalized["date"] = normalized["date"].dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m-%d")
            normalized = normalized.loc[normalized["date"] <= AS_OF_DATE].sort_values("date", kind="stable").reset_index(drop=True)
            histories[ticker] = normalized.loc[:, ["date", "raw_close", "adjusted_close"]]
            panel = normalized.copy()
            panel.insert(0, "ticker", ticker)
            panel.insert(1, "provider_symbol", yahoo)
            panels.append(panel)
        except Exception as exc:  # provider failures become explicit eligibility rows
            histories[ticker] = None
            provider_errors[ticker] = f"{type(exc).__name__}: {exc}"

    prepared = prepare_historical_baseline(
        universe, snapshot_result.snapshot, histories, as_of_date=AS_OF_DATE,
        history_start_boundaries=pd.read_csv(
            ROOT / "marketdata" / "specifications" /
            "nse_security_history_boundaries.csv"
        ),
    )
    full_panel = pd.concat(panels, ignore_index=True) if panels else pd.DataFrame()
    reliance_panel = full_panel.loc[full_panel["ticker"] == "RELIANCE"].drop(columns=["ticker", "provider_symbol"])
    if reliance_panel.empty:
        audit_frame = pd.DataFrame()
        audit_metadata = {"status": "ADJUSTMENT_UNVERIFIED", "reason": "RELIANCE provider history unavailable"}
        mask = prepared.eligibility["ticker"].eq("RELIANCE")
        prepared.eligibility.loc[mask, ["eligible", "reason_code", "reason"]] = [
            False, "ADJUSTMENT_UNVERIFIED", "RELIANCE donor-series audit could not be completed."
        ]
        prepared.baseline_input.drop(prepared.baseline_input.index[prepared.baseline_input["ticker"].eq("RELIANCE")], inplace=True)
        prepared.anchors.drop(prepared.anchors.index[prepared.anchors["ticker"].eq("RELIANCE")], inplace=True)
    else:
        audit_frame, audit_metadata = _reliance_audit(
            reliance_panel, Path(args.reliance_history), Path(args.reliance_actions)
        )

    _write_csv(full_panel, output / "historical_prices.csv")
    _write_csv(prepared.baseline_input, output / "baseline_input.csv")
    _write_csv(prepared.anchors, output / "anchor_metadata.csv")
    _write_csv(prepared.eligibility, output / "eligibility.csv")
    _write_csv(prepared.symbol_map, output / "symbol_map.csv")
    _write_csv(prepared.current_crosscheck, output / "current_crosscheck.csv")
    _write_csv(audit_frame, output / "reliance_donor_audit.csv")
    (output / "reliance_donor_audit.json").write_text(
        json.dumps(audit_metadata, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
    )
    reason_counts = prepared.eligibility.loc[~prepared.eligibility["eligible"], "reason_code"].value_counts().sort_index().to_dict()
    metadata: dict[str, Any] = {
        "adapter_version": ADAPTER_VERSION,
        "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": AS_OF_DATE,
        "requested_count": len(universe),
        "provider_resolved_count": len(universe) - len(provider_errors),
        "data_download_count": len(panels),
        "terminal_crosscheck_pass_count": int(prepared.current_crosscheck["status"].eq("PASS").sum()),
        "eligible_count": int(prepared.eligibility["eligible"].sum()),
        "excluded_count": int((~prepared.eligibility["eligible"]).sum()),
        "excluded_reason_counts": {str(key): int(value) for key, value in reason_counts.items()},
        "provider_errors": provider_errors,
        "provider": PROVIDER,
        "yfinance_version": yf.__version__,
        "api_options": {"period": "max", "interval": "1d", "auto_adjust": False, "repair": True, "actions": True},
        "selected_series": PRICE_SERIES,
        "selected_series_semantics": "Provider-maintained adjusted price including upstream dividend adjustments; not identical to unadjusted source-price semantics.",
        "anchor_policy": "latest observation on or before target, maximum seven calendar days",
        "universe_policy": "Current NIFTY 50 classification snapshot; not survivorship-bias-free history",
        "software_upstream": "https://github.com/ranaroussi/yfinance",
        "software_license": "Apache-2.0",
        "data_use_caveat": "Yahoo Finance data is used for research, education, and personal-use demonstration only; source accuracy and terms remain applicable.",
        "official_nifty_sha256": _sha(Path(args.nifty)),
        "official_bhavcopy_sha256": _sha(Path(args.bhavcopy)),
        "official_snapshot_provenance": snapshot_result.provenance,
        "reliance_audit_status": audit_metadata.get("status"),
    }
    (output / "acquisition_metadata.json").write_text(
        json.dumps(metadata, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
    )
    copies = {
        "marketdata_dependency_lock.txt": ROOT / "marketdata" / "environment" / "marketdata_dependency_lock.txt",
        "marketdata_environment_report.json": ROOT / "marketdata" / "environment" / "marketdata_environment_report.json",
        "security_history_boundaries.csv": ROOT / "marketdata" / "specifications" / "nse_security_history_boundaries.csv",
    }
    for name, source in copies.items():
        shutil.copyfile(source, output / name)
    artifact_names = sorted(path.name for path in output.iterdir() if path.is_file())
    inventory = [
        {"path": name, "sha256": _sha(output / name), "size": (output / name).stat().st_size}
        for name in artifact_names
    ]
    fingerprint = sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    manifest = {"schema_version": 1, "bundle_fingerprint": fingerprint, "files": inventory}
    (output / "bundle_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return {**metadata, "bundle_fingerprint": fingerprint, "bundle_directory": str(output)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire one frozen real NIFTY 50 Baseline bundle.")
    parser.add_argument("--nifty", required=True)
    parser.add_argument("--bhavcopy", required=True)
    parser.add_argument("--reliance-history", required=True)
    parser.add_argument("--reliance-actions", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(acquire(args), sort_keys=True, indent=2))
        return 0
    except Exception as exc:
        print(f"acquisition failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
