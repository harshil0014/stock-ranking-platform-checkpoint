from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import statistics
import sys

HOME = Path.home()
PROJECT = HOME / "Downloads" / "stock-ranking-platform"

PROMOTED = PROJECT / "data/live_market/bse_candidate_history_integration_20260907/promoted_codes.csv"
CANDIDATE_CACHE = PROJECT / "data/live_market/history_cache_candidate_bse_20260907"
REFERENCE_CACHE = PROJECT / "data/live_market/history_cache"
ACTIONS = HOME / "Downloads/BSE_Adjustment_Readiness/action_readiness.csv"
OUTPUT = PROJECT / "data/live_market/bse_adjustment_semantics_audit_20260907"


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fnum(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - pos) + xs[hi] * (pos - lo)


def load_history(path: Path) -> dict[str, dict]:
    rows = read_csv(path)
    out = {}
    for r in rows:
        d = str(r.get("date", "")).strip()
        if not d:
            continue
        raw = fnum(r.get("raw_close"))
        adj = fnum(r.get("adjusted_close"))
        if adj is None or adj <= 0:
            continue
        out[d] = {"raw_close": raw, "adjusted_close": adj}
    return out


def action_return_gap(candidate: dict, reference: dict, ex_date: str) -> float | None:
    common = sorted(set(candidate) & set(reference))
    if len(common) < 2:
        return None
    before = [d for d in common if d < ex_date]
    after = [d for d in common if d >= ex_date]
    if not before or not after:
        return None
    d0 = before[-1]
    d1 = after[0]
    # Do not compare across a large unrelated gap.
    from datetime import date
    if (date.fromisoformat(d1) - date.fromisoformat(d0)).days > 10:
        return None
    c0 = candidate[d0]["adjusted_close"]
    c1 = candidate[d1]["adjusted_close"]
    r0 = reference[d0]["adjusted_close"]
    r1 = reference[d1]["adjusted_close"]
    if min(c0, c1, r0, r1) <= 0:
        return None
    return abs((c1 / c0 - 1.0) - (r1 / r0 - 1.0))


