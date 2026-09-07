from __future__ import annotations

import argparse
import csv
from datetime import date
import json
import math
import os
from pathlib import Path
import shutil
import sys

HOME = Path.home()
PROJECT = HOME / "Downloads" / "stock-ranking-platform"

DEFAULT_BASE_CACHE = PROJECT / "data/live_market/history_cache_candidate_bse_20260907"
DEFAULT_OUTPUT_CACHE = PROJECT / "data/live_market/history_cache_candidate_bse_price_return_20260907"
DEFAULT_LIVE = PROJECT / "data/live_market/candidate_bse_20260907_refreshed/live_market.csv"

INTEGRATION_ROOT = PROJECT / "data/live_market/bse_candidate_history_integration_20260907"
DEFAULT_PROMOTED = INTEGRATION_ROOT / "promoted_codes.csv"
DEFAULT_BLOCKED = INTEGRATION_ROOT / "blocked_current_codes.csv"
DEFAULT_ABSENT = INTEGRATION_ROOT / "absent_current_codes.csv"

READINESS_ROOT = HOME / "Downloads/BSE_Adjustment_Readiness"
DEFAULT_RAW_ROOT = READINESS_ROOT / "raw_history"
DEFAULT_ACTIONS = READINESS_ROOT / "action_readiness.csv"

