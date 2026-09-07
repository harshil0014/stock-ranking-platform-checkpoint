from __future__ import annotations

import argparse
import csv
from datetime import date
import json
import math
from pathlib import Path
import sys


HOME = Path.home()
PROJECT = HOME / "Downloads" / "stock-ranking-platform"

DEFAULT_CACHE = PROJECT / "data" / "live_market" / "history_cache_candidate_bse_20260907"
DEFAULT_PROMOTED = PROJECT / "data" / "live_market" / "bse_candidate_history_integration_20260907" / "promoted_codes.csv"
DEFAULT_BLOCKED = PROJECT / "data" / "live_market" / "bse_candidate_history_integration_20260907" / "blocked_current_codes.csv"
DEFAULT_ABSENT = PROJECT / "data" / "live_market" / "bse_candidate_history_integration_20260907" / "absent_current_codes.csv"
DEFAULT_LIVE = PROJECT / "data" / "live_market" / "candidate_bse_20260907" / "live_market.csv"

TRADE_DATE = "2026-09-07"


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def norm_code(v: object) -> str:
    s = str(v or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(6) if s.isdigit() else s


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Audit that only safe current BSE histories entered the isolated candidate cache."
    )
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    p.add_argument("--promoted", type=Path, default=DEFAULT_PROMOTED)
    p.add_argument("--blocked", type=Path, default=DEFAULT_BLOCKED)
    p.add_argument("--absent", type=Path, default=DEFAULT_ABSENT)
    p.add_argument("--live-market", type=Path, default=DEFAULT_LIVE)
    p.add_argument("--trade-date", default=TRADE_DATE)
    args = p.parse_args(argv)

    try:
        cache = args.cache.resolve()
        promoted = read_csv(args.promoted.resolve())
        blocked = read_csv(args.blocked.resolve())
        absent = read_csv(args.absent.resolve())
        live = read_csv(args.live_market.resolve())

        live_by_code = {}
        for r in live:
            if str(r.get("primary_exchange", "")).strip().upper() != "BSE":
                continue
            code = norm_code(r.get("exchange_security_id"))
            if len(code) == 6 and code.isdigit():
                live_by_code[code] = r

        errors = []
        warnings = []

        promoted_codes = {norm_code(r["bse_code"]) for r in promoted}
        blocked_codes = {norm_code(r["bse_code"]) for r in blocked}
        absent_codes = {norm_code(r["bse_code"]) for r in absent}

        if promoted_codes & blocked_codes:
            errors.append("Promoted and blocked code sets overlap.")
        if promoted_codes & absent_codes:
            errors.append("Promoted and absent-current code sets overlap.")
        if blocked_codes & absent_codes:
            errors.append("Blocked-current and absent-current code sets overlap.")

        promoted_bad = []
        for r in promoted:
            code = norm_code(r["bse_code"])
            ticker = str(r["ticker"]).strip()
            path = cache / f"{ticker}.csv"

            if not path.is_file():
                promoted_bad.append({"code": code, "reason": "CACHE_FILE_MISSING"})
                continue

            rows = read_csv(path)
            if not rows:
                promoted_bad.append({"code": code, "reason": "CACHE_EMPTY"})
                continue

            dates = [str(x.get("date", "")).strip() for x in rows]
            if len(dates) != len(set(dates)):
                promoted_bad.append({"code": code, "reason": "DUPLICATE_DATE"})
                continue
            if dates != sorted(dates):
                promoted_bad.append({"code": code, "reason": "UNSORTED_DATES"})
                continue
            if dates[-1] != args.trade_date:
                promoted_bad.append({
                    "code": code,
                    "reason": f"TERMINAL_DATE_{dates[-1]}",
                })
                continue

            try:
                terminal_raw = float(rows[-1]["raw_close"])
                terminal_adj = float(rows[-1]["adjusted_close"])
            except Exception:
                promoted_bad.append({"code": code, "reason": "BAD_TERMINAL_PRICE"})
                continue

            market = live_by_code.get(code)
            if market is None:
                promoted_bad.append({"code": code, "reason": "NOT_IN_CANDIDATE_LIVE"})
                continue
            official = float(market["latest_price"])
            if not all(math.isfinite(x) and x > 0 for x in (terminal_raw, terminal_adj, official)):
                promoted_bad.append({"code": code, "reason": "NONPOSITIVE_TERMINAL_PRICE"})
                continue
            if abs(terminal_raw - official) > 1e-9 or abs(terminal_adj - official) > 1e-9:
                promoted_bad.append({
                    "code": code,
                    "reason": f"TERMINAL_MISMATCH raw={terminal_raw} adj={terminal_adj} official={official}",
                })

        quarantined_leaks = []
        for code in sorted(blocked_codes | absent_codes):
            path = cache / f"BSE-{code}.csv"
            if path.is_file():
                quarantined_leaks.append({
                    "bse_code": code,
                    "kind": "BLOCKED" if code in blocked_codes else "ABSENT_CURRENT",
                    "path": str(path),
                })

        if promoted_bad:
            errors.append(f"{len(promoted_bad)} promoted cache files failed validation.")
        if quarantined_leaks:
            errors.append(
                f"{len(quarantined_leaks)} blocked/absent BSE cache files leaked into candidate cache."
            )

        summary = {
            "promoted_codes": len(promoted_codes),
            "blocked_current_codes": len(blocked_codes),
            "absent_current_codes": len(absent_codes),
            "promoted_files_bad": len(promoted_bad),
            "quarantine_leaks": len(quarantined_leaks),
            "candidate_cache_csv_files": len(list(cache.glob("*.csv"))) if cache.is_dir() else 0,
            "errors": errors,
            "warnings": warnings,
        }

        report_root = cache.parent / "bse_candidate_cache_audit_20260907"
        report_root.mkdir(parents=True, exist_ok=True)
        (report_root / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        if promoted_bad:
            fields = sorted({k for r in promoted_bad for k in r})
            with (report_root / "promoted_failures.csv").open(
                "w", encoding="utf-8", newline=""
            ) as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerows(promoted_bad)

        if quarantined_leaks:
            with (report_root / "quarantine_leaks.csv").open(
                "w", encoding="utf-8", newline=""
            ) as f:
                w = csv.DictWriter(f, fieldnames=["bse_code", "kind", "path"])
                w.writeheader()
                w.writerows(quarantined_leaks)

        print(json.dumps(summary, indent=2, sort_keys=True))
        print(f"Audit report: {report_root}")

        if errors:
            print("BSE CANDIDATE CACHE QUARANTINE AUDIT: FAIL")
            return 2

        print("BSE CANDIDATE CACHE QUARANTINE AUDIT: PASS")
        return 0

    except Exception as exc:
        print(
            f"BSE CANDIDATE CACHE QUARANTINE AUDIT FAILED TO RUN: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
