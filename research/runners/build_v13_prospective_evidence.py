"""Freeze research-only official endpoint prices and action extensions for V13."""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import ast
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
import pandas as pd

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_research.personalized_official_actions import load_official_action_ledger

OUT = ROOT / "experiments/personalized-v13-20261002/prospective-2025-09-30"
PRICE = OUT / "prices"
ACTION = OUT / "official_actions"
OLD_SPLIT = ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2"
OLD_LEDGER = ROOT / "experiments/personalized-official-action-freeze/build-06/normalized_official_action_ledger.csv.gz"
OLD_RECOVERY = ROOT / "external_research_pack/ownership_history_20260925"
CACHE = ROOT / "data/live_market/history_cache"
NSE_RAW = ROOT / "data/company_facts/providers/official_exchange/automatic-20261002T143202Z/raw/nse_actions.json"
DATES = ("2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24",
         "2026-09-25", "2026-09-28", "2026-09-29", "2026-09-30")


def sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def official_prices(facts: pd.DataFrame) -> pd.DataFrame:
    locator = facts[["isin", "ticker", "primary_exchange"]].rename(columns={"primary_exchange": "exchange"})
    pieces = []
    for day in DATES:
        compact = day.replace("-", "")
        for exchange in ("NSE", "BSE"):
            if exchange == "NSE":
                path = OUT / "official_prices" / f"BhavCopy_NSE_CM_0_0_0_{compact}_F_0000.csv.zip"
                with ZipFile(BytesIO(path.read_bytes())) as archive:
                    frame = pd.read_csv(BytesIO(archive.read(archive.namelist()[0])), low_memory=False)
            else:
                path = OUT / "official_prices" / f"BhavCopy_BSE_CM_0_0_0_{compact}_F_0000.csv"
                frame = pd.read_csv(path, low_memory=False)
            if set(frame.TradDt.astype(str)) != {day}:
                raise ValueError("official date mismatch")
            frame["exchange"] = exchange
            frame = frame.merge(locator, left_on=["ISIN", "exchange"],
                                right_on=["isin", "exchange"], how="inner", validate="many_to_one")
            frame = frame.sort_values("SctySrs", key=lambda s: s.ne("EQ"), kind="stable")
            frame = frame.drop_duplicates("isin", keep="first")
            frame["close"] = pd.to_numeric(frame.ClsPric, errors="coerce")
            frame = frame.loc[frame.close.gt(0), ["isin", "ticker", "exchange", "close"]]
            frame["date"] = day
            pieces.append(frame)
    result = pd.concat(pieces, ignore_index=True)
    if result.duplicated(["isin", "date"]).any():
        raise ValueError("duplicate official price")
    return result


