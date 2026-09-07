from __future__ import annotations

import argparse
import csv
from datetime import datetime, date
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys


DEFAULT_DOWNLOADS = Path.home() / "Downloads"

PRICE_AUDIT = DEFAULT_DOWNLOADS / "BSE_History_Final_Audit" / "combined_912_status.csv"
ANNOUNCEMENTS = DEFAULT_DOWNLOADS / "BSE_Historical_Announcements_v2" / "normalized" / "relevant_events.csv"
ANN_STATE = DEFAULT_DOWNLOADS / "BSE_Historical_Announcements_v2" / "state" / "progress.sqlite"
STRUCTURED = DEFAULT_DOWNLOADS / "BSE_Structured_Corporate_Actions" / "normalized" / "events.csv"
STRUCT_STATE = DEFAULT_DOWNLOADS / "BSE_Structured_Corporate_Actions" / "state" / "progress.sqlite"
OUTPUT = DEFAULT_DOWNLOADS / "BSE_Combined_Integration_Stage"

IDENTITY_TYPES = {
    "MERGER", "DEMERGER", "SCHEME_OF_ARRANGEMENT",
    "CAPITAL_REDUCTION", "CONSOLIDATION", "DELISTING",
}
PRICE_ACTION_TYPES = {"SPLIT", "BONUS", "RIGHTS", "DIVIDEND", "BUYBACK"}


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    temp.replace(path)


def split_types(value: str) -> set[str]:
    return {x.strip() for x in str(value or "").split("|") if x.strip()}


