from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
from zipfile import ZipFile


HOME = Path.home()
DOWNLOADS = HOME / "Downloads"

DEFAULT_STAGE = DOWNLOADS / "BSE_Combined_Integration_Stage"
DEFAULT_DIRECT_DB = DOWNLOADS / "BSE_History_Direct" / "state" / "progress.sqlite"
DEFAULT_PHASE1 = DOWNLOADS / "BSE_2025_2026(1).zip"
DEFAULT_PROJECT = DOWNLOADS / "stock-ranking-platform"
DEFAULT_OUTPUT = DOWNLOADS / "BSE_Adjustment_Readiness"

PRICE_ACTIONS = {"SPLIT", "BONUS", "RIGHTS", "DIVIDEND"}
IDENTITY_TYPES = {
    "MERGER", "DEMERGER", "SCHEME_OF_ARRANGEMENT",
    "CAPITAL_REDUCTION", "CONSOLIDATION", "DELISTING",
}

RAW_REQUIRED = (
    "Date", "Open Price", "High Price", "Low Price", "Close Price", "No.of Shares",
)

PURPOSE_RATIO = re.compile(r"(?<!\d)(\d+(?:\.\d+)?)\s*[:/]\s*(\d+(?:\.\d+)?)(?!\d)")
NUMBER = r"(\d+(?:\.\d+)?)"

DIVIDEND_PATTERNS = (
    re.compile(r"(?:rs\.?|inr)\s*[-:]?\s*" + NUMBER, re.I),
    re.compile(r"dividend[^0-9]{0,40}" + NUMBER + r"\s*(?:rs\.?|inr)", re.I),
)
ISSUE_PRICE_PATTERNS = (
    re.compile(r"(?:issue|offer|subscription)\s+price[^0-9]{0,30}(?:rs\.?|inr)?\s*" + NUMBER, re.I),
    re.compile(r"(?:@|at)\s*(?:rs\.?|inr)\s*" + NUMBER, re.I),
)
SPLIT_FACE_VALUE_PATTERNS = (
    re.compile(
        r"(?:from|face\s+value(?:\s+of)?)\s*(?:rs\.?|inr)?\s*" + NUMBER +
        r"[^0-9]{0,40}(?:to|into)\s*(?:rs\.?|inr)?\s*" + NUMBER,
        re.I,
    ),
    re.compile(
        r"(?:rs\.?|inr)\s*" + NUMBER +
        r"[^0-9]{0,40}(?:to|into)\s*(?:rs\.?|inr)\s*" + NUMBER,
        re.I,
    ),
)


