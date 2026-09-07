from __future__ import annotations

import argparse
import csv
from datetime import date
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys


HOME = Path.home()
PROJECT = HOME / "Downloads" / "stock-ranking-platform"

DEFAULT_LIVE = PROJECT / "data" / "live_market" / "candidate_bse_20260907" / "live_market.csv"
DEFAULT_EXISTING_CACHE = PROJECT / "data" / "live_market" / "history_cache"
DEFAULT_OUTPUT_CACHE = PROJECT / "data" / "live_market" / "history_cache_candidate_bse_20260907"

READINESS_ROOT = HOME / "Downloads" / "BSE_Adjustment_Readiness"
DEFAULT_RAW_ROOT = READINESS_ROOT / "raw_history"
DEFAULT_ACTIONS = READINESS_ROOT / "action_readiness.csv"
DEFAULT_PER_CODE = READINESS_ROOT / "per_code_readiness.csv"

TRADE_DATE = "2026-09-07"

TERMINAL_READY = "ADJUSTMENT_READY"
ACTION_READY = "READY"


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


def finite_positive(value: object, label: str) -> float:
    try:
        x = float(value)
    except Exception as exc:
        raise ValueError(f"{label} is not numeric: {value!r}") from exc
    if not math.isfinite(x) or x <= 0:
        raise ValueError(f"{label} must be finite and positive: {value!r}")
    return x


def load_candidate_mapping(path: Path) -> dict[str, dict]:
    rows = read_csv(path)
    mapping = {}
    for r in rows:
        if str(r.get("primary_exchange", "")).strip().upper() != "BSE":
            continue
        code = norm_code(r.get("exchange_security_id"))
        ticker = str(r.get("ticker", "")).strip()
        if not re.fullmatch(r"\d{6}", code):
            continue
        if ticker.upper() != f"BSE-{code}":
            raise ValueError(
                f"candidate BSE identity mismatch for {code}: ticker={ticker!r}"
            )
        latest = finite_positive(r.get("latest_price"), f"{ticker}.latest_price")
        mapping[code] = {
            "ticker": ticker,
            "isin": str(r.get("isin", "")).strip(),
            "company": str(r.get("company", "")).strip(),
            "latest_price": latest,
            "trade_date": str(r.get("trade_date", "")).strip(),
        }
    return mapping


