"""Acquire broad Yahoo facts as secondary/reference evidence with resume support."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402

from stock_ranker.data_state import atomic_write_json, resolve_accepted_bundle_root  # noqa: E402
from stock_ranker.live_market import load_live_market_bundle  # noqa: E402
from stock_ranker.exchange_backbone import (  # noqa: E402
    BACKLOG_COLUMNS, due_backlog, initialize_backlog, update_backlog,
)
from stock_ranker.secondary_facts import (  # noqa: E402
    YAHOO_OBSERVATION_VERSION,
    load_yahoo_secondary_bundle,
    sha256_file,
    validate_yahoo_observations,
    validate_yahoo_identity,
    yahoo_numeric_fact,
    yahoo_coverage,
)


INFO_FIELDS = (
    "symbol", "longName", "shortName", "exchange", "quoteType", "currency",
    "sector", "industry", "longBusinessSummary", "marketCap", "sharesOutstanding",
    "trailingPE", "priceToBook", "trailingEps", "bookValue",
    "trailingAnnualDividendYield", "dividendYield", "beta",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "returnOnEquity", "debtToEquity",
    "revenueGrowth", "earningsGrowth", "operatingMargins", "profitMargins",
)
STATEMENT_FIELDS = {
    "annual_income": (
        "Total Revenue", "Operating Revenue", "EBIT", "EBITDA", "Pretax Income",
        "Tax Provision", "Net Income", "Basic EPS", "Diluted EPS",
    ),
    "quarterly_income": (
        "Total Revenue", "Operating Revenue", "EBIT", "EBITDA", "Pretax Income",
        "Tax Provision", "Net Income", "Basic EPS", "Diluted EPS",
    ),
    "balance_sheet": (
        "Total Assets", "Current Assets", "Cash Cash Equivalents And Short Term Investments",
        "Inventory", "Receivables", "Total Liabilities Net Minority Interest",
        "Current Liabilities", "Total Debt", "Stockholders Equity", "Ordinary Shares Number",
    ),
    "cash_flow": (
        "Operating Cash Flow", "Investing Cash Flow", "Financing Cash Flow",
        "Capital Expenditure", "Free Cash Flow", "End Cash Position",
    ),
}


def _clean_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _provider_symbols(market: pd.DataFrame, strategy_path: Path) -> dict[str, str]:
    mapping = {
        str(row.isin): f"{row.ticker}.NS"
        for row in market.loc[market["primary_exchange"].eq("NSE")].itertuples(index=False)
    }
    if strategy_path.is_file():
        strategy = pd.read_csv(strategy_path, low_memory=False)
        for row in strategy.itertuples(index=False):
            symbol = _clean_text(getattr(row, "provider_symbol", None))
            canonical = market.loc[market["isin"].astype(str).eq(str(row.isin))]
            is_bse_only = not canonical.empty and canonical["primary_exchange"].eq("BSE").all()
            if is_bse_only and symbol and symbol.lower() != "nan" and symbol.upper().endswith(".BO"):
                mapping[str(row.isin)] = symbol.upper()
    return mapping


def _select(market: pd.DataFrame, mapping: dict[str, str], strategy_path: Path, limit: int, full_market: bool) -> pd.DataFrame:
    candidates = market.loc[market["isin"].astype(str).isin(mapping)].copy()
    candidates["provider_symbol"] = candidates["isin"].astype(str).map(mapping)
    candidates["priority"] = 1
    if strategy_path.is_file():
        professor_isins = set(pd.read_csv(strategy_path, usecols=["isin"])["isin"].dropna().astype(str))
        candidates.loc[candidates["isin"].astype(str).isin(professor_isins), "priority"] = 0
    if full_market:
        return candidates.sort_values(["priority", "primary_exchange", "ticker"], kind="stable")
    professor = candidates.loc[candidates["priority"].eq(0)]
    other = candidates.loc[candidates["priority"].eq(1)].copy()
    other["stratum"] = (
        other["primary_exchange"].astype(str) + "|" + other["size_segment"].fillna("UNKNOWN").astype(str)
        + "|" + other["classification_status"].fillna("UNKNOWN").astype(str)
    )
    other["sample_key"] = other["isin"].astype(str).map(lambda value: hashlib.sha256(value.encode()).hexdigest())
    groups = [group.sort_values("sample_key", kind="stable") for _, group in other.groupby("stratum", sort=True)]
    selected: list[pd.Series] = []
    index = 0
    while len(selected) < limit and any(index < len(group) for group in groups):
        for group in groups:
            if index < len(group) and len(selected) < limit:
                selected.append(group.iloc[index])
        index += 1
    sampled = pd.DataFrame(selected).drop(columns=["stratum", "sample_key"], errors="ignore") if selected else other.iloc[0:0]
    return pd.concat([professor, sampled], ignore_index=True).drop_duplicates("isin").sort_values(["priority", "primary_exchange", "ticker"], kind="stable")


def _statement_records(ticker: Any, kind: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if frame is None or frame.empty:
        return records
    for concept in STATEMENT_FIELDS[kind]:
        if concept not in frame.index:
            continue
        for period, value in frame.loc[concept].items():
            number = _clean_number(value)
            if number is not None:
                records.append({
                    "ticker": ticker, "statement": kind, "canonical_concept": concept.lower().replace(" ", "_"),
                    "provider_concept": concept, "period_end": pd.Timestamp(period).date().isoformat(),
                    "value": number, "unit": "provider currency units", "source": "Yahoo Finance",
                    "verification_status": "SECONDARY_REFERENCE", "reporting_basis": "YAHOO_PROVIDER_BASIS_UNSPECIFIED",
                })
    return records


def _fetch(row: Any, version: str) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    ticker = str(row.ticker)
    symbol = str(row.provider_symbol).upper()
    base = {
        "ticker": ticker, "isin": str(row.isin), "primary_exchange": str(row.primary_exchange),
        "provider_symbol": symbol, "provider_version": version,
    }
    try:
        provider = yf.Ticker(symbol)
        info = provider.info or {}
        returned_symbol = _clean_text(info.get("symbol"))
        returned_exchange = _clean_text(info.get("exchange"))
        quote_type = _clean_text(info.get("quoteType"))
        identity_ok, identity_reason = validate_yahoo_identity(
            provider_symbol=symbol, primary_exchange=str(row.primary_exchange),
            returned_symbol=returned_symbol, returned_exchange=returned_exchange,
            returned_quote_type=quote_type,
        )
        if not identity_ok:
            return {"base": base, "status": "REJECTED_IDENTITY", "reason": identity_reason, "info": {}, "financials": [], "actions": []}
        frames: dict[str, pd.DataFrame] = {}
        getters = {
            "annual_income": lambda: provider.income_stmt,
            "quarterly_income": lambda: provider.quarterly_income_stmt,
            "balance_sheet": lambda: provider.balance_sheet,
            "cash_flow": lambda: provider.cashflow,
        }
        for name, getter in getters.items():
            try:
                frames[name] = getter()
            except Exception:
                frames[name] = pd.DataFrame()
        financials = [record for name, frame in frames.items() for record in _statement_records(ticker, name, frame)]
        try:
            actions = provider.actions
        except Exception:
            actions = pd.DataFrame()
        action_records = []
        if actions is not None and not actions.empty:
            for action_date, values in actions.iterrows():
                for action_type in ("Dividends", "Stock Splits", "Capital Gains"):
                    number = _clean_number(values.get(action_type))
                    if number not in (None, 0.0):
                        action_records.append({"ticker": ticker, "date": pd.Timestamp(action_date).date().isoformat(), "action_type": action_type, "value": number, "source": "Yahoo Finance", "verification_status": "SECONDARY_REFERENCE"})
        holder_status = "NO_USEFUL_FACTS"
        try:
            holders = provider.major_holders
            if holders is not None and not holders.empty and holders.notna().any(axis=None):
                holder_status = "USEFUL_FACTS"
        except Exception:
            pass
        statuses = {}
        for kind in STATEMENT_FIELDS:
            statuses[kind] = "USEFUL_FACTS" if any(record["statement"] == kind for record in financials) else "NO_USEFUL_FACTS"
        return {"base": base, "status": "EXCHANGE_SYMBOL_MATCH", "reason": identity_reason, "info": {key: info.get(key) for key in INFO_FIELDS}, "financials": financials, "actions": action_records, "statuses": statuses, "holder_status": holder_status, "retrieved_at": started.isoformat()}
    except Exception as exc:
        return {"base": base, "status": "PROVIDER_ERROR", "reason": f"{type(exc).__name__}: {str(exc)[:300]}", "info": {}, "financials": [], "actions": [], "retrieved_at": started.isoformat()}


def _observation(result: dict[str, Any]) -> dict[str, Any]:
    base, info = result["base"], result.get("info", {})
    accepted = result["status"] == "EXCHANGE_SYMBOL_MATCH"
    retrieved = result.get("retrieved_at") or datetime.now(timezone.utc).isoformat()
    next_due = (datetime.fromisoformat(retrieved) + timedelta(days=1)).isoformat()
    value = lambda key: info.get(key) if accepted else None
    statuses = result.get("statuses", {})
    return {
        **base, "retrieved_at": retrieved, "source_as_of": retrieved,
        "last_checked_at": retrieved, "last_changed_at": retrieved, "next_check_due": next_due,
        "freshness_status": "CURRENT" if accepted else "SOURCE_TEMPORARILY_UNAVAILABLE" if result["status"] == "PROVIDER_ERROR" else "STALE",
        "identity_status": result["status"], "identity_reason": result["reason"],
        "returned_symbol": value("symbol"), "returned_exchange": value("exchange"),
        "returned_quote_type": value("quoteType"), "returned_name": value("longName") or value("shortName"),
        "currency": value("currency"), "sector": value("sector"), "industry": value("industry"),
        "company_profile": value("longBusinessSummary"), "market_cap": yahoo_numeric_fact(info, "marketCap") if accepted else None,
        "shares_outstanding": yahoo_numeric_fact(info, "sharesOutstanding") if accepted else None,
        "trailing_pe": yahoo_numeric_fact(info, "trailingPE") if accepted else None,
        "price_to_book": yahoo_numeric_fact(info, "priceToBook") if accepted else None,
        "trailing_eps": yahoo_numeric_fact(info, "trailingEps") if accepted else None,
        "book_value": yahoo_numeric_fact(info, "bookValue") if accepted else None,
        "dividend_yield_decimal": yahoo_numeric_fact(info, "trailingAnnualDividendYield") if accepted else None,
        "beta": yahoo_numeric_fact(info, "beta") if accepted else None,
        "fifty_two_week_high": yahoo_numeric_fact(info, "fiftyTwoWeekHigh") if accepted else None,
        "fifty_two_week_low": yahoo_numeric_fact(info, "fiftyTwoWeekLow") if accepted else None,
        "return_on_equity": yahoo_numeric_fact(info, "returnOnEquity") if accepted else None,
        "debt_to_equity_decimal": yahoo_numeric_fact(info, "debtToEquity", percentage_points=True) if accepted else None,
        "revenue_growth": yahoo_numeric_fact(info, "revenueGrowth") if accepted else None,
        "earnings_growth": yahoo_numeric_fact(info, "earningsGrowth") if accepted else None,
        "operating_margin": yahoo_numeric_fact(info, "operatingMargins") if accepted else None,
        "profit_margin": yahoo_numeric_fact(info, "profitMargins") if accepted else None,
        "annual_income_status": statuses.get("annual_income") if accepted else None,
        "quarterly_income_status": statuses.get("quarterly_income") if accepted else None,
        "balance_sheet_status": statuses.get("balance_sheet") if accepted else None,
        "cash_flow_status": statuses.get("cash_flow") if accepted else None,
        "corporate_actions_status": "USEFUL_FACTS" if accepted and result.get("actions") else "NO_USEFUL_FACTS" if accepted else None,
        "holder_data_status": result.get("holder_status") if accepted else None,
        "error_code": None if accepted else result["status"], "error_message": None if accepted else result["reason"],
    }


def _is_throttle(result: dict[str, Any]) -> bool:
    text = str(result.get("reason", "")).lower()
    return result.get("status") == "PROVIDER_ERROR" and any(
        token in text for token in ("429", "too many requests", "rate limit", "invalid crumb")
    )


def _save_backlog(path: Path, frame: pd.DataFrame) -> None:
    frame.loc[:, BACKLOG_COLUMNS].to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire identity-validated Yahoo secondary company facts.")
    parser.add_argument("--batch-id", default="benchmark-20260822")
    parser.add_argument("--limit", type=int, default=250, help="Non-professor deterministic sample size.")
    parser.add_argument("--full-market", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-errors", action="store_true", help="On resume, retry only checkpoints with transient provider errors.")
    parser.add_argument("--seed-batch", help="Previously validated batch whose accepted checkpoints may seed a fresh broader batch.")
    parser.add_argument("--drain-backlog", action="store_true", help="Fetch one conservative durable-backlog batch and stop on throttling.")
    parser.add_argument("--provider-budget", type=int, default=20)
    parser.add_argument("--cooldown-hours", type=int, default=24)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "data/company_facts/providers/yahoo")
    args = parser.parse_args(argv)
    if args.limit < 0 or not 1 <= args.workers <= 6 or args.provider_budget < 1 or args.cooldown_hours < 1:
        parser.error("limit must be nonnegative and workers must be 1 through 6")
    bundle = load_live_market_bundle(resolve_accepted_bundle_root(PROJECT_ROOT / "data/live_market"))
    strategy_path = PROJECT_ROOT / "data/professor_reference/strategy_current/professor_strategy_comparison.csv"
    mapping = _provider_symbols(bundle.market, strategy_path)
    selected = _select(bundle.market, mapping, strategy_path, args.limit, args.full_market)
    backlog_path = args.output_root / "backlog.csv"
    prior_bundle = None
    pointer_path = args.output_root / "accepted_state.json"
    if pointer_path.is_file():
        state = json.loads(pointer_path.read_text(encoding="utf-8"))
        prior_bundle = load_yahoo_secondary_bundle(args.output_root / str(state["accepted_batch"]))
    backlog = None
    if args.drain_backlog:
        if args.workers != 1:
            parser.error("drain-backlog requires workers=1")
        all_candidates = _select(bundle.market, mapping, strategy_path, 0, True)
        candidate_columns = all_candidates.loc[:, ["ticker", "isin", "provider_symbol", "priority"]]
        prior_backlog = pd.read_csv(backlog_path, low_memory=False) if backlog_path.is_file() else None
        backlog = initialize_backlog(candidate_columns, prior_backlog)
        if prior_bundle is not None:
            accepted_isins = set(prior_bundle.observations.loc[
                prior_bundle.observations["identity_status"].eq("EXCHANGE_SYMBOL_MATCH"), "isin"
            ].astype(str))
            backlog.loc[backlog["isin"].astype(str).isin(accepted_isins), "completion_status"] = "ACCEPTED"
        due = due_backlog(backlog, now=datetime.now(timezone.utc).isoformat(), limit=args.provider_budget)
        selected = all_candidates.loc[all_candidates["isin"].astype(str).isin(set(due["isin"].astype(str)))].copy()
        selected = selected.sort_values(["priority", "ticker"], kind="stable")
    batch = args.output_root / args.batch_id
    checkpoint = batch / "checkpoints"
    if args.dry_run:
        print(json.dumps({"would_write": False, "selected": len(selected), "professor_rows": int(selected["priority"].eq(0).sum()), "sample_rows": int(selected["priority"].eq(1).sum()), "workers": args.workers, "provider_version": yf.__version__}, sort_keys=True))
        return 0
    if batch.exists() and not args.resume:
        raise ValueError("Yahoo batch exists; use --resume or a fresh batch ID")
    checkpoint.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, Any]] = {}
    seed_checkpoint = args.output_root / args.seed_batch / "checkpoints" if args.seed_batch else None
    pending = []
    for row in selected.itertuples(index=False):
        path = checkpoint / f"{row.ticker}.json"
        if args.resume and path.is_file():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if args.retry_errors and existing.get("status") == "PROVIDER_ERROR":
                pending.append(row)
            else:
                results[str(row.ticker)] = existing
        elif seed_checkpoint is not None and (seed_checkpoint / f"{row.ticker}.json").is_file():
            seeded = json.loads((seed_checkpoint / f"{row.ticker}.json").read_text(encoding="utf-8"))
            if seeded.get("base", {}).get("isin") == str(row.isin) and seeded.get("base", {}).get("provider_symbol") == str(row.provider_symbol):
                results[str(row.ticker)] = seeded
                atomic_write_json(path, seeded)
            else:
                pending.append(row)
        else:
            pending.append(row)
    if args.drain_backlog:
        for row in pending:
            result = _fetch(row, yf.__version__)
            results[str(row.ticker)] = result
            atomic_write_json(checkpoint / f"{row.ticker}.json", result)
            attempted = datetime.now(timezone.utc).isoformat()
            status = "ACCEPTED" if result["status"] == "EXCHANGE_SYMBOL_MATCH" else "PERMANENTLY_REJECTED" if result["status"] == "REJECTED_IDENTITY" else "TRANSIENT_FAILED"
            retry = (datetime.now(timezone.utc) + timedelta(hours=args.cooldown_hours)).isoformat() if status == "TRANSIENT_FAILED" else None
            backlog = update_backlog(backlog, str(row.ticker), status=status,
                                     error_class=None if status == "ACCEPTED" else str(result["status"]),
                                     attempted_at=attempted, retry_after=retry)
            _save_backlog(backlog_path, backlog)
            if _is_throttle(result):
                break
            time.sleep(1.0)
        selected = selected.loc[selected["ticker"].astype(str).isin(results)]
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_fetch, row, yf.__version__): row for row in pending}
            for future in as_completed(futures):
                row = futures[future]
                result = future.result()
                results[str(row.ticker)] = result
                atomic_write_json(checkpoint / f"{row.ticker}.json", result)
                time.sleep(0.05)
    ordered = [results[str(row.ticker)] for row in selected.itertuples(index=False)]
    observations = pd.DataFrame([_observation(result) for result in ordered])
    if pointer_path.is_file():
        try:
            prior_state = json.loads(pointer_path.read_text(encoding="utf-8"))
            prior = load_yahoo_secondary_bundle(args.output_root / str(prior_state["accepted_batch"])).observations.set_index("isin")
            volatile = [
                "identity_status", "returned_symbol", "returned_exchange", "returned_quote_type",
                "sector", "industry", "company_profile", "market_cap", "shares_outstanding",
                "trailing_pe", "price_to_book", "trailing_eps", "book_value",
                "dividend_yield_decimal", "beta", "fifty_two_week_high", "fifty_two_week_low",
                "return_on_equity", "debt_to_equity_decimal", "revenue_growth", "earnings_growth",
                "operating_margin", "profit_margin", "annual_income_status", "quarterly_income_status",
                "balance_sheet_status", "cash_flow_status", "corporate_actions_status", "holder_data_status",
            ]
            for index, row in observations.iterrows():
                isin = str(row["isin"])
                if isin not in prior.index:
                    continue
                previous = prior.loc[isin]
                def same(name: str) -> bool:
                    left, right = row[name], previous[name]
                    return (pd.isna(left) and pd.isna(right)) or left == right
                if all(same(name) for name in volatile):
                    observations.at[index, "last_changed_at"] = previous["last_changed_at"]
        except (FileNotFoundError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    observations = validate_yahoo_observations(observations)
    financials = pd.DataFrame([record for result in ordered for record in result.get("financials", [])], columns=["ticker", "statement", "canonical_concept", "provider_concept", "period_end", "value", "unit", "source", "verification_status", "reporting_basis"])
    actions = pd.DataFrame([record for result in ordered for record in result.get("actions", [])], columns=["ticker", "date", "action_type", "value", "source", "verification_status"])
    if args.drain_backlog and prior_bundle is not None:
        refreshed = set(observations["isin"].astype(str))
        observations = validate_yahoo_observations(pd.concat([
            prior_bundle.observations.loc[~prior_bundle.observations["isin"].astype(str).isin(refreshed)],
            observations,
        ], ignore_index=True))
        refreshed_tickers = set(selected["ticker"].astype(str))
        financials = pd.concat([
            prior_bundle.financial_facts.loc[~prior_bundle.financial_facts["ticker"].astype(str).isin(refreshed_tickers)],
            financials,
        ], ignore_index=True)
        actions = pd.concat([
            prior_bundle.corporate_actions.loc[~prior_bundle.corporate_actions["ticker"].astype(str).isin(refreshed_tickers)],
            actions,
        ], ignore_index=True)
    observations.to_csv(batch / "observations.csv", index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")
    financials.sort_values(["ticker", "statement", "period_end", "canonical_concept"], kind="stable").to_csv(batch / "financial_facts.csv", index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")
    actions.sort_values(["ticker", "date", "action_type"], kind="stable").to_csv(batch / "corporate_actions.csv", index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")
    coverage = yahoo_coverage(observations)
    atomic_write_json(batch / "coverage.json", coverage)
    artifacts = {name: sha256_file(batch / name) for name in ("observations.csv", "financial_facts.csv", "corporate_actions.csv", "coverage.json")}
    manifest = {
        "schema_version": YAHOO_OBSERVATION_VERSION, "batch_id": args.batch_id,
        "provider": "Yahoo Finance via yfinance", "provider_version": yf.__version__,
        "verification": "SECONDARY_REFERENCE", "market_fingerprint": bundle.fingerprint,
        "requested_count": len(observations), "coverage": coverage, "artifacts": artifacts,
        "identity_rule": "exact provider symbol + expected exchange + EQUITY quote type",
        "screener_dependency": False,
        "seed_batch": args.seed_batch,
        "backlog_drain": args.drain_backlog,
        "provider_budget": args.provider_budget if args.drain_backlog else None,
        "backlog_counts": ({str(k): int(v) for k, v in backlog["completion_status"].value_counts().items()}
                           if backlog is not None else None),
    }
    manifest["fingerprint"] = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    atomic_write_json(batch / "manifest.json", manifest)
    load_yahoo_secondary_bundle(batch)
    pointer = {"accepted_batch": batch.relative_to(args.output_root).as_posix(), "fingerprint": manifest["fingerprint"], "accepted_at": datetime.now(timezone.utc).isoformat()}
    atomic_write_json(args.output_root / "accepted_state.json", pointer)
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
