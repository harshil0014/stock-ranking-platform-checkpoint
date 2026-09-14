"""Acquire Upstox historical fundamentals as PIT candidates, never as PIT truth.

The Analytics Token is read from ``UPSTOX_ACCESS_TOKEN`` only.  It is never
accepted on the command line and is never written to output.  Raw responses are
cached under the selected output directory so a long run can be resumed.

Example probe (Windows CMD):

    set UPSTOX_ACCESS_TOKEN=<token set locally, not committed>
    .venv-test\Scripts\python marketdata\runners\acquire_upstox_v2_candidates.py ^
      --company-facts data\company_facts\snapshots\...\company_facts.csv ^
      --output data\point_in_time\upstox_v2_probe_20260914 --limit 100

Use ``--all`` only after the probe is reviewed.  Present-day Upstox values are
not promoted to Research V2 by this runner.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.upstox_fundamentals import (  # noqa: E402
    UPSTOX_API_BASE,
    build_profit_pairs,
    canonical_json_bytes,
    normalize_balance_sheet,
    normalize_income_statement,
    validate_isin,
)


USER_AGENT = "StockRankingResearch/0.2 PIT-candidate-acquisition"
MAX_RESPONSE_BYTES = 10_000_000
DEFAULT_SLEEP_SECONDS = 1.1  # stays below the documented 2,000 / 30 min ceiling
PROVENANCE_SCHEMA = "upstox_v2_candidate_acquisition_v1"


class UpstoxFetchError(RuntimeError):
    pass


def _truthy(series: pd.Series) -> pd.Series:
    return series.map(
        lambda value: value is True
        or str(value).strip().lower() in {"1", "true", "yes", "y"}
    )


def load_targets(
    *, targets_path: Path | None, company_facts_path: Path | None,
    include_eligible: bool,
) -> pd.DataFrame:
    if (targets_path is None) == (company_facts_path is None):
        raise ValueError("supply exactly one of --targets or --company-facts")
    source = targets_path or company_facts_path
    assert source is not None
    frame = pd.read_csv(source, low_memory=False)
    missing = {"ticker", "isin"} - set(frame.columns)
    if missing:
        raise ValueError(f"target source missing columns: {sorted(missing)}")
    if company_facts_path is not None and not include_eligible and "v2_eligible" in frame.columns:
        frame = frame.loc[~_truthy(frame["v2_eligible"])].copy()
    frame = frame.loc[:, ["ticker", "isin"]].copy()
    frame["ticker"] = frame["ticker"].astype(str).str.strip()
    frame["isin"] = frame["isin"].astype(str).str.strip().str.upper()
    frame = frame.loc[frame["ticker"].ne("") & frame["isin"].ne("")].copy()
    frame["isin"] = frame["isin"].map(validate_isin)
    if frame["ticker"].duplicated().any():
        duplicates = frame.loc[frame["ticker"].duplicated(keep=False), "ticker"].tolist()
        raise ValueError(f"duplicate target tickers: {duplicates[:10]}")
    ticker_per_isin = frame.groupby("isin")["ticker"].nunique()
    ambiguous = ticker_per_isin[ticker_per_isin.gt(1)]
    if not ambiguous.empty:
        raise ValueError(f"multiple target tickers for ISIN(s): {ambiguous.index.tolist()[:10]}")
    return frame.sort_values(["ticker", "isin"], kind="stable").reset_index(drop=True)


def _fetch_json(url: str, *, token: str) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.upstox.com":
        raise ValueError(f"refusing non-Upstox URL: {url}")
    request = Request(url, headers={
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT,
    })
    try:
        with urlopen(request, timeout=60) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        raise UpstoxFetchError(
            f"HTTP_{exc.code}" + (f" retry_after={retry_after}" if retry_after else "")
        ) from exc
    except URLError as exc:
        raise UpstoxFetchError(f"NETWORK_ERROR:{exc.reason}") from exc
    if not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise UpstoxFetchError("INVALID_RESPONSE_SIZE")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UpstoxFetchError("INVALID_JSON") from exc
    if not isinstance(payload, dict):
        raise UpstoxFetchError("INVALID_JSON_ROOT")
    return payload


def _endpoint_url(isin: str, endpoint: str, basis: str) -> str:
    if endpoint == "income-statement":
        query = urlencode({"type": basis, "time_period": "yearly", "fs": "true"})
    elif endpoint == "balance-sheet":
        query = urlencode({"type": basis, "fs": "true"})
    else:
        raise ValueError(f"unsupported endpoint: {endpoint}")
    return f"{UPSTOX_API_BASE}/{isin}/{endpoint}?{query}"


def _raw_path(output: Path, ticker: str, endpoint: str) -> Path:
    safe = "".join(character if character.isalnum() or character in "-_." else "_" for character in ticker)
    return output / "raw" / endpoint / f"{safe}.json"


def _write_json(path: Path, payload: Any) -> str:
    content = canonical_json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return sha256(content).hexdigest()


def _load_provenance(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != PROVENANCE_SCHEMA:
        raise ValueError("unexpected Upstox acquisition provenance schema")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("malformed Upstox acquisition provenance")
    return records


def _persist_provenance(path: Path, records: list[dict[str, Any]]) -> None:
    _write_json(path, {"schema_version": PROVENANCE_SCHEMA, "records": records})


def _normalize_all(output: Path, records: list[dict[str, Any]], *, basis: str) -> dict[str, int]:
    income_frames: list[pd.DataFrame] = []
    balance_frames: list[pd.DataFrame] = []
    successful = [row for row in records if row.get("status") == "FETCHED"]
    for row in sorted(successful, key=lambda item: (item["ticker"], item["endpoint"])):
        raw_path = output / str(row["raw_path"])
        if not raw_path.is_file():
            raise ValueError(f"cached Upstox payload missing: {raw_path}")
        raw_bytes = raw_path.read_bytes()
        actual_sha = sha256(raw_bytes).hexdigest()
        if actual_sha != row["raw_sha256"]:
            raise ValueError(f"cached Upstox payload hash mismatch: {row['ticker']}/{row['endpoint']}")
        payload = json.loads(raw_bytes)
        if row["endpoint"] == "income-statement":
            income_frames.append(normalize_income_statement(
                payload, isin=row["isin"], reporting_basis=basis,
                source_observed_at=row["observed_at"],
            ))
        elif row["endpoint"] == "balance-sheet":
            balance_frames.append(normalize_balance_sheet(
                payload, isin=row["isin"], reporting_basis=basis,
                source_observed_at=row["observed_at"],
            ))
    income = pd.concat(income_frames, ignore_index=True) if income_frames else pd.DataFrame()
    balance = pd.concat(balance_frames, ignore_index=True) if balance_frames else pd.DataFrame()
    pairs = build_profit_pairs(income) if not income.empty else pd.DataFrame()
    normalized = output / "normalized"
    normalized.mkdir(parents=True, exist_ok=True)
    income.to_csv(normalized / "income_facts.csv", index=False, encoding="utf-8", lineterminator="\n")
    balance.to_csv(normalized / "balance_facts.csv", index=False, encoding="utf-8", lineterminator="\n")
    pairs.to_csv(normalized / "profit_pairs.csv", index=False, encoding="utf-8", lineterminator="\n")
    return {
        "income_fact_rows": int(len(income)),
        "balance_fact_rows": int(len(balance)),
        "profit_pair_rows": int(len(pairs)),
        "historical_roce_rows_promoted": 0,
        "historical_debt_to_equity_rows_promoted": 0,
    }


def acquire(
    *, targets: pd.DataFrame, output: Path, token: str, basis: str,
    limit: int | None, resume: bool, sleep_seconds: float,
) -> dict[str, Any]:
    if basis not in {"standalone", "consolidated"}:
        raise ValueError("basis must be standalone or consolidated")
    if not token.strip():
        raise ValueError("UPSTOX_ACCESS_TOKEN is blank")
    if sleep_seconds < 0:
        raise ValueError("sleep seconds cannot be negative")
    if output.exists() and not resume:
        raise ValueError(f"output already exists; use --resume: {output}")
    output.mkdir(parents=True, exist_ok=True)
    provenance_path = output / "provenance.json"
    records = _load_provenance(provenance_path) if resume else []
    completed = {
        (str(row.get("ticker")), str(row.get("endpoint")))
        for row in records if row.get("status") == "FETCHED"
    }
    selected = targets if limit is None else targets.head(limit)
    endpoint_names = ("income-statement", "balance-sheet")
    attempted = 0
    fetched = 0
    failed = 0
    for target in selected.itertuples(index=False):
        for endpoint in endpoint_names:
            key = (str(target.ticker), endpoint)
            if key in completed:
                continue
            attempted += 1
            observed_at = datetime.now(timezone.utc).isoformat()
            try:
                payload = _fetch_json(
                    _endpoint_url(str(target.isin), endpoint, basis), token=token
                )
                raw_path = _raw_path(output, str(target.ticker), endpoint)
                raw_sha = _write_json(raw_path, payload)
                # Normalize before marking the response successful.  This catches
                # basis/schema surprises at acquisition time rather than later.
                if endpoint == "income-statement":
                    normalize_income_statement(
                        payload, isin=str(target.isin), reporting_basis=basis,
                        source_observed_at=observed_at,
                    )
                else:
                    normalize_balance_sheet(
                        payload, isin=str(target.isin), reporting_basis=basis,
                        source_observed_at=observed_at,
                    )
                records.append({
                    "ticker": str(target.ticker), "isin": str(target.isin),
                    "endpoint": endpoint, "reporting_basis": basis.upper(),
                    "observed_at": observed_at, "status": "FETCHED",
                    "raw_path": raw_path.relative_to(output).as_posix(),
                    "raw_sha256": raw_sha,
                })
                completed.add(key)
                fetched += 1
            except Exception as exc:
                records.append({
                    "ticker": str(target.ticker), "isin": str(target.isin),
                    "endpoint": endpoint, "reporting_basis": basis.upper(),
                    "observed_at": observed_at, "status": "FAILED",
                    "error_class": type(exc).__name__, "error": str(exc),
                })
                failed += 1
            _persist_provenance(provenance_path, records)
            if sleep_seconds:
                time.sleep(sleep_seconds)
    normalization = _normalize_all(output, records, basis=basis)
    summary = {
        "schema_version": PROVENANCE_SCHEMA,
        "target_count": int(len(selected)), "endpoint_attempt_count": attempted,
        "endpoint_fetched_this_run": fetched, "endpoint_failed_this_run": failed,
        "endpoint_fetched_total": int(sum(row.get("status") == "FETCHED" for row in records)),
        "reporting_basis": basis.upper(),
        "source": "Upstox Company Fundamentals v2",
        "pit_policy": (
            "CANDIDATE_ONLY: present-day Upstox historical periods are not historical "
            "availability evidence. Exact official filing match + exchange dissemination "
            "time is required before Research V2 promotion."
        ),
        "key_ratios_policy": "CURRENT_KEY_RATIOS_NOT_ACQUIRED_FOR_PIT",
        **normalization,
    }
    _write_json(output / "summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire PIT-candidate Upstox fundamentals.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--targets", type=Path)
    source.add_argument("--company-facts", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--basis", choices=("standalone", "consolidated"), default="standalone")
    parser.add_argument("--limit", type=int, default=100, help="Probe size; ignored by --all.")
    parser.add_argument("--all", action="store_true", help="Acquire every selected target.")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--include-v2-eligible", action="store_true")
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS)
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    token = os.environ.get("UPSTOX_ACCESS_TOKEN", "")
    if not token.strip():
        print(
            "UPSTOX_ACCESS_TOKEN is not set. Generate a read-only Analytics Token and "
            "set it only in the local environment; never commit it.",
            file=sys.stderr,
        )
        return 2
    try:
        targets = load_targets(
            targets_path=args.targets, company_facts_path=args.company_facts,
            include_eligible=args.include_v2_eligible,
        )
        summary = acquire(
            targets=targets, output=args.output, token=token, basis=args.basis,
            limit=None if args.all else args.limit, resume=args.resume,
            sleep_seconds=args.sleep_seconds,
        )
    except Exception as exc:
        print(f"Upstox candidate acquisition failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
