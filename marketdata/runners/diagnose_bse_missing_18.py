from __future__ import annotations

import csv
import re
from pathlib import Path
from zipfile import ZipFile

HOME = Path.home()
PROJECT = HOME / "Downloads" / "stock-ranking-platform"

CANDIDATE = PROJECT / "data" / "live_market" / "candidate_bse_20260907" / "live_market.csv"
BSE_BHAV = PROJECT / "data" / "live_market" / "source" / "bse_bhavcopy_20260907.csv"

PHASE1_CANDIDATES = (
    HOME / "Downloads" / "BSE_2025_2026(1).zip",
    HOME / "Downloads" / "BSE_2025_2026.zip",
    HOME / "Downloads" / "BSE_2025_2026",
)

CODE_RE = re.compile(r"^(?:BSE_)?(?P<code>\d{6})(?:[_-].*)?\.csv$", re.I)


def norm_code(v):
    s = str(v or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(6) if s.isdigit() else s


def read_csv(path: Path):
    if not path.is_file():
        raise SystemExit(f"Missing file: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def discover_phase1():
    for p in PHASE1_CANDIDATES:
        if p.exists():
            return p
    raise SystemExit("Could not find BSE_2025_2026 source in Downloads")


def phase1_codes(source: Path):
    if source.is_dir():
        names = [p.name for p in source.rglob("*.csv")]
    else:
        with ZipFile(source) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    out = set()
    for name in names:
        m = CODE_RE.fullmatch(Path(name).name)
        if m:
            out.add(m.group("code"))
    return out


def ordinary_equity_reason(row: dict) -> tuple[bool, str]:
    """
    Mirror the current repo's BSE ordinary-equity gates closely enough to
    explain why a raw BSE row may not appear in the candidate universe.
    """
    isin = str(row.get("ISIN", "")).strip().upper()
    series = str(row.get("SctySrs", "")).strip().upper()
    ticker = str(row.get("TckrSymb", "")).strip().upper()
    instr = str(row.get("FinInstrmTp", "")).strip().upper()
    segment = str(row.get("Sgmt", "")).strip().upper()
    src = str(row.get("Src", "")).strip().upper()

    if segment != "CM" or src != "BSE" or instr != "STK":
        return False, "NOT_BSE_CM_STK"
    if not re.fullmatch(r"IN[A-Z0-9]{9}[0-9]", isin):
        return False, "INVALID_ISIN"

    issuer_family = isin[2:3]
    security_code = isin[7:9]

    if series in {"IF", "R", "G"}:
        return False, f"EXCLUDED_SERIES_{series}"
    if issuer_family == "F":
        return False, "FUND_OR_ETF"
    if issuer_family in {"A", "B", "0"}:
        return False, "GOVERNMENT_OR_DEBT"
    if series == "IF" or security_code in {"23", "25"}:
        return False, "LISTED_TRUST_UNIT"
    if series == "R" or security_code == "20":
        return False, "RIGHTS_ENTITLEMENT"
    if issuer_family == "9" or "DVR" in ticker:
        return False, "ALTERNATE_SECURITY_CLASS"
    if issuer_family != "E":
        return False, f"NON_COMPANY_ISSUER_FAMILY_{issuer_family}"
    if security_code != "01":
        return False, f"NON_ORDINARY_SECURITY_CODE_{security_code}"

    return True, "ELIGIBLE_ORDINARY_EQUITY"


def main():
    source = discover_phase1()
    targets = phase1_codes(source)
    if len(targets) != 228:
        raise SystemExit(f"Expected 228 target codes, got {len(targets)}")

    live = read_csv(CANDIDATE)
    bhav = read_csv(BSE_BHAV)

    live_by_isin = {}
    live_by_bse_code = {}
    live_by_bse_ticker = {}

    for r in live:
        isin = str(r.get("isin", "")).strip().upper()
        if isin:
            live_by_isin[isin] = r

        code = norm_code(r.get("exchange_security_id", ""))
        if (
            str(r.get("primary_exchange", "")).strip().upper() == "BSE"
            and re.fullmatch(r"\d{6}", code)
        ):
            live_by_bse_code[code] = r

        ticker = str(r.get("ticker", "")).strip().upper()
        m = re.fullmatch(r"BSE-(\d{6})", ticker)
        if m:
            live_by_bse_ticker[m.group(1)] = r

    raw_by_code = {}
    for r in bhav:
        code = norm_code(r.get("FinInstrmId", ""))
        if re.fullmatch(r"\d{6}", code):
            raw_by_code[code] = r

    direct = targets & (set(live_by_bse_code) | set(live_by_bse_ticker))
    missing = sorted(targets - direct)

    rows = []
    status_counts = {}

    for code in missing:
        raw = raw_by_code.get(code)

        if raw is None:
            status = "NOT_IN_2026_09_07_BHAVCOPY"
            detail = "No raw BSE row for this six-digit code on 2026-09-07."
            raw_isin = raw_ticker = raw_series = raw_name = ""
            candidate_ticker = candidate_exchange = candidate_isin = ""
        else:
            raw_isin = str(raw.get("ISIN", "")).strip().upper()
            raw_ticker = str(raw.get("TckrSymb", "")).strip()
            raw_series = str(raw.get("SctySrs", "")).strip()
            raw_name = str(raw.get("FinInstrmNm", "")).strip()

            candidate = live_by_isin.get(raw_isin)
            eligible, reason = ordinary_equity_reason(raw)

            if candidate is not None:
                candidate_ticker = str(candidate.get("ticker", "")).strip()
                candidate_exchange = str(candidate.get("primary_exchange", "")).strip()
                candidate_isin = str(candidate.get("isin", "")).strip()

                if candidate_exchange.upper() == "NSE":
                    status = "DUAL_LISTED_ISIN_MAPS_TO_NSE"
                    detail = (
                        "Exact BSE raw row exists, but its ISIN is already represented "
                        "by an NSE primary-security row in the candidate universe."
                    )
                else:
                    status = "ISIN_PRESENT_DIFFERENT_REPRESENTATION"
                    detail = (
                        "Exact ISIN exists in candidate universe, but not under the expected "
                        "BSE-<code> / BSE primary representation."
                    )
            elif not eligible:
                candidate_ticker = candidate_exchange = candidate_isin = ""
                status = "EXCLUDED_BY_ORDINARY_EQUITY_CONTRACT"
                detail = reason
            else:
                candidate_ticker = candidate_exchange = candidate_isin = ""
                status = "RAW_BSE_ELIGIBLE_BUT_NOT_IN_CANDIDATE"
                detail = (
                    "Raw 2026-09-07 BSE row appears ordinary-equity eligible but is absent "
                    "from the candidate bundle. This needs code-level investigation."
                )

        status_counts[status] = status_counts.get(status, 0) + 1
        rows.append({
            "bse_code": code,
            "status": status,
            "detail": detail,
            "raw_isin": raw_isin,
            "raw_ticker": raw_ticker,
            "raw_series": raw_series,
            "raw_company": raw_name,
            "candidate_ticker": candidate_ticker,
            "candidate_primary_exchange": candidate_exchange,
            "candidate_isin": candidate_isin,
        })

    out = HOME / "Downloads" / "BSE_Missing18_Diagnostic.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            w.writeheader()
            w.writerows(rows)

    print("BSE MISSING-18 RESOLUTION DIAGNOSTIC")
    print("=" * 90)
    print("target codes:", len(targets))
    print("direct BSE-code matches:", len(direct))
    print("codes requiring resolution:", len(missing))
    print("status counts:", status_counts)
    print()

    for r in rows:
        print(
            f"{r['bse_code']} | {r['status']} | "
            f"raw_ticker={r['raw_ticker']} | isin={r['raw_isin']} | "
            f"candidate={r['candidate_ticker']} | {r['detail']}"
        )

    print()
    print("CSV:", out)

    unsafe = [
        r for r in rows
        if r["status"] == "RAW_BSE_ELIGIBLE_BUT_NOT_IN_CANDIDATE"
    ]
    if unsafe:
        print("MISSING-18 AUDIT: FAIL")
        return 2

    print("MISSING-18 AUDIT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