def action_extension(facts: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    bse_audit = pd.read_csv(ACTION / "bse_acquisition_audit.csv", dtype={"bse_code": str})
    if len(bse_audit) != facts.primary_exchange.eq("BSE").sum():
        raise ValueError("BSE action cohort mismatch")
    failed = bse_audit.loc[bse_audit.status.ne("SUCCESS"), "bse_code"].tolist()
    bse = pd.read_csv(ACTION / "bse_recent_events.csv", dtype={"bse_code": str})
    source = []
    for row in bse.itertuples(index=False):
        response = ACTION / "raw" / f"{row.bse_code}.json"
        if sha(response) != row.response_sha256:
            raise ValueError("BSE event response hash mismatch")
        source.append({"exchange": "BSE", "isin": None, "ticker_or_code": row.bse_code,
                       "event_date": row.ex_date, "record_date": row.record_date,
                       "source_text": row.purpose, "event_type": row.event_type,
                       "ratio_numerator": None, "ratio_denominator": None,
                       "total_share_multiplier": None,
                       "parse_status": "PARSED" if row.event_type in ("SPLIT", "BONUS") else "NON_AUTOMATIC_OR_TERMS_SEPARATE",
                       "event_date_parsed": pd.to_datetime(row.ex_date, dayfirst=True).date().isoformat()})
    nse = json.loads(NSE_RAW.read_text())
    for item in nse:
        day = pd.to_datetime(item.get("exDate"), errors="coerce", dayfirst=True)
        if pd.isna(day) or not (pd.Timestamp("2026-09-19") <= day <= pd.Timestamp("2026-09-30")):
            continue
        subject = str(item.get("subject", ""))
        lower = subject.lower()
        kind = ("BONUS" if "bonus" in lower else "SPLIT" if "split" in lower or "sub-div" in lower
                else "RIGHTS" if "right" in lower else "DEMERGER" if "demerger" in lower
                else "SCHEME_OR_MERGER" if "merger" in lower or "scheme" in lower else None)
        if kind is None:
            continue
        source.append({"exchange": "NSE", "isin": item.get("isin"),
                       "ticker_or_code": item.get("symbol"), "event_date": item.get("exDate"),
                       "record_date": item.get("recDate"), "source_text": subject,
                       "event_type": kind, "ratio_numerator": None,
                       "ratio_denominator": None, "total_share_multiplier": None,
                       "parse_status": "PARSED" if kind in ("SPLIT", "BONUS") else "NON_AUTOMATIC_OR_TERMS_SEPARATE",
                       "event_date_parsed": day.date().isoformat()})
    source_frame = pd.DataFrame(source)
    source_frame.to_csv(ACTION / "recent_source_events.csv", index=False)
    mapped, mapping = load_official_action_ledger(facts, ACTION / "recent_source_events.csv", as_of_date="2026-09-30")
    old = pd.read_csv(OLD_LEDGER, low_memory=False)
    if old.event_date.gt("2026-09-18").any():
        raise ValueError("frozen ledger boundary drift")
    new = mapped.loc[mapped.event_date.gt("2026-09-18")].copy()
    new["economic_policy"] = "OFFICIAL_MULTIPLIER_OR_EXISTING_BLOCK"
    for name in ("evidence_url", "entitlement_terms", "issue_price_inr", "policy_assumption"):
        new[name] = None
    overlap = old.merge(new, on=["isin", "event_date", "event_type"], how="inner")
    if not overlap.empty:
        raise ValueError("new official event collides with frozen ledger")
    combined = pd.concat([old, new[old.columns]], ignore_index=True)
    combined.to_csv(ACTION / "normalized_official_action_ledger_through_20260930.csv.gz",
                    index=False, compression={"method": "gzip", "mtime": 0})
    return combined, {"old_rows": len(old), "new_rows": len(new), "source_event_rows": len(source_frame),
                      "bse_success": int(bse_audit.status.eq("SUCCESS").sum()),
                      "bse_failed_codes": failed, "mapping": mapping,
                      "frozen_ledger_sha256": sha(OLD_LEDGER), "nse_raw_sha256": sha(NSE_RAW)}


def split_extension() -> tuple[pd.DataFrame, dict]:
    old = pd.read_csv(OLD_SPLIT / "split_ledger.csv")
    audit = pd.read_csv(PRICE / "acquisition_audit.csv")
    rows = []
    for item in audit.loc[audit.status.eq("SUCCESS")].itertuples(index=False):
        for event in ast.literal_eval(item.new_split_events):
            raw = PRICE / "raw" / f"{item.isin}.json"
            if sha(raw) != item.response_sha256:
                raise ValueError("provider split response hash mismatch")
            rows.append({"isin": item.isin, "ticker": item.ticker,
                         "provider_symbol": item.provider_symbol, **event,
                         "source_url": item.source_url,
                         "response_sha256": item.response_sha256})
    new = pd.DataFrame(rows, columns=old.columns)
    if len(new) != 2:
        raise ValueError("unexpected post-cutoff provider split count")
    combined = pd.concat([old, new], ignore_index=True)
    if combined.duplicated(["isin", "event_date", "split_ratio"]).any():
        raise ValueError("duplicate provider split")
    root = OUT / "provider_split_ledger"
    root.mkdir(parents=True, exist_ok=True)
    combined.to_csv(root / "split_ledger.csv", index=False)
    return new, {"prior_rows": len(old), "new_rows": len(new),
                 "old_ledger_sha256": sha(OLD_SPLIT / "split_ledger.csv")}


def execution_overlay(facts: pd.DataFrame, prices: pd.DataFrame,
                      splits: pd.DataFrame) -> dict:
    split_groups = {name: group.sort_values("event_date") for name, group in splits.groupby("isin")}
    price_groups = {name: group.sort_values("date") for name, group in prices.groupby("isin")}
    root = OUT / "official_execution_overlay"
    root.mkdir(parents=True, exist_ok=True)
    rows, no_base = 0, []
    for item in facts[["isin", "ticker"]].itertuples(index=False):
        base = OLD_RECOVERY / f"{item.ticker}.csv"
        if not base.exists():
            base = CACHE / f"{item.ticker}.csv"
        if not base.exists():
            no_base.append(item.isin)
            continue
        old = pd.read_csv(base, usecols=["date", "raw_close", "adjusted_close"])
        old = old.loc[old.date.le("2026-09-18")].copy()
        if old.empty or old.date.duplicated().any():
            no_base.append(item.isin)
            continue
        recent_splits = split_groups.get(item.isin)
        if recent_splits is not None:
            for split in recent_splits.itertuples(index=False):
                before = old.date.lt(split.event_date)
                old.loc[before, ["raw_close", "adjusted_close"]] /= split.split_ratio
        official = price_groups.get(item.isin)
        if official is not None:
            extension = official[["date", "close"]].copy()
            if recent_splits is not None:
                for split in recent_splits.itertuples(index=False):
                    extension.loc[extension.date.lt(split.event_date), "close"] /= split.split_ratio
            extension = extension.rename(columns={"close": "raw_close"})
            extension["adjusted_close"] = extension.raw_close
            old = pd.concat([old, extension], ignore_index=True)
            rows += len(extension)
        old = old.sort_values("date", kind="stable")
        if old.date.duplicated().any() or old.raw_close.le(0).any():
            raise ValueError(f"invalid execution overlay: {item.ticker}")
        old.to_csv(root / f"{item.ticker}.csv", index=False, float_format="%.17g")
    return {"official_price_rows_appended": rows, "base_missing_identities": len(no_base),
            "overlay_files": len(list(root.glob("*.csv"))),
            "overlay_source_priority": "validated recovered history, then frozen cache; official UDiFF close for new dates"}


def main() -> None:
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    prices = official_prices(facts)
    prices.to_csv(OUT / "official_prices_mapped.csv.gz", index=False,
                  compression={"method": "gzip", "mtime": 0})
    _, action = action_extension(facts)
    split, provider = split_extension()
    overlay = execution_overlay(facts, prices, split)
    summary = {"schema": "v13_prospective_execution_evidence_v1",
               "decision_date": "2025-09-30", "endpoint": "2026-09-30",
               "official_price_rows": len(prices), "action": action, "provider": provider,
               "overlay": overlay, "no_outcome_columns_loaded": True,
               "selection_lock_sha256": sha(ROOT / "experiments/personalized-v13-20261002/locked_selection.json"),
               "pre_reveal_record_sha256": sha(OUT / "pre_reveal_record.json"),
               "accepted_data_mutated": False}
    (OUT / "execution_evidence_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"official_price_rows": len(prices), "new_actions": action["new_rows"],
                      "new_provider_splits": provider["new_rows"], **overlay}), flush=True)


if __name__ == "__main__":
    main()