def parse_bse_date(value: str) -> str:
    s = str(value or "").strip()
    if not s or s.lower() in {"-", "--", "na", "n/a", "none", "null", "nan"}:
        return ""
    for fmt in ("%d %b %Y", "%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"unparseable BSE date: {s!r}")


def sqlite_status_counts(path: Path) -> dict[str, int]:
    if not path.is_file():
        raise FileNotFoundError(path)
    con = sqlite3.connect(str(path))
    try:
        tables = {
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in ("chunks", "tasks", "scrips"):
            if table not in tables:
                continue
            cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
            if "status" not in cols:
                continue
            rows = con.execute(
                f"SELECT status,COUNT(*) FROM {table} GROUP BY status"
            ).fetchall()
            return {str(k): int(v) for k, v in rows}
    finally:
        con.close()
    raise ValueError(f"no status-bearing table found in {path}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Stage audited BSE price-history evidence and corporate-action evidence together without mutating the ranking platform."
    )
    p.add_argument("--price-audit", type=Path, default=PRICE_AUDIT)
    p.add_argument("--announcements", type=Path, default=ANNOUNCEMENTS)
    p.add_argument("--announcement-state", type=Path, default=ANN_STATE)
    p.add_argument("--structured-actions", type=Path, default=STRUCTURED)
    p.add_argument("--structured-state", type=Path, default=STRUCT_STATE)
    p.add_argument("--output-root", type=Path, default=OUTPUT)
    args = p.parse_args(argv)

    try:
        prices = read_csv(args.price_audit)
        anns = read_csv(args.announcements)
        structured = read_csv(args.structured_actions)
        ann_states = sqlite_status_counts(args.announcement_state)
        struct_states = sqlite_status_counts(args.structured_state)

        errors = []
        warnings = []

        # --- Price evidence ---
        price_codes = {str(r["bse_code"]).zfill(6) for r in prices}
        if len(prices) != 912:
            errors.append(f"price evidence has {len(prices)} rows; expected 912")
        if len(price_codes) != 228:
            errors.append(f"price evidence has {len(price_codes)} codes; expected 228")

        final_counts = {}
        for r in prices:
            s = str(r["final_status"])
            final_counts[s] = final_counts.get(s, 0) + 1
        allowed_final = {"DIRECT_OK", "NO_RECORD_CONFIRMED", "BHAVCOPY_RECOVERED"}
        bad_final = {k: v for k, v in final_counts.items() if k not in allowed_final}
        if bad_final:
            errors.append(f"unexpected price final statuses: {bad_final}")

        # --- Announcement evidence ---
        ann_codes = {str(r["bse_code"]).zfill(6) for r in anns}
        outside_ann = sorted(ann_codes - price_codes)
        if outside_ann:
            errors.append(f"announcement evidence contains {len(outside_ann)} codes outside 228 universe")

        if ann_states != {"OK": 1368}:
            errors.append(f"announcement state not fully OK: {ann_states}")

        identity_candidates = []
        announcement_price_candidates = []
        for r in anns:
            types = split_types(r.get("event_types", ""))
            if types & IDENTITY_TYPES:
                x = dict(r)
                x["matched_identity_types"] = "|".join(sorted(types & IDENTITY_TYPES))
                identity_candidates.append(x)
            if types & PRICE_ACTION_TYPES:
                x = dict(r)
                x["matched_price_action_types"] = "|".join(sorted(types & PRICE_ACTION_TYPES))
                announcement_price_candidates.append(x)

        # --- Structured action evidence ---
        if struct_states != {"OK": 1368}:
            errors.append(f"structured-action state not fully OK: {struct_states}")

        structured_codes = {str(r["bse_code"]).zfill(6) for r in structured}
        outside_struct = sorted(structured_codes - price_codes)
        if outside_struct:
            errors.append(f"structured evidence contains {len(outside_struct)} codes outside 228 universe")

        normalized_structured = []
        for r in structured:
            x = dict(r)
            x["bse_code"] = str(x["bse_code"]).zfill(6)
            x["ex_date_iso"] = parse_bse_date(x.get("ex_date", ""))
            x["record_date_iso"] = parse_bse_date(x.get("record_date", ""))
            x["payment_date_iso"] = parse_bse_date(x.get("payment_date", ""))
            et = str(x.get("event_type", "")).strip().upper()
            x["adjustment_policy"] = (
                "RATIO_REQUIRED"
                if et in {"SPLIT", "BONUS"}
                else "TERMS_REQUIRED"
                if et == "RIGHTS"
                else "PRICE_RETURN_NO_ADJUSTMENT_BY_DEFAULT"
                if et == "DIVIDEND"
                else "IDENTITY_REVIEW"
                if et == "MERGER_DEMERGER_SCHEME"
                else "NO_AUTOMATIC_PRICE_ADJUSTMENT"
            )
            normalized_structured.append(x)

        # Per-code combined evidence summary.
        per_code = {}
        for code in sorted(price_codes):
            per_code[code] = {
                "bse_code": code,
                "price_windows_total": 0,
                "price_windows_with_data": 0,
                "price_windows_no_record": 0,
                "announcement_candidates": 0,
                "identity_candidates": 0,
                "structured_actions": 0,
                "split_actions": 0,
                "bonus_actions": 0,
                "rights_actions": 0,
                "dividend_actions": 0,
            }

        for r in prices:
            code = str(r["bse_code"]).zfill(6)
            per_code[code]["price_windows_total"] += 1
            if r["final_status"] in {"DIRECT_OK", "BHAVCOPY_RECOVERED"}:
                per_code[code]["price_windows_with_data"] += 1
            if r["final_status"] == "NO_RECORD_CONFIRMED":
                per_code[code]["price_windows_no_record"] += 1

        for r in anns:
            code = str(r["bse_code"]).zfill(6)
            per_code[code]["announcement_candidates"] += 1
            if split_types(r.get("event_types", "")) & IDENTITY_TYPES:
                per_code[code]["identity_candidates"] += 1

        for r in normalized_structured:
            code = str(r["bse_code"]).zfill(6)
            per_code[code]["structured_actions"] += 1
            et = str(r.get("event_type", "")).upper()
            if et == "SPLIT":
                per_code[code]["split_actions"] += 1
            elif et == "BONUS":
                per_code[code]["bonus_actions"] += 1
            elif et == "RIGHTS":
                per_code[code]["rights_actions"] += 1
            elif et == "DIVIDEND":
                per_code[code]["dividend_actions"] += 1

        # Conservative staging policy:
        # - Never bridge history across a merger/demerger/scheme automatically.
        # - Never calculate split/bonus/rights factors just from keyword announcements.
        # - Structured ex-date evidence is canonical for ordinary corporate actions.
        # - Announcement evidence is a candidate/identity layer until separately resolved.
        summary = {
            "price": {
                "rows": len(prices),
                "codes": len(price_codes),
                "final_statuses": final_counts,
            },
            "announcements": {
                "rows": len(anns),
                "codes_with_candidates": len(ann_codes),
                "state_statuses": ann_states,
                "identity_candidates": len(identity_candidates),
                "price_action_candidates": len(announcement_price_candidates),
            },
            "structured_actions": {
                "rows": len(structured),
                "codes_with_actions": len(structured_codes),
                "state_statuses": struct_states,
                "by_type": {},
            },
            "policy": {
                "raw_exchange_prices_preserved": True,
                "automatic_merger_history_bridge": False,
                "automatic_rights_adjustment": False,
                "dividend_default": "PRICE_RETURN_NO_ADJUSTMENT",
                "split_bonus_require_parsed_ratio": True,
            },
            "errors": errors,
            "warnings": warnings,
        }

        for r in normalized_structured:
            et = str(r.get("event_type", "")).upper()
            summary["structured_actions"]["by_type"][et] = (
                summary["structured_actions"]["by_type"].get(et, 0) + 1
            )

        root = args.output_root
        root.mkdir(parents=True, exist_ok=True)

        # Copy/normalize evidence into one immutable-ish stage directory.
        price_fields = list(prices[0].keys()) if prices else []
        ann_fields = list(anns[0].keys()) if anns else []
        structured_fields = (
            list(normalized_structured[0].keys()) if normalized_structured else
            ["bse_code","short_name","long_name","ex_date","record_date","purpose","event_type",
             "bc_start_date","bc_end_date","no_delivery_start","no_delivery_end","payment_date",
             "source","source_chunk","ex_date_iso","record_date_iso","payment_date_iso","adjustment_policy"]
        )

        write_csv(root / "price_window_evidence.csv", prices, price_fields)
        write_csv(root / "structured_actions.csv", normalized_structured, structured_fields)

        id_fields = ann_fields + (["matched_identity_types"] if ann_fields else [])
        ap_fields = ann_fields + (["matched_price_action_types"] if ann_fields else [])
        write_csv(root / "identity_event_candidates.csv", identity_candidates, id_fields)
        write_csv(root / "announcement_price_action_candidates.csv", announcement_price_candidates, ap_fields)

        code_rows = list(per_code.values())
        write_csv(root / "per_code_evidence_summary.csv", code_rows, list(code_rows[0].keys()))

        (root / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        print(json.dumps(summary, indent=2, sort_keys=True))
        print(f"Stage root: {root}")
        print(f"Per-code summary: {root / 'per_code_evidence_summary.csv'}")
        print(f"Identity candidates: {root / 'identity_event_candidates.csv'}")
        print(f"Structured actions: {root / 'structured_actions.csv'}")

        if errors:
            print("STAGING AUDIT: FAIL")
            return 2

        print("STAGING AUDIT: PASS")
        print("No ranking-platform files were modified.")
        return 0

    except Exception as exc:
        print(f"STAGING FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
