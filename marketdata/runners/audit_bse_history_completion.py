from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from zipfile import ZipFile


CODE_RE = re.compile(r"^(?:BSE_)?(?P<code>\d{6})(?:[_-].*)?\.csv$", re.I)

DEFAULT_DOWNLOADS = Path.home() / "Downloads"
DEFAULT_DIRECT_ROOT = DEFAULT_DOWNLOADS / "BSE_History_Direct"
DEFAULT_FALLBACK_ROOT = DEFAULT_DOWNLOADS / "BSE_History_Bhavcopy_Fallback"


def discover_phase1(downloads: Path) -> Path:
    for p in (
        downloads / "BSE_2025_2026",
        downloads / "BSE_2025_2026.zip",
        downloads / "BSE_2025_2026(1).zip",
    ):
        if p.is_dir() or p.is_file():
            return p
    zips = sorted(
        downloads.glob("BSE_2025_2026*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if zips:
        return zips[0]
    raise FileNotFoundError("Could not find BSE_2025_2026 source in Downloads")


def codes_from_phase1(source: Path) -> set[str]:
    if source.is_dir():
        names = [p.name for p in source.rglob("*.csv") if p.is_file()]
    else:
        with ZipFile(source) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    result = set()
    for name in names:
        m = CODE_RE.fullmatch(Path(name).name)
        if m:
            result.add(m.group("code"))
    return result


def read_direct(db: Path) -> list[dict]:
    if not db.is_file():
        raise FileNotFoundError(f"Direct DB missing: {db}")
    con = sqlite3.connect(str(db))
    try:
        rows = con.execute("""
            SELECT task_key,bse_code,from_date,to_date,status,attempts,rows,
                   output_file,sha256,error
            FROM tasks
            ORDER BY bse_code,from_date
        """).fetchall()
    finally:
        con.close()
    return [
        dict(
            task_key=r[0], bse_code=str(r[1]).zfill(6),
            from_date=r[2], to_date=r[3], status=r[4], attempts=r[5],
            rows=r[6], output_file=r[7], sha256=r[8], error=r[9],
        )
        for r in rows
    ]


def read_coverage(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Fallback coverage missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fallback_daily_summary(db: Path) -> dict[str, int]:
    if not db.is_file():
        raise FileNotFoundError(f"Fallback state DB missing: {db}")
    con = sqlite3.connect(str(db))
    try:
        rows = con.execute(
            "SELECT status,COUNT(*) FROM daily_files GROUP BY status"
        ).fetchall()
    finally:
        con.close()
    return {str(k): int(v) for k, v in rows}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Audit completion of the 228×4 BSE historical-price acquisition.")
    p.add_argument("--downloads-root", type=Path, default=DEFAULT_DOWNLOADS)
    p.add_argument("--direct-root", type=Path, default=DEFAULT_DIRECT_ROOT)
    p.add_argument("--fallback-root", type=Path, default=DEFAULT_FALLBACK_ROOT)
    p.add_argument(
        "--report-root",
        type=Path,
        default=DEFAULT_DOWNLOADS / "BSE_History_Final_Audit",
    )
    args = p.parse_args(argv)

    try:
        phase1 = discover_phase1(args.downloads_root)
        phase1_codes = codes_from_phase1(phase1)
        direct = read_direct(args.direct_root / "state" / "progress.sqlite")
        coverage = read_coverage(args.fallback_root / "reports" / "coverage.csv")
        daily = fallback_daily_summary(args.fallback_root / "state" / "bhavcopy.sqlite")

        errors: list[str] = []
        warnings: list[str] = []

        if len(phase1_codes) != 228:
            errors.append(f"Phase-1 exact code count is {len(phase1_codes)}, expected 228.")

        if len(direct) != 912:
            errors.append(f"Direct task count is {len(direct)}, expected 912.")

        direct_keys = {r["task_key"] for r in direct}
        if len(direct_keys) != len(direct):
            errors.append("Duplicate task_key exists in direct DB.")

        direct_codes = {r["bse_code"] for r in direct}
        if direct_codes != phase1_codes:
            errors.append(
                f"Direct-code universe differs from phase-1 universe "
                f"(direct={len(direct_codes)}, phase1={len(phase1_codes)})."
            )

        direct_ok = [r for r in direct if r["status"] == "DIRECT_OK"]
        needs = [r for r in direct if r["status"] == "NEEDS_BHAVCOPY_CHECK"]
        unexpected_direct = [
            r for r in direct
            if r["status"] not in {"DIRECT_OK", "NEEDS_BHAVCOPY_CHECK"}
        ]

        if unexpected_direct:
            errors.append(
                f"{len(unexpected_direct)} direct tasks have unexpected/nonterminal statuses."
            )

        # Verify every DIRECT_OK file is still present and matches its stored digest.
        bad_direct_files = []
        for r in direct_ok:
            op = r["output_file"]
            if not op:
                bad_direct_files.append((r["task_key"], "missing output_file"))
                continue
            fp = Path(op)
            if not fp.is_file():
                bad_direct_files.append((r["task_key"], f"file missing: {fp}"))
                continue
            if r["sha256"]:
                actual = sha256(fp)
                if actual.lower() != str(r["sha256"]).lower():
                    bad_direct_files.append((r["task_key"], "SHA256 mismatch"))
        if bad_direct_files:
            errors.append(f"{len(bad_direct_files)} DIRECT_OK files failed existence/hash audit.")

        cov_by_key = {r["task_key"]: r for r in coverage}
        if len(cov_by_key) != len(coverage):
            errors.append("Duplicate task_key exists in fallback coverage report.")

        needs_keys = {r["task_key"] for r in needs}
        cov_keys = set(cov_by_key)

        missing_cov = needs_keys - cov_keys
        extra_cov = cov_keys - needs_keys
        if missing_cov:
            errors.append(f"{len(missing_cov)} NEEDS_BHAVCOPY_CHECK tasks are absent from fallback coverage.")
        if extra_cov:
            errors.append(f"{len(extra_cov)} fallback coverage rows do not belong to unresolved direct tasks.")

        fallback_counts: dict[str, int] = {}
        for r in coverage:
            result = r.get("result", "")
            fallback_counts[result] = fallback_counts.get(result, 0) + 1

        bad_fallback_results = {
            k: v for k, v in fallback_counts.items()
            if k not in {"BHAVCOPY_RECOVERED", "NO_RECORD_CONFIRMED"}
        }
        if bad_fallback_results:
            errors.append(f"Nonterminal/problem fallback results exist: {bad_fallback_results}")

        bad_daily = {
            k: v for k, v in daily.items()
            if k not in {"OK", "NO_FILE"}
        }
        if bad_daily:
            errors.append(f"Bhavcopy daily-file errors remain: {bad_daily}")

        # Combined status for all 912.
        combined = []
        by_code: dict[str, dict[str, int]] = {
            c: {
                "DIRECT_OK": 0,
                "BHAVCOPY_RECOVERED": 0,
                "NO_RECORD_CONFIRMED": 0,
                "TOTAL_WINDOWS": 0,
            }
            for c in sorted(phase1_codes)
        }

        for r in direct:
            if r["status"] == "DIRECT_OK":
                final = "DIRECT_OK"
            else:
                cov = cov_by_key.get(r["task_key"])
                final = cov.get("result", "MISSING_FALLBACK") if cov else "MISSING_FALLBACK"

            combined.append({
                "task_key": r["task_key"],
                "bse_code": r["bse_code"],
                "from_date": r["from_date"],
                "to_date": r["to_date"],
                "direct_status": r["status"],
                "final_status": final,
                "direct_rows": r["rows"] if r["rows"] is not None else "",
            })
            if r["bse_code"] in by_code:
                by_code[r["bse_code"]]["TOTAL_WINDOWS"] += 1
                if final in by_code[r["bse_code"]]:
                    by_code[r["bse_code"]][final] += 1

        unresolved_final = [
            r for r in combined
            if r["final_status"] not in {
                "DIRECT_OK", "BHAVCOPY_RECOVERED", "NO_RECORD_CONFIRMED"
            }
        ]
        if unresolved_final:
            errors.append(f"{len(unresolved_final)} combined tasks remain unresolved.")

        report_root = args.report_root
        write_csv(
            report_root / "combined_912_status.csv",
            ["task_key","bse_code","from_date","to_date","direct_status","final_status","direct_rows"],
            combined,
        )

        code_rows = []
        for code, counts in sorted(by_code.items()):
            row = {"bse_code": code, **counts}
            row["DATA_WINDOWS"] = counts["DIRECT_OK"] + counts["BHAVCOPY_RECOVERED"]
            code_rows.append(row)

        write_csv(
            report_root / "per_code_coverage.csv",
            [
                "bse_code","TOTAL_WINDOWS","DATA_WINDOWS","DIRECT_OK",
                "BHAVCOPY_RECOVERED","NO_RECORD_CONFIRMED",
            ],
            code_rows,
        )

        final_counts: dict[str, int] = {}
        for r in combined:
            final_counts[r["final_status"]] = final_counts.get(r["final_status"], 0) + 1

        summary = {
            "phase1_exact_codes": len(phase1_codes),
            "direct_tasks": len(direct),
            "direct_statuses": {
                "DIRECT_OK": len(direct_ok),
                "NEEDS_BHAVCOPY_CHECK": len(needs),
            },
            "fallback_results": fallback_counts,
            "bhavcopy_daily_statuses": daily,
            "combined_final_statuses": final_counts,
            "combined_resolved_tasks": len(combined) - len(unresolved_final),
            "combined_total_tasks": len(combined),
            "direct_files_bad": len(bad_direct_files),
            "errors": errors,
            "warnings": warnings,
        }

        report_root.mkdir(parents=True, exist_ok=True)
        (report_root / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        print(json.dumps(summary, indent=2, sort_keys=True))
        print(f"Combined status: {report_root / 'combined_912_status.csv'}")
        print(f"Per-code coverage: {report_root / 'per_code_coverage.csv'}")
        print(f"Summary: {report_root / 'summary.json'}")

        if errors:
            print("AUDIT: FAIL")
            return 2

        print("AUDIT: PASS")
        return 0

    except Exception as exc:
        print(f"AUDIT FAILED TO RUN: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