def norm_code(v: object) -> str:
    s = str(v or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(6) if s.isdigit() else s


def parse_bse_date(value: str) -> date:
    s = str(value or "").strip()
    for fmt in ("%d-%B-%Y", "%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unparseable BSE date: {s!r}")


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def load_live_code_map(project: Path) -> dict[str, dict]:
    path = project / "data" / "live_market" / "current" / "live_market.csv"
    rows = read_csv(path)
    result = {}
    for r in rows:
        if str(r.get("primary_exchange", "")).strip().upper() != "BSE":
            continue
        code = norm_code(r.get("exchange_security_id"))
        if not re.fullmatch(r"\d{6}", code):
            continue
        result[code] = {
            "ticker": str(r.get("ticker", "")).strip(),
            "isin": str(r.get("isin", "")).strip(),
            "company": str(r.get("company", "")).strip(),
            "listing_date": str(r.get("listing_date", "")).strip(),
            "latest_price": str(r.get("latest_price", "")).strip(),
        }
    return result


def decode_csv(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    raise ValueError("cannot decode CSV")


def parse_stockprice_csv(raw: bytes, expected_code: str, source_label: str) -> list[dict]:
    text = decode_csv(raw)
    reader = csv.DictReader(io.StringIO(text))
    fields = [str(x or "").strip().lstrip("\ufeff") for x in (reader.fieldnames or [])]
    missing = [c for c in RAW_REQUIRED if c not in fields]
    if missing:
        raise ValueError(f"{source_label}: missing columns {missing}")

    rows = []
    for n, raw_row in enumerate(reader, 2):
        r = {str(k or "").strip().lstrip("\ufeff"): str(v or "").strip() for k, v in raw_row.items()}
        if not any(r.values()):
            continue
        d = parse_bse_date(r["Date"])
        vals = {}
        for col in ("Open Price", "High Price", "Low Price", "Close Price", "No.of Shares"):
            try:
                vals[col] = float(r[col].replace(",", ""))
            except Exception as exc:
                raise ValueError(f"{source_label}: row {n} bad {col}") from exc
            if not math.isfinite(vals[col]) or vals[col] < 0:
                raise ValueError(f"{source_label}: row {n} invalid {col}")
        o, h, l, c = vals["Open Price"], vals["High Price"], vals["Low Price"], vals["Close Price"]
        if h < l or h < max(o, c) or l > min(o, c):
            raise ValueError(f"{source_label}: row {n} impossible OHLC")
        rows.append({
            "date": d.isoformat(),
            "bse_code": expected_code,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": int(vals["No.of Shares"]),
            "source": source_label,
        })
    return rows


def find_phase1(downloads: Path, explicit: Path | None) -> Path:
    if explicit is not None and explicit.exists():
        return explicit
    for p in (
        downloads / "BSE_2025_2026(1).zip",
        downloads / "BSE_2025_2026.zip",
        downloads / "BSE_2025_2026",
    ):
        if p.exists():
            return p
    zips = sorted(downloads.glob("BSE_2025_2026*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    if zips:
        return zips[0]
    raise FileNotFoundError("phase-1 BSE 2025-2026 source not found")


def load_phase1_histories(source: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    if source.is_file():
        with ZipFile(source) as zf:
            for name in zf.namelist():
                if not name.lower().endswith(".csv"):
                    continue
                m = re.fullmatch(r"(?:BSE_)?(\d{6})(?:[_-].*)?\.csv", Path(name).name, re.I)
                if not m:
                    continue
                code = m.group(1)
                out.setdefault(code, []).extend(
                    parse_stockprice_csv(zf.read(name), code, f"PHASE1:{Path(name).name}")
                )
    else:
        for p in source.rglob("*.csv"):
            m = re.fullmatch(r"(?:BSE_)?(\d{6})(?:[_-].*)?\.csv", p.name, re.I)
            if not m:
                continue
            code = m.group(1)
            out.setdefault(code, []).extend(
                parse_stockprice_csv(p.read_bytes(), code, f"PHASE1:{p.name}")
            )
    return out


def load_direct_histories(db_path: Path) -> dict[str, list[dict]]:
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute("""
            SELECT bse_code,output_file
            FROM tasks
            WHERE status='DIRECT_OK'
            ORDER BY bse_code,from_date
        """).fetchall()
    finally:
        con.close()

    out: dict[str, list[dict]] = {}
    for code_raw, file_raw in rows:
        code = norm_code(code_raw)
        if not file_raw:
            raise ValueError(f"DIRECT_OK missing output file for {code}")
        path = Path(file_raw)
        if not path.is_file():
            raise FileNotFoundError(path)
        out.setdefault(code, []).extend(
            parse_stockprice_csv(path.read_bytes(), code, f"DIRECT:{path.name}")
        )
    return out


def merge_history(code: str, groups: list[list[dict]]) -> list[dict]:
    by_date = {}
    for rows in groups:
        for r in rows:
            key = r["date"]
            if key in by_date:
                old = by_date[key]
                for col in ("open", "high", "low", "close", "volume"):
                    if abs(float(old[col]) - float(r[col])) > 1e-9:
                        raise ValueError(f"{code} conflicting duplicate {key} {col}")
                # Prefer direct historical evidence over phase1 only if identical.
                if str(r["source"]).startswith("DIRECT:"):
                    by_date[key] = r
            else:
                by_date[key] = r
    return [by_date[k] for k in sorted(by_date)]


def prior_close(history: list[dict], ex_date: date, max_days: int = 14) -> tuple[str, float] | None:
    candidates = [r for r in history if date.fromisoformat(r["date"]) < ex_date]
    if not candidates:
        return None
    r = candidates[-1]
    d = date.fromisoformat(r["date"])
    if (ex_date - d).days > max_days:
        return None
    return r["date"], float(r["close"])


def ratio_any(text: str) -> tuple[float, float] | None:
    m = PURPOSE_RATIO.search(text or "")
    if not m:
        return None
    a, b = float(m.group(1)), float(m.group(2))
    if a <= 0 or b <= 0:
        return None
    return a, b


def parse_split_factor(purpose: str) -> tuple[float | None, str]:
    for pat in SPLIT_FACE_VALUE_PATTERNS:
        m = pat.search(purpose or "")
        if m:
            old_fv, new_fv = float(m.group(1)), float(m.group(2))
            if old_fv > 0 and new_fv > 0 and old_fv > new_fv:
                return new_fv / old_fv, f"face_value:{old_fv:g}->{new_fv:g}"
    ratio = ratio_any(purpose)
    if ratio:
        a, b = ratio
        # For text explicitly saying "split X:Y", interpret as post:pre shares.
        if re.search(r"\bsplit\b", purpose or "", re.I):
            post_per_pre = a / b
            if post_per_pre > 1:
                return 1.0 / post_per_pre, f"share_ratio:{a:g}:{b:g}"
    return None, "split ratio not conservatively parseable"


def parse_bonus_factor(purpose: str) -> tuple[float | None, str]:
    ratio = ratio_any(purpose)
    if not ratio:
        return None, "bonus ratio missing"
    bonus, existing = ratio
    factor = existing / (existing + bonus)
    if not (0 < factor <= 1):
        return None, "invalid bonus ratio"
    return factor, f"bonus:{bonus:g}:{existing:g}"


def parse_dividend_amount(purpose: str) -> tuple[float | None, str]:
    text = purpose or ""
    # Prefer an amount that occurs close to "Dividend".
    candidates = []
    for pat in DIVIDEND_PATTERNS:
        for m in pat.finditer(text):
            try:
                candidates.append(float(m.group(1)))
            except Exception:
                pass
    candidates = [x for x in candidates if x >= 0 and math.isfinite(x)]
    if not candidates:
        return None, "cash dividend amount not parseable"
    # BSE purpose usually exposes a single Rs amount; if multiple candidates,
    # use the last one only when they are numerically identical.
    uniq = sorted({round(x, 10) for x in candidates})
    if len(uniq) != 1:
        return None, f"ambiguous dividend amounts {uniq}"
    return float(uniq[0]), f"cash_dividend_rs:{uniq[0]:g}"


def parse_rights_terms(purpose: str) -> tuple[tuple[float, float, float] | None, str]:
    ratio = ratio_any(purpose)
    if not ratio:
        return None, "rights ratio missing"
    rights, existing = ratio
    prices = []
    for pat in ISSUE_PRICE_PATTERNS:
        for m in pat.finditer(purpose or ""):
            try:
                prices.append(float(m.group(1)))
            except Exception:
                pass
    uniq = sorted({round(x, 10) for x in prices if x >= 0 and math.isfinite(x)})
    if len(uniq) != 1:
        return None, "rights issue price missing/ambiguous"
    return (rights, existing, float(uniq[0])), f"rights:{rights:g}:{existing:g}@{uniq[0]:g}"


def announcement_types(row: dict) -> set[str]:
    return {x for x in str(row.get("matched_identity_types", row.get("event_types", ""))).split("|") if x}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Build official raw BSE history candidates and audit whether corporate actions are ready for deterministic adjustment."
    )
    p.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT)
    p.add_argument("--stage-root", type=Path, default=DEFAULT_STAGE)
    p.add_argument("--direct-db", type=Path, default=DEFAULT_DIRECT_DB)
    p.add_argument("--phase1", type=Path)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = p.parse_args(argv)

    try:
        stage = args.stage_root.resolve()
        structured = read_csv(stage / "structured_actions.csv")
        identity = read_csv(stage / "identity_event_candidates.csv")
        price_evidence = read_csv(stage / "price_window_evidence.csv")

        live_map = load_live_code_map(args.project_root.resolve())
        phase1_source = find_phase1(DOWNLOADS, args.phase1.resolve() if args.phase1 else None)
        phase1 = load_phase1_histories(phase1_source)
        direct = load_direct_histories(args.direct_db.resolve())

        codes = sorted({norm_code(r["bse_code"]) for r in price_evidence})
        if len(codes) != 228:
            raise ValueError(f"expected 228 price-evidence codes, got {len(codes)}")

        histories = {}
        for code in codes:
            histories[code] = merge_history(code, [direct.get(code, []), phase1.get(code, [])])

        # Only codes with actual raw price observations can affect ranking metrics.
        priced_codes = {c for c, rows in histories.items() if rows}
        identity_by_code: dict[str, list[dict]] = {}
        for r in identity:
            identity_by_code.setdefault(norm_code(r["bse_code"]), []).append(r)

        action_rows = []
        ready_counts = {}
        structured_by_code: dict[str, list[dict]] = {}
        for r in structured:
            code = norm_code(r["bse_code"])
            structured_by_code.setdefault(code, []).append(r)

            event_type = str(r.get("event_type", "")).strip().upper()
            ex_iso = str(r.get("ex_date_iso", "")).strip()
            purpose = str(r.get("purpose", "")).strip()
            readiness = "NOT_PRICE_AFFECTING"
            method = ""
            candidate_factor = ""
            prior_date_s = ""
            prior_close_v = ""
            note = ""

            if event_type in PRICE_ACTIONS:
                if not ex_iso:
                    readiness = "UNRESOLVED"
                    note = "structured price action has no parseable ex-date"
                elif code not in priced_codes:
                    readiness = "IRRELEVANT_NO_PRICE_HISTORY"
                    note = "no raw history exists for this exact code"
                else:
                    ex = date.fromisoformat(ex_iso)
                    prior = prior_close(histories[code], ex)
                    if prior is None:
                        readiness = "UNRESOLVED"
                        note = "no prior raw close within 14 days of ex-date"
                    else:
                        prior_date_s, prior_close_v = prior[0], prior[1]
                        if event_type == "SPLIT":
                            factor, method = parse_split_factor(purpose)
                            if factor is None:
                                readiness = "UNRESOLVED"
                                note = method
                            else:
                                readiness = "READY"
                                candidate_factor = factor
                        elif event_type == "BONUS":
                            factor, method = parse_bonus_factor(purpose)
                            if factor is None:
                                readiness = "UNRESOLVED"
                                note = method
                            else:
                                readiness = "READY"
                                candidate_factor = factor
                        elif event_type == "DIVIDEND":
                            amount, method = parse_dividend_amount(purpose)
                            if amount is None:
                                readiness = "UNRESOLVED"
                                note = method
                            elif prior_close_v <= amount:
                                readiness = "UNRESOLVED"
                                note = "cash dividend is not below prior close"
                            else:
                                readiness = "READY"
                                candidate_factor = (prior_close_v - amount) / prior_close_v
                        elif event_type == "RIGHTS":
                            terms, method = parse_rights_terms(purpose)
                            if terms is None:
                                readiness = "UNRESOLVED"
                                note = method
                            else:
                                rights, existing, issue_price = terms
                                theoretical_ex = (
                                    prior_close_v * existing + issue_price * rights
                                ) / (existing + rights)
                                factor = theoretical_ex / prior_close_v
                                if not (0 < factor <= 1.5):
                                    readiness = "UNRESOLVED"
                                    note = f"implausible rights factor {factor}"
                                else:
                                    readiness = "READY"
                                    candidate_factor = factor

            action = dict(r)
            action.update({
                "bse_code": code,
                "ticker": live_map.get(code, {}).get("ticker", ""),
                "isin": live_map.get(code, {}).get("isin", ""),
                "adjustment_readiness": readiness,
                "candidate_method": method,
                "candidate_backward_factor": candidate_factor,
                "prior_trade_date": prior_date_s,
                "prior_raw_close": prior_close_v,
                "note": note,
            })
            action_rows.append(action)
            ready_counts[readiness] = ready_counts.get(readiness, 0) + 1

        # Detect same-code/same-ex-date multi-action groups; auto-application is unsafe.
        groups: dict[tuple[str, str], list[int]] = {}
        for idx, r in enumerate(action_rows):
            if str(r.get("ex_date_iso", "")).strip() and str(r.get("event_type", "")).upper() in PRICE_ACTIONS:
                groups.setdefault((r["bse_code"], r["ex_date_iso"]), []).append(idx)
        multi_groups = 0
        for key, idxs in groups.items():
            if len(idxs) <= 1:
                continue
            multi_groups += 1
            for i in idxs:
                if action_rows[i]["adjustment_readiness"] == "READY":
                    action_rows[i]["adjustment_readiness"] = "REVIEW_MULTI_ACTION_SAME_DATE"
                    action_rows[i]["note"] = (
                        "multiple price-affecting actions share this ex-date; "
                        "combine explicitly before applying any factor"
                    )

        # Per-code promotion policy.
        code_rows = []
        promotion_counts = {}
        for code in codes:
            raw = histories[code]
            struct = structured_by_code.get(code, [])
            idc = identity_by_code.get(code, [])
            action_subset = [r for r in action_rows if r["bse_code"] == code]
            unresolved = [
                r for r in action_subset
                if r["adjustment_readiness"] in {"UNRESOLVED", "REVIEW_MULTI_ACTION_SAME_DATE"}
            ]
            ready = [r for r in action_subset if r["adjustment_readiness"] == "READY"]

            if not raw:
                policy = "NO_HISTORY_CONFIRMED"
                reason = "No official raw trading history exists for this exact BSE code in the acquired period."
            elif idc:
                policy = "IDENTITY_REVIEW_REQUIRED"
                reason = (
                    f"{len(idc)} merger/demerger/scheme/delisting announcement candidate(s) "
                    "must be resolved before adjusted-history promotion."
                )
            elif unresolved:
                policy = "CORPORATE_ACTION_REVIEW_REQUIRED"
                reason = f"{len(unresolved)} structured price action(s) are not deterministically adjustable yet."
            else:
                policy = "ADJUSTMENT_READY"
                reason = (
                    "Raw history exists and all structured price actions are either "
                    "deterministically adjustable or non-price-affecting."
                )

            promotion_counts[policy] = promotion_counts.get(policy, 0) + 1
            lm = live_map.get(code, {})
            code_rows.append({
                "bse_code": code,
                "ticker": lm.get("ticker", ""),
                "isin": lm.get("isin", ""),
                "company": lm.get("company", ""),
                "raw_rows": len(raw),
                "raw_first_date": raw[0]["date"] if raw else "",
                "raw_last_date": raw[-1]["date"] if raw else "",
                "structured_actions": len(struct),
                "ready_adjustments": len(ready),
                "unresolved_price_actions": len(unresolved),
                "identity_candidates": len(idc),
                "promotion_policy": policy,
                "promotion_reason": reason,
            })

        # Write raw histories as candidate artifacts, never into project history_cache yet.
        root = args.output_root.resolve()
        raw_root = root / "raw_history"
        for code, rows in histories.items():
            if not rows:
                continue
            ticker = live_map.get(code, {}).get("ticker", f"BSE-{code}")
            out_path = raw_root / f"{ticker}.csv"
            write_csv(
                out_path,
                rows,
                ["date","bse_code","open","high","low","close","volume","source"],
            )

        action_fields = list(action_rows[0].keys()) if action_rows else [
            "bse_code","ticker","isin","event_type","ex_date_iso","purpose",
            "adjustment_readiness","candidate_method","candidate_backward_factor",
            "prior_trade_date","prior_raw_close","note",
        ]
        write_csv(root / "action_readiness.csv", action_rows, action_fields)
        write_csv(
            root / "per_code_readiness.csv",
            code_rows,
            list(code_rows[0].keys()),
        )

        summary = {
            "codes_total": len(codes),
            "codes_with_raw_history": len(priced_codes),
            "codes_without_raw_history": len(codes) - len(priced_codes),
            "raw_history_rows_total": sum(len(v) for v in histories.values()),
            "structured_actions_total": len(structured),
            "identity_candidates_total": len(identity),
            "action_readiness_counts": ready_counts,
            "multi_action_same_date_groups": multi_groups,
            "promotion_policy_counts": promotion_counts,
            "live_market_code_matches": sum(1 for c in codes if c in live_map),
            "phase1_source": str(phase1_source),
            "policy": {
                "raw_prices_mutated": False,
                "platform_history_cache_mutated": False,
                "identity_candidates_block_auto_promotion": True,
                "unresolved_price_actions_block_auto_promotion": True,
                "dividend_semantics": "candidate Yahoo-compatible backward factor from official cash amount and prior raw close",
                "rights_semantics": "candidate TERP-based factor only when ratio and issue price are parseable",
            },
        }
        root.mkdir(parents=True, exist_ok=True)
        (root / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        print(json.dumps(summary, indent=2, sort_keys=True))
        print(f"Candidate raw histories: {raw_root}")
        print(f"Action readiness: {root / 'action_readiness.csv'}")
        print(f"Per-code readiness: {root / 'per_code_readiness.csv'}")
        print(f"Summary: {root / 'summary.json'}")
        print("ADJUSTMENT READINESS AUDIT: PASS")
        print("No ranking-platform history_cache files were modified.")
        return 0

    except Exception as exc:
        print(f"ADJUSTMENT READINESS AUDIT FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