def clone_existing_cache(source: Path, destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    if not source.is_dir():
        return copied
    for src in source.glob("*.csv"):
        dst = destination / src.name
        if dst.exists():
            continue
        # Copy rather than symlink/hardlink so the candidate cache is fully isolated.
        shutil.copy2(src, dst)
        copied += 1
    return copied


def load_raw_history(path: Path, expected_code: str) -> list[dict]:
    rows = read_csv(path)
    out = []
    seen = set()
    for r in rows:
        d = str(r.get("date", "")).strip()
        try:
            date.fromisoformat(d)
        except ValueError as exc:
            raise ValueError(f"{path.name}: bad date {d!r}") from exc
        if d in seen:
            raise ValueError(f"{path.name}: duplicate date {d}")
        seen.add(d)

        code = norm_code(r.get("bse_code"))
        if code != expected_code:
            raise ValueError(f"{path.name}: expected code {expected_code}, got {code}")

        raw_close = finite_positive(r.get("close"), f"{path.name}:{d}:close")
        out.append({
            "date": d,
            "raw_close": raw_close,
            "adjusted_close": raw_close,
        })

    out.sort(key=lambda r: r["date"])
    if not out:
        raise ValueError(f"{path.name}: no raw history rows")
    return out


def action_factor_rows(actions_path: Path) -> dict[str, list[dict]]:
    actions = read_csv(actions_path)
    by_code: dict[str, list[dict]] = {}

    for r in actions:
        code = norm_code(r.get("bse_code"))
        if str(r.get("adjustment_readiness", "")).strip() != ACTION_READY:
            continue
        ex = str(r.get("ex_date_iso", "")).strip()
        try:
            date.fromisoformat(ex)
        except ValueError as exc:
            raise ValueError(f"READY action {code} has invalid ex-date {ex!r}") from exc

        factor = finite_positive(
            r.get("candidate_backward_factor"),
            f"{code} {ex} candidate_backward_factor",
        )
        if factor > 1.5:
            raise ValueError(f"{code} {ex}: implausible backward factor {factor}")

        by_code.setdefault(code, []).append({
            "ex_date": ex,
            "factor": factor,
            "event_type": str(r.get("event_type", "")).strip(),
            "purpose": str(r.get("purpose", "")).strip(),
            "method": str(r.get("candidate_method", "")).strip(),
        })

    # Codes marked ADJUSTMENT_READY should not contain multiple READY actions on
    # the same ex-date, because the readiness auditor quarantines those groups.
    for code, rows in by_code.items():
        seen = set()
        for r in rows:
            if r["ex_date"] in seen:
                raise ValueError(
                    f"{code}: multiple READY factors share ex-date {r['ex_date']}"
                )
            seen.add(r["ex_date"])
        rows.sort(key=lambda r: r["ex_date"])

    return by_code


def apply_backward_adjustments(
    history: list[dict],
    actions: list[dict],
) -> list[dict]:
    out = [dict(r) for r in history]

    # Current-basis adjusted series:
    # every action's factor applies only to observations strictly before its ex-date.
    for action in sorted(actions, key=lambda r: r["ex_date"]):
        ex = action["ex_date"]
        factor = float(action["factor"])
        for r in out:
            if r["date"] < ex:
                r["adjusted_close"] *= factor

    for r in out:
        if not math.isfinite(float(r["adjusted_close"])) or float(r["adjusted_close"]) <= 0:
            raise ValueError("adjusted_close became invalid")
    return out


def upsert_current_observation(
    history: list[dict],
    *,
    trade_date: str,
    latest_price: float,
) -> list[dict]:
    by_date = {r["date"]: dict(r) for r in history}
    by_date[trade_date] = {
        "date": trade_date,
        "raw_close": latest_price,
        "adjusted_close": latest_price,
    }
    return [by_date[d] for d in sorted(by_date)]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Build an isolated candidate history cache for exact current BSE identities. "
            "Only ADJUSTMENT_READY codes are promoted; review-blocked codes remain quarantined."
        )
    )
    p.add_argument("--candidate-live-market", type=Path, default=DEFAULT_LIVE)
    p.add_argument("--existing-cache", type=Path, default=DEFAULT_EXISTING_CACHE)
    p.add_argument("--output-cache", type=Path, default=DEFAULT_OUTPUT_CACHE)
    p.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    p.add_argument("--actions", type=Path, default=DEFAULT_ACTIONS)
    p.add_argument("--per-code", type=Path, default=DEFAULT_PER_CODE)
    p.add_argument("--trade-date", default=TRADE_DATE)
    args = p.parse_args(argv)

    try:
        date.fromisoformat(args.trade_date)

        candidate = load_candidate_mapping(args.candidate_live_market.resolve())
        per_code_rows = read_csv(args.per_code.resolve())
        actions = action_factor_rows(args.actions.resolve())

        policy_by_code = {
            norm_code(r["bse_code"]): str(r.get("promotion_policy", "")).strip()
            for r in per_code_rows
        }

        all_evidence_codes = set(policy_by_code)
        current_codes = set(candidate)
        current_evidence_codes = sorted(all_evidence_codes & current_codes)
        absent_current = sorted(all_evidence_codes - current_codes)

        safe_codes = sorted(
            c for c in current_evidence_codes
            if policy_by_code.get(c) == TERMINAL_READY
        )
        blocked_codes = sorted(set(current_evidence_codes) - set(safe_codes))

        output_cache = args.output_cache.resolve()
        seeded = clone_existing_cache(args.existing_cache.resolve(), output_cache)

        promotion_rows = []
        total_raw_rows = 0
        total_adjusted_rows = 0
        total_actions_applied = 0

        for code in safe_codes:
            ticker = candidate[code]["ticker"]
            raw_path = args.raw_root.resolve() / f"BSE-{code}.csv"
            history = load_raw_history(raw_path, code)
            total_raw_rows += len(history)

            code_actions = actions.get(code, [])
            adjusted = apply_backward_adjustments(history, code_actions)
            total_actions_applied += len(code_actions)

            adjusted = upsert_current_observation(
                adjusted,
                trade_date=args.trade_date,
                latest_price=float(candidate[code]["latest_price"]),
            )
            total_adjusted_rows += len(adjusted)

            terminal = adjusted[-1]
            if terminal["date"] != args.trade_date:
                raise ValueError(f"{code}: candidate history does not end on trade date")
            if abs(float(terminal["adjusted_close"]) - float(candidate[code]["latest_price"])) > 1e-9:
                raise ValueError(f"{code}: terminal adjusted close != official current close")

            target = output_cache / f"{ticker}.csv"
            write_csv_atomic(
                target,
                adjusted,
                ["date", "raw_close", "adjusted_close"],
            )

            promotion_rows.append({
                "bse_code": code,
                "ticker": ticker,
                "isin": candidate[code]["isin"],
                "company": candidate[code]["company"],
                "raw_rows_before_current": len(history),
                "candidate_rows": len(adjusted),
                "actions_applied": len(code_actions),
                "first_date": adjusted[0]["date"],
                "last_date": adjusted[-1]["date"],
                "official_current_close": candidate[code]["latest_price"],
                "status": "PROMOTED_TO_CANDIDATE_CACHE",
            })

        root = output_cache.parent / "bse_candidate_history_integration_20260907"
        root.mkdir(parents=True, exist_ok=True)

        write_csv_atomic(
            root / "promoted_codes.csv",
            promotion_rows,
            list(promotion_rows[0].keys()) if promotion_rows else [
                "bse_code","ticker","isin","company","raw_rows_before_current",
                "candidate_rows","actions_applied","first_date","last_date",
                "official_current_close","status",
            ],
        )

        blocked_rows = []
        per_code_map = {norm_code(r["bse_code"]): r for r in per_code_rows}
        for code in blocked_codes:
            r = per_code_map[code]
            blocked_rows.append({
                "bse_code": code,
                "ticker": candidate[code]["ticker"],
                "promotion_policy": policy_by_code[code],
                "promotion_reason": r.get("promotion_reason", ""),
                "structured_actions": r.get("structured_actions", ""),
                "unresolved_price_actions": r.get("unresolved_price_actions", ""),
                "identity_candidates": r.get("identity_candidates", ""),
            })
        write_csv_atomic(
            root / "blocked_current_codes.csv",
            blocked_rows,
            list(blocked_rows[0].keys()) if blocked_rows else [
                "bse_code","ticker","promotion_policy","promotion_reason",
                "structured_actions","unresolved_price_actions","identity_candidates",
            ],
        )

        absent_rows = [
            {
                "bse_code": code,
                "promotion_policy": policy_by_code.get(code, ""),
                "status": "ABSENT_FROM_2026_09_07_BSE_BHAVCOPY",
            }
            for code in absent_current
        ]
        write_csv_atomic(
            root / "absent_current_codes.csv",
            absent_rows,
            ["bse_code","promotion_policy","status"],
        )

        summary = {
            "evidence_codes_total": len(all_evidence_codes),
            "current_candidate_exact_bse_codes": len(current_codes),
            "evidence_codes_present_currently": len(current_evidence_codes),
            "evidence_codes_absent_currently": len(absent_current),
            "safe_current_codes_promoted": len(safe_codes),
            "blocked_current_codes": len(blocked_codes),
            "existing_cache_files_seeded": seeded,
            "raw_rows_consumed": total_raw_rows,
            "candidate_adjusted_rows_written": total_adjusted_rows,
            "corporate_action_factors_applied": total_actions_applied,
            "output_cache": str(output_cache),
            "trade_date": args.trade_date,
            "policy": {
                "source_raw_prices_preserved": True,
                "only_adjustment_ready_codes_promoted": True,
                "review_blocked_codes_written_to_cache": False,
                "absent_current_codes_written_to_cache": False,
                "current_close_appended_from_official_candidate_snapshot": True,
                "adjusted_close_semantics": (
                    "current-basis backward-adjusted series; official structured "
                    "split/bonus/dividend/rights factors applied to pre-ex-date rows"
                ),
            },
        }

        (root / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        print(json.dumps(summary, indent=2, sort_keys=True))
        print(f"Candidate cache: {output_cache}")
        print(f"Promotion report: {root / 'promoted_codes.csv'}")
        print(f"Blocked current codes: {root / 'blocked_current_codes.csv'}")
        print(f"Absent current codes: {root / 'absent_current_codes.csv'}")
        print("BSE CANDIDATE HISTORY CACHE BUILD: PASS")
        print("Accepted current live_market/history_cache were NOT modified.")
        return 0

    except Exception as exc:
        print(
            f"BSE CANDIDATE HISTORY CACHE BUILD FAILED: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