def main() -> int:
    try:
        promoted = read_csv(PROMOTED)
        adjusted_promoted = [
            r for r in promoted if int(float(str(r.get("actions_applied") or "0"))) > 0
        ]
        adjusted_codes = {str(r["bse_code"]).strip().zfill(6) for r in adjusted_promoted}

        action_rows = read_csv(ACTIONS)
        ready_actions = []
        for r in action_rows:
            code = str(r.get("bse_code", "")).strip().zfill(6)
            if code not in adjusted_codes:
                continue
            if str(r.get("adjustment_readiness", "")).strip() != "READY":
                continue
            factor = fnum(r.get("candidate_backward_factor"))
            if factor is None or factor <= 0:
                continue
            ready_actions.append(r)

        actions_by_code: dict[str, list[dict]] = {}
        by_event_type: dict[str, int] = {}
        for r in ready_actions:
            code = str(r["bse_code"]).strip().zfill(6)
            actions_by_code.setdefault(code, []).append(r)
            et = str(r.get("event_type", "")).strip() or "<blank>"
            by_event_type[et] = by_event_type.get(et, 0) + 1

        mechanical_errors = []
        detail = []
        classification_counts: dict[str, int] = {}

        expected_actions = sum(int(float(str(r.get("actions_applied") or "0"))) for r in adjusted_promoted)
        if expected_actions != len(ready_actions):
            mechanical_errors.append(
                f"promoted report says {expected_actions} actions applied but "
                f"{len(ready_actions)} READY action rows were resolved"
            )

        reference_files = 0
        reference_ge_100 = 0
        all_action_gaps = []

        for p in sorted(adjusted_promoted, key=lambda r: str(r["bse_code"])):
            code = str(p["bse_code"]).strip().zfill(6)
            ticker = str(p["ticker"]).strip()
            cand_path = CANDIDATE_CACHE / f"{ticker}.csv"
            ref_path = REFERENCE_CACHE / f"{ticker}.csv"

            if not cand_path.is_file():
                mechanical_errors.append(f"{ticker}: candidate history missing")
                continue

            cand = load_history(cand_path)
            ref_exists = ref_path.is_file()
            ref = load_history(ref_path) if ref_exists else {}
            reference_files += int(ref_exists)

            common = sorted(set(cand) & set(ref))
            if len(common) >= 100:
                reference_ge_100 += 1

            median_norm_error = None
            p95_norm_error = None
            max_norm_error = None
            raw_median_gap = None

            if common:
                anchor = common[-1]
                ca = cand[anchor]["adjusted_close"]
                ra = ref[anchor]["adjusted_close"]
                norm_errors = []
                raw_gaps = []
                if ca > 0 and ra > 0:
                    for d in common:
                        cn = cand[d]["adjusted_close"] / ca
                        rn = ref[d]["adjusted_close"] / ra
                        if rn > 0:
                            norm_errors.append(abs(cn - rn) / rn)
                        cr = cand[d].get("raw_close")
                        rr = ref[d].get("raw_close")
                        if cr and rr and cr > 0 and rr > 0:
                            raw_gaps.append(abs(cr - rr) / rr)
                median_norm_error = percentile(norm_errors, 0.50)
                p95_norm_error = percentile(norm_errors, 0.95)
                max_norm_error = max(norm_errors) if norm_errors else None
                raw_median_gap = percentile(raw_gaps, 0.50)

            action_gaps = []
            for a in actions_by_code.get(code, []):
                ex = str(a.get("ex_date_iso", "")).strip()
                gap = action_return_gap(cand, ref, ex) if ref else None
                if gap is not None:
                    action_gaps.append(gap)
                    all_action_gaps.append(gap)

            max_action_gap = max(action_gaps) if action_gaps else None

            if not ref_exists:
                cls = "NO_YAHOO_REFERENCE"
            elif len(common) < 100:
                cls = "INSUFFICIENT_OVERLAP"
            elif p95_norm_error is not None and p95_norm_error <= 0.02 and (
                max_action_gap is None or max_action_gap <= 0.03
            ):
                cls = "REFERENCE_MATCH"
            elif p95_norm_error is not None and p95_norm_error <= 0.05 and (
                max_action_gap is None or max_action_gap <= 0.05
            ):
                cls = "CLOSE_REVIEW"
            else:
                cls = "SEMANTIC_REVIEW_REQUIRED"

            classification_counts[cls] = classification_counts.get(cls, 0) + 1

            detail.append({
                "bse_code": code,
                "ticker": ticker,
                "actions_applied": int(float(str(p.get("actions_applied") or "0"))),
                "event_types": ";".join(sorted({
                    str(a.get("event_type", "")).strip()
                    for a in actions_by_code.get(code, [])
                })),
                "yahoo_reference_exists": ref_exists,
                "overlap_rows": len(common),
                "median_normalized_adjusted_error": median_norm_error,
                "p95_normalized_adjusted_error": p95_norm_error,
                "max_normalized_adjusted_error": max_norm_error,
                "median_raw_close_gap": raw_median_gap,
                "action_return_comparisons": len(action_gaps),
                "max_action_return_gap": max_action_gap,
                "classification": cls,
            })

        summary = {
            "promoted_codes_total": len(promoted),
            "promoted_codes_with_adjustments": len(adjusted_promoted),
            "action_factors_reported_applied": expected_actions,
            "ready_action_rows_resolved": len(ready_actions),
            "ready_action_event_types": dict(sorted(by_event_type.items())),
            "yahoo_reference_files_available": reference_files,
            "yahoo_reference_codes_with_at_least_100_overlap_rows": reference_ge_100,
            "reference_classifications": dict(sorted(classification_counts.items())),
            "action_return_gap_median": percentile(all_action_gaps, 0.50),
            "action_return_gap_p95": percentile(all_action_gaps, 0.95),
            "action_return_gap_max": max(all_action_gaps) if all_action_gaps else None,
            "mechanical_errors": mechanical_errors,
            "policy_note": (
                "This audit does not auto-promote. It checks whether the official-BSE "
                "backward-adjusted histories agree with any pre-existing Yahoo-adjusted "
                "reference on overlapping dates. NO_YAHOO_REFERENCE requires separate "
                "validation before production promotion."
            ),
        }

        OUTPUT.mkdir(parents=True, exist_ok=True)
        with (OUTPUT / "per_code_semantics.csv").open("w", encoding="utf-8", newline="") as f:
            fields = list(detail[0].keys()) if detail else [
                "bse_code","ticker","actions_applied","event_types",
                "yahoo_reference_exists","overlap_rows",
                "median_normalized_adjusted_error","p95_normalized_adjusted_error",
                "max_normalized_adjusted_error","median_raw_close_gap",
                "action_return_comparisons","max_action_return_gap","classification",
            ]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(detail)

        (OUTPUT / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        print(json.dumps(summary, indent=2, sort_keys=True))
        print(f"Per-code report: {OUTPUT / 'per_code_semantics.csv'}")
        if mechanical_errors:
            print("BSE ADJUSTMENT SEMANTICS AUDIT: FAIL")
            return 2
        print("BSE ADJUSTMENT SEMANTICS AUDIT: PASS")
        print("No accepted or candidate data was modified.")
        return 0

    except Exception as exc:
        print(
            f"BSE ADJUSTMENT SEMANTICS AUDIT FAILED TO RUN: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
