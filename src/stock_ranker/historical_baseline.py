"""Validated real-history adapter for the accepted Baseline V1 engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from stock_ranker.baseline import calculate_baseline_rankings, get_top_stocks_by_sector
from stock_ranker.config import BaselineConfig


ADAPTER_VERSION = "nifty50_real_history_adapter_v1"
PRICE_SERIES = "Yahoo Adj Close from repaired fetch (auto_adjust=False, repair=True)"
PROVIDER = "Yahoo Finance through yfinance 1.5.1"
AS_OF_DATE = "2026-08-07"
ANCHOR_TOLERANCE_DAYS = 7
CURRENT_ABSOLUTE_TOLERANCE = 0.05
CURRENT_RELATIVE_TOLERANCE = 0.0001
HISTORY_COLUMNS = ("date", "raw_close", "adjusted_close")
BUNDLE_FILES = (
    "baseline_input.csv", "anchor_metadata.csv", "eligibility.csv",
    "symbol_map.csv", "current_crosscheck.csv", "historical_prices.csv",
    "reliance_donor_audit.csv", "reliance_donor_audit.json",
    "acquisition_metadata.json", "marketdata_dependency_lock.txt",
    "marketdata_environment_report.json", "security_history_boundaries.csv",
)


@dataclass(frozen=True, slots=True)
class HistoricalBaselinePrepared:
    baseline_input: pd.DataFrame
    anchors: pd.DataFrame
    eligibility: pd.DataFrame
    symbol_map: pd.DataFrame
    current_crosscheck: pd.DataFrame


@dataclass(frozen=True, slots=True)
class HistoricalBaselineBundle:
    path: Path
    baseline_input: pd.DataFrame
    anchors: pd.DataFrame
    eligibility: pd.DataFrame
    symbol_map: pd.DataFrame
    current_crosscheck: pd.DataFrame
    metadata: dict[str, Any]
    fingerprint: str


def provider_symbol(nse_symbol: str) -> str:
    """Map an exact official NSE symbol to Yahoo without fuzzy matching."""
    if not isinstance(nse_symbol, str) or not nse_symbol.strip():
        raise ValueError("official NSE symbol must not be blank")
    symbol = nse_symbol.strip()
    if any(character.isspace() for character in symbol):
        raise ValueError("official NSE symbol must not contain whitespace")
    return f"{symbol}.NS"


def normalize_provider_history(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize provider dates and candidate closes without adjusting prices."""
    missing = [column for column in HISTORY_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError("provider history missing columns: " + ", ".join(missing))
    result = frame.loc[:, list(HISTORY_COLUMNS)].copy()
    parsed = pd.to_datetime(result["date"], errors="coerce", utc=True)
    if parsed.isna().any():
        raise ValueError("provider history contains malformed dates")
    result["date"] = parsed.dt.tz_convert("Asia/Kolkata").dt.date.astype(str)
    if result["date"].duplicated().any():
        raise ValueError("provider history contains duplicate normalized dates")
    for column in ("raw_close", "adjusted_close"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
        if (~np.isfinite(result[column]) | (result[column] <= 0)).any():
            raise ValueError(f"provider history {column} must be finite and positive")
    return result.sort_values("date", kind="stable").reset_index(drop=True)


def _prior_anchor(
    history: pd.DataFrame, target: date, *, tolerance_days: int
) -> tuple[str, float] | None:
    dates = pd.to_datetime(history["date"], format="%Y-%m-%d").dt.date
    eligible = history.loc[dates <= target]
    if eligible.empty:
        return None
    row = eligible.iloc[-1]
    selected = date.fromisoformat(str(row["date"]))
    if (target - selected).days > tolerance_days:
        return None
    return selected.isoformat(), float(row["adjusted_close"])


def prepare_historical_baseline(
    universe: pd.DataFrame,
    official_snapshot: pd.DataFrame,
    histories: Mapping[str, pd.DataFrame | None],
    *,
    as_of_date: str = AS_OF_DATE,
    tolerance_days: int = ANCHOR_TOLERANCE_DAYS,
    history_start_boundaries: pd.DataFrame | None = None,
) -> HistoricalBaselinePrepared:
    """Derive canonical Baseline inputs and explicit eligibility diagnostics."""
    required_universe = ("Symbol", "Company Name", "Industry")
    missing = [name for name in required_universe if name not in universe.columns]
    if missing:
        raise ValueError("universe missing columns: " + ", ".join(missing))
    if universe.empty or universe["Symbol"].astype(str).str.strip().duplicated().any():
        raise ValueError("universe symbols must be nonempty and unique")
    required_snapshot = ("ticker", "close")
    missing = [name for name in required_snapshot if name not in official_snapshot.columns]
    if missing:
        raise ValueError("official snapshot missing columns: " + ", ".join(missing))
    if official_snapshot["ticker"].duplicated().any():
        raise ValueError("official snapshot ticker must be unique")
    as_of = date.fromisoformat(as_of_date)
    boundary_by_ticker: dict[str, dict[str, str]] = {}
    if history_start_boundaries is not None:
        required_boundary = (
            "ticker", "valid_from_date", "boundary_type", "evidence_source"
        )
        missing = [
            name for name in required_boundary
            if name not in history_start_boundaries.columns
        ]
        if missing:
            raise ValueError(
                "history boundaries missing columns: " + ", ".join(missing)
            )
        boundaries = history_start_boundaries.loc[:, list(required_boundary)].copy()
        if boundaries["ticker"].isna().any() or boundaries["ticker"].astype(str).str.strip().duplicated().any():
            raise ValueError("history boundary tickers must be nonblank and unique")
        parsed_boundaries = pd.to_datetime(
            boundaries["valid_from_date"], format="%Y-%m-%d", errors="coerce"
        )
        if parsed_boundaries.isna().any():
            raise ValueError("history boundary valid_from_date must use ISO YYYY-MM-DD")
        if (parsed_boundaries.dt.date > as_of).any():
            raise ValueError("history boundary cannot be after as_of_date")
        for column in ("boundary_type", "evidence_source"):
            if boundaries[column].isna().any() or boundaries[column].astype(str).str.strip().eq("").any():
                raise ValueError(f"history boundary {column} must not be blank")
        for row in boundaries.to_dict("records"):
            boundary_by_ticker[str(row["ticker"]).strip()] = {
                "valid_from_date": str(row["valid_from_date"]),
                "boundary_type": str(row["boundary_type"]).strip(),
                "evidence_source": str(row["evidence_source"]).strip(),
            }
    snapshot_close = official_snapshot.set_index("ticker")["close"].to_dict()
    input_rows: list[dict[str, Any]] = []
    anchor_rows: list[dict[str, Any]] = []
    eligibility_rows: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, Any]] = []
    crosscheck_rows: list[dict[str, Any]] = []

    for identity in universe.loc[:, list(required_universe)].to_dict("records"):
        ticker = str(identity["Symbol"]).strip()
        yahoo = provider_symbol(ticker)
        reason_code, reason = "ELIGIBLE", "All frozen real-history quality gates passed."
        history = histories.get(ticker)
        mapping_status = "RESOLVED" if history is not None else "UNAVAILABLE"
        mapping_rows.append({"ticker": ticker, "provider_symbol": yahoo,
                             "status": mapping_status,
                             "reason": "Exact .NS mapping" if history is not None else "Provider returned no history"})
        anchors: dict[str, tuple[str, float]] = {}
        normalized: pd.DataFrame | None = None
        if history is None or history.empty:
            reason_code, reason = "PROVIDER_SYMBOL_UNAVAILABLE", "Provider returned no historical observations."
        else:
            try:
                normalized = normalize_provider_history(history)
            except ValueError as exc:
                message = str(exc)
                reason_code = "DUPLICATE_DATE" if "duplicate" in message else "NONFINITE_PRICE"
                reason = message
        if normalized is not None:
            targets = {
                "current": as_of,
                "close_1y": date(as_of.year - 1, as_of.month, as_of.day),
                "close_3y": date(as_of.year - 3, as_of.month, as_of.day),
                "close_5y": date(as_of.year - 5, as_of.month, as_of.day),
            }
            for name, target in targets.items():
                selected = _prior_anchor(normalized, target, tolerance_days=tolerance_days)
                if selected is not None:
                    anchors[name] = selected
            if "current" not in anchors:
                reason_code, reason = "CURRENT_PRICE_MISMATCH", "No current observation within the prior-date tolerance."
            else:
                official = float(snapshot_close.get(ticker, np.nan))
                provider_current = anchors["current"][1]
                absolute = abs(provider_current - official)
                relative = absolute / official if np.isfinite(official) and official > 0 else np.inf
                passed = np.isfinite(official) and (absolute <= CURRENT_ABSOLUTE_TOLERANCE or relative <= CURRENT_RELATIVE_TOLERANCE)
                crosscheck_rows.append({
                    "ticker": ticker, "provider_symbol": yahoo,
                    "official_nse_close": official, "provider_current_close": provider_current,
                    "absolute_difference": absolute, "relative_difference": relative,
                    "status": "PASS" if passed else "FAIL",
                })
                if not passed:
                    reason_code, reason = "CURRENT_PRICE_MISMATCH", "Provider terminal adjusted close did not match the official NSE close tolerance."
            for name, code in (("close_1y", "INSUFFICIENT_1Y_HISTORY"),
                               ("close_3y", "INSUFFICIENT_3Y_HISTORY"),
                               ("close_5y", "INSUFFICIENT_5Y_HISTORY")):
                if reason_code == "ELIGIBLE" and name not in anchors:
                    reason_code, reason = code, f"No prior trading observation within {tolerance_days} calendar days of the target."
                    break
            if reason_code == "ELIGIBLE":
                through_date = normalized.loc[normalized["date"] <= as_of.isoformat()]
                boundary = boundary_by_ticker.get(ticker)
                if boundary is not None:
                    through_date = through_date.loc[
                        through_date["date"] >= boundary["valid_from_date"]
                    ]
                if through_date.empty:
                    reason_code, reason = "RECORDED_HIGH_HISTORY_UNAVAILABLE", "No recorded history through the ranking date."
                else:
                    maximum = float(through_date["adjusted_close"].max())
                    high_rows = through_date.loc[through_date["adjusted_close"] == maximum]
                    high_date = str(high_rows.iloc[-1]["date"])
                    input_rows.append({
                        "ticker": ticker, "company": str(identity["Company Name"]).strip(),
                        "sector": str(identity["Industry"]).strip(), "as_of_date": as_of.isoformat(),
                        "current_price": anchors["current"][1], "close_1y_ago": anchors["close_1y"][1],
                        "close_3y_ago": anchors["close_3y"][1], "close_5y_ago": anchors["close_5y"][1],
                        "ath_date": high_date,
                    })
                    anchor_rows.append({
                        "ticker": ticker, "current_date": anchors["current"][0],
                        "current_price": anchors["current"][1],
                        "close_1y_date": anchors["close_1y"][0], "close_1y_ago": anchors["close_1y"][1],
                        "close_3y_date": anchors["close_3y"][0], "close_3y_ago": anchors["close_3y"][1],
                        "close_5y_date": anchors["close_5y"][0], "close_5y_ago": anchors["close_5y"][1],
                        "recorded_high_date": high_date, "recorded_high_price": maximum,
                        "recorded_high_search_start_date": (
                            boundary["valid_from_date"] if boundary is not None
                            else str(normalized.iloc[0]["date"])
                        ),
                        "recorded_high_search_start_basis": (
                            boundary["boundary_type"] if boundary is not None
                            else "PROVIDER_MAX_HISTORY_START"
                        ),
                        "recorded_high_search_start_evidence": (
                            boundary["evidence_source"] if boundary is not None
                            else "Yahoo Finance maximum available history"
                        ),
                    })
        eligibility_rows.append({
            "ticker": ticker, "company": str(identity["Company Name"]).strip(),
            "sector": str(identity["Industry"]).strip(), "eligible": reason_code == "ELIGIBLE",
            "reason_code": reason_code, "reason": reason,
        })

    return HistoricalBaselinePrepared(
        baseline_input=pd.DataFrame(input_rows), anchors=pd.DataFrame(anchor_rows),
        eligibility=pd.DataFrame(eligibility_rows), symbol_map=pd.DataFrame(mapping_rows),
        current_crosscheck=pd.DataFrame(crosscheck_rows),
    )


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_historical_baseline_bundle(path: str | Path) -> HistoricalBaselineBundle:
    """Load a frozen bundle after validating its manifest and file hashes."""
    root = Path(path).resolve()
    if not root.is_dir():
        raise ValueError(f"prepared real-history bundle directory does not exist: {root}")
    manifest_path = root / "bundle_manifest.json"
    if not manifest_path.is_file():
        raise ValueError("prepared bundle is missing bundle_manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"prepared bundle manifest is unreadable: {exc}") from exc
    inventory = manifest.get("files")
    if not isinstance(inventory, list):
        raise ValueError("prepared bundle manifest files must be a list")
    for entry in inventory:
        relative = entry.get("path") if isinstance(entry, dict) else None
        expected = entry.get("sha256") if isinstance(entry, dict) else None
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("prepared bundle manifest contains an unsafe path")
        target = root / relative
        if not target.is_file() or _file_hash(target) != expected:
            raise ValueError(f"prepared bundle hash mismatch: {relative}")
    fingerprint = str(manifest.get("bundle_fingerprint", ""))
    canonical = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
    if fingerprint != sha256(canonical).hexdigest():
        raise ValueError("prepared bundle fingerprint is invalid")
    required = set(BUNDLE_FILES)
    found = {entry["path"] for entry in inventory}
    if not required.issubset(found):
        raise ValueError("prepared bundle is incomplete: " + ", ".join(sorted(required - found)))
    metadata = json.loads((root / "acquisition_metadata.json").read_text(encoding="utf-8"))
    if metadata.get("adapter_version") != ADAPTER_VERSION:
        raise ValueError("prepared bundle adapter version is unsupported")
    return HistoricalBaselineBundle(
        path=root,
        baseline_input=pd.read_csv(root / "baseline_input.csv"),
        anchors=pd.read_csv(root / "anchor_metadata.csv"),
        eligibility=pd.read_csv(root / "eligibility.csv"),
        symbol_map=pd.read_csv(root / "symbol_map.csv"),
        current_crosscheck=pd.read_csv(root / "current_crosscheck.csv"),
        metadata=metadata, fingerprint=fingerprint,
    )


def calculate_prepared_real_rankings(
    bundle: HistoricalBaselineBundle, top_n: int = 5
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rankings = calculate_baseline_rankings(
        bundle.baseline_input, BaselineConfig(top_n=top_n)
    )
    return rankings, get_top_stocks_by_sector(rankings, top_n)