TRADE_DATE = "2026-09-07"
CAPITAL_ACTIONS = {"SPLIT", "BONUS"}


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_atomic(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def norm_code(v: object) -> str:
    s = str(v or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(6) if s.isdigit() else s


def pos_float(v: object, label: str) -> float:
    try:
        x = float(v)
    except Exception as exc:
        raise ValueError(f"{label} is not numeric: {v!r}") from exc
    if not math.isfinite(x) or x <= 0:
        raise ValueError(f"{label} must be finite and positive: {v!r}")
    return x


def clone_cache(src: Path, dst: Path) -> int:
    if not src.is_dir():
        raise FileNotFoundError(src)
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    for p in src.glob("*.csv"):
        shutil.copy2(p, dst / p.name)
        copied += 1
    return copied


def load_live(path: Path) -> dict[str, dict]:
    rows = read_csv(path)
    out = {}
    for r in rows:
        if str(r.get("primary_exchange", "")).strip().upper() != "BSE":
            continue
        code = norm_code(r.get("exchange_security_id"))
        if not (len(code) == 6 and code.isdigit()):
            continue
        out[code] = {
            "ticker": str(r.get("ticker", "")).strip(),
            "latest_price": pos_float(r.get("latest_price"), f"{code}.latest_price"),
            "isin": str(r.get("isin", "")).strip(),
            "company": str(r.get("company", "")).strip(),
        }
    return out


def load_raw_history(path: Path, code: str) -> list[dict]:
    rows = read_csv(path)
    out = []
    seen = set()
    for r in rows:
        d = str(r.get("date", "")).strip()
        date.fromisoformat(d)
        if d in seen:
            raise ValueError(f"{path.name}: duplicate date {d}")
        seen.add(d)
        if norm_code(r.get("bse_code")) != code:
            raise ValueError(f"{path.name}: wrong BSE code")
        close = pos_float(r.get("close"), f"{path.name}:{d}:close")
        out.append({"date": d, "raw_close": close, "adjusted_close": close})
    out.sort(key=lambda x: x["date"])
    if not out:
        raise ValueError(f"{path.name}: empty history")
    return out


def load_actions(path: Path) -> tuple[dict[str, list[dict]], dict[str, int]]:
    by_code: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}
    for r in read_csv(path):
        if str(r.get("adjustment_readiness", "")).strip() != "READY":
            continue
        code = norm_code(r.get("bse_code"))
        et = str(r.get("event_type", "")).strip().upper()
        counts[et] = counts.get(et, 0) + 1
        factor = pos_float(
            r.get("candidate_backward_factor"),
            f"{code} {et} candidate_backward_factor",
        )
        ex = str(r.get("ex_date_iso", "")).strip()
        date.fromisoformat(ex)
        by_code.setdefault(code, []).append({
            "event_type": et,
            "ex_date": ex,
            "factor": factor,
        })
    for rows in by_code.values():
        rows.sort(key=lambda x: x["ex_date"])
    return by_code, counts


def apply_price_return_actions(history: list[dict], actions: list[dict]) -> tuple[list[dict], int, int]:
    out = [dict(r) for r in history]
    applied = 0
    ignored_dividends = 0

    for a in actions:
        et = a["event_type"]
        if et == "DIVIDEND":
            ignored_dividends += 1
            continue
        if et not in CAPITAL_ACTIONS:
            # Conservative price-return policy: no automatic rights/other adjustment here.
            continue
        factor = float(a["factor"])
        ex = a["ex_date"]
        for r in out:
            if r["date"] < ex:
                r["adjusted_close"] *= factor
        applied += 1

    return out, applied, ignored_dividends


def upsert_current(history: list[dict], trade_date: str, close: float) -> list[dict]:
    by_date = {r["date"]: dict(r) for r in history}
    by_date[trade_date] = {
        "date": trade_date,
        "raw_close": close,
        "adjusted_close": close,
    }
    return [by_date[d] for d in sorted(by_date)]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Rebuild the isolated BSE candidate history cache under explicit "
            "PRICE_RETURN semantics: split/bonus adjust backward; dividends do not."
        )
    )
    p.add_argument("--base-cache", type=Path, default=DEFAULT_BASE_CACHE)
    p.add_argument("--output-cache", type=Path, default=DEFAULT_OUTPUT_CACHE)
    p.add_argument("--live-market", type=Path, default=DEFAULT_LIVE)
    p.add_argument("--promoted", type=Path, default=DEFAULT_PROMOTED)
    p.add_argument("--blocked", type=Path, default=DEFAULT_BLOCKED)
    p.add_argument("--absent", type=Path, default=DEFAULT_ABSENT)
    p.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    p.add_argument("--actions", type=Path, default=DEFAULT_ACTIONS)
    p.add_argument("--trade-date", default=TRADE_DATE)
    args = p.parse_args(argv)

    try:
        date.fromisoformat(args.trade_date)
        live = load_live(args.live_market.resolve())
        promoted_rows = read_csv(args.promoted.resolve())
        promoted_codes = [norm_code(r["bse_code"]) for r in promoted_rows]
        blocked_codes = {norm_code(r["bse_code"]) for r in read_csv(args.blocked.resolve())}
        absent_codes = {norm_code(r["bse_code"]) for r in read_csv(args.absent.resolve())}
        actions_by_code, ready_counts = load_actions(args.actions.resolve())

        dst = args.output_cache.resolve()
        copied = clone_cache(args.base_cache.resolve(), dst)

        # The Yahoo refresh may have recreated quarantined/absent BSE cache files.
        # Remove them deterministically in the corrected candidate cache.
        removed_quarantine = []
        for code in sorted(blocked_codes | absent_codes):
            pth = dst / f"BSE-{code}.csv"
            if pth.is_file():
                pth.unlink()
                removed_quarantine.append(code)

        report = []
        total_capital_actions = 0
        total_dividends_ignored = 0
        total_rows = 0

        for code in promoted_codes:
            if code not in live:
                raise ValueError(f"{code}: promoted code missing from current BSE live market")
            ticker = live[code]["ticker"]
            if ticker != f"BSE-{code}":
                raise ValueError(f"{code}: unexpected ticker {ticker}")

            history = load_raw_history(args.raw_root.resolve() / f"BSE-{code}.csv", code)
            adjusted, applied, dividends_ignored = apply_price_return_actions(
                history,
                actions_by_code.get(code, []),
            )
            adjusted = upsert_current(
                adjusted,
                args.trade_date,
                live[code]["latest_price"],
            )

            terminal = adjusted[-1]
            if terminal["date"] != args.trade_date:
                raise ValueError(f"{code}: bad terminal date")
            if abs(float(terminal["adjusted_close"]) - live[code]["latest_price"]) > 1e-9:
                raise ValueError(f"{code}: terminal adjusted close mismatch")

            write_csv_atomic(
                dst / f"{ticker}.csv",
                adjusted,
                ["date", "raw_close", "adjusted_close"],
            )

            total_capital_actions += applied
            total_dividends_ignored += dividends_ignored
            total_rows += len(adjusted)
            report.append({
                "bse_code": code,
                "ticker": ticker,
                "rows": len(adjusted),
                "capital_actions_applied": applied,
                "dividends_ignored_for_price_return": dividends_ignored,
                "first_date": adjusted[0]["date"],
                "last_date": adjusted[-1]["date"],
                "status": "PROMOTED_TO_PRICE_RETURN_CANDIDATE",
            })

        leaks = []
        for code in sorted(blocked_codes | absent_codes):
            if (dst / f"BSE-{code}.csv").is_file():
                leaks.append(code)

        if leaks:
            raise ValueError(f"quarantine leak after rebuild: {leaks[:10]}")

        report_root = PROJECT / "data/live_market/bse_price_return_rebuild_20260907"
        report_root.mkdir(parents=True, exist_ok=True)
        write_csv_atomic(
            report_root / "promoted_codes.csv",
            report,
            list(report[0].keys()) if report else [
                "bse_code","ticker","rows","capital_actions_applied",
                "dividends_ignored_for_price_return","first_date","last_date","status"
            ],
        )

        summary = {
            "base_cache_files_copied": copied,
            "promoted_codes_rebuilt": len(promoted_codes),
            "blocked_codes": len(blocked_codes),
            "absent_current_codes": len(absent_codes),
            "quarantine_files_removed_from_refreshed_base": len(removed_quarantine),
            "quarantine_leaks_after_rebuild": len(leaks),
            "candidate_rows_written_for_promoted_codes": total_rows,
            "split_bonus_factors_applied": total_capital_actions,
            "dividend_factors_intentionally_not_applied": total_dividends_ignored,
            "ready_action_rows_global_by_type": dict(sorted(ready_counts.items())),
            "output_cache": str(dst),
            "trade_date": args.trade_date,
            "policy": {
                "ranking_return_basis": "PRICE_RETURN",
                "raw_exchange_prices_preserved": True,
                "split_bonus_backward_adjustment": True,
                "dividend_adjustment": False,
                "rights_adjustment": False,
                "merger_history_bridge": False,
                "review_blocked_and_absent_codes_quarantined": True,
            },
        }

        (report_root / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        print(json.dumps(summary, indent=2, sort_keys=True))
        print(f"Corrected candidate cache: {dst}")
        print(f"Report: {report_root / 'summary.json'}")
        print("BSE PRICE-RETURN CANDIDATE REBUILD: PASS")
        print("Accepted market/history/company-fact state was NOT modified.")
        return 0

    except Exception as exc:
        print(
            f"BSE PRICE-RETURN CANDIDATE REBUILD FAILED: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
