from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys

HOME = Path.home()
PROJECT = HOME / "Downloads" / "stock-ranking-platform"

DEFAULT_CANDIDATE_FACTS = PROJECT / "data/company_facts_candidate_bse_20260907_refreshed/company_facts.csv"
DEFAULT_LOSSES = PROJECT / "data/company_facts_candidate_bse_20260907_refreshed/comparison_vs_accepted/eligibility_losses.csv"
DEFAULT_HISTORY = PROJECT / "data/live_market/history_cache_candidate_bse_20260907"
DEFAULT_PROMOTED = PROJECT / "data/live_market/bse_candidate_history_integration_20260907/promoted_codes.csv"
DEFAULT_BLOCKED = PROJECT / "data/live_market/bse_candidate_history_integration_20260907/blocked_current_codes.csv"
DEFAULT_ACCEPTED_STATE = PROJECT / "data/company_facts/accepted_state.json"
DEFAULT_OUTPUT = PROJECT / "data/company_facts_candidate_bse_20260907_refreshed/loss_diagnostic"


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_state(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def fnum(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Diagnose exact causes of Product Baseline eligibility losses.")
    p.add_argument("--candidate-facts", type=Path, default=DEFAULT_CANDIDATE_FACTS)
    p.add_argument("--losses", type=Path, default=DEFAULT_LOSSES)
    p.add_argument("--history-root", type=Path, default=DEFAULT_HISTORY)
    p.add_argument("--promoted", type=Path, default=DEFAULT_PROMOTED)
    p.add_argument("--blocked", type=Path, default=DEFAULT_BLOCKED)
    p.add_argument("--accepted-state", type=Path, default=DEFAULT_ACCEPTED_STATE)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = p.parse_args(argv)

    try:
        facts = read_csv(args.candidate_facts.resolve())
        losses = read_csv(args.losses.resolve())
        facts_by_isin = {str(r["isin"]).strip().upper(): r for r in facts}

        promoted = set()
        if args.promoted.is_file():
            promoted = {str(r["ticker"]).strip() for r in read_csv(args.promoted)}
        blocked = set()
        if args.blocked.is_file():
            blocked = {str(r["ticker"]).strip() for r in read_csv(args.blocked)}

        rows = []
        reason_counts = {}
        exchange_counts = {}
        source_counts = {}
        promoted_losses = 0
        blocked_losses = 0
        terminal_missing = 0

        for loss in losses:
            isin = str(loss["isin"]).strip().upper()
            fact = facts_by_isin[isin]
            ticker = str(fact["ticker"]).strip()
            reason = str(fact.get("product_baseline_reason_code", "")).strip()
            exchange = str(fact.get("primary_exchange", "")).strip()
            source = str(fact.get("snapshot_source", "")).strip()

            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            exchange_counts[exchange] = exchange_counts.get(exchange, 0) + 1
            source_counts[source] = source_counts.get(source, 0) + 1

            hist_path = args.history_root.resolve() / f"{ticker}.csv"
            hist_last_date = ""
            hist_raw = None
            hist_adj = None
            if hist_path.is_file():
                h = read_csv(hist_path)
                if h:
                    last = h[-1]
                    hist_last_date = str(last.get("date", "")).strip()
                    hist_raw = fnum(last.get("raw_close"))
                    hist_adj = fnum(last.get("adjusted_close"))
            else:
                terminal_missing += 1

            current = fnum(fact.get("latest_price"))
            rel_raw = None
            rel_adj = None
            if current and current > 0 and hist_raw is not None:
                rel_raw = abs(hist_raw - current) / current
            if current and current > 0 and hist_adj is not None:
                rel_adj = abs(hist_adj - current) / current

            is_promoted = ticker in promoted
            is_blocked = ticker in blocked
            promoted_losses += int(is_promoted)
            blocked_losses += int(is_blocked)

            rows.append({
                "isin": isin,
                "ticker": ticker,
                "exchange": exchange,
                "reason": reason,
                "snapshot_source": source,
                "latest_price": current,
                "history_last_date": hist_last_date,
                "history_terminal_raw": hist_raw,
                "history_terminal_adjusted": hist_adj,
                "relative_raw_gap": rel_raw,
                "relative_adjusted_gap": rel_adj,
                "official_bse_promoted_history": is_promoted,
                "blocked_bse_code": is_blocked,
            })

        mismatch_rows = [r for r in rows if r["reason"] == "CURRENT_PRICE_MISMATCH"]
        gap_buckets = {
            "2_to_5pct": 0,
            "5_to_10pct": 0,
            "10_to_25pct": 0,
            "25pct_plus": 0,
            "no_terminal_value": 0,
        }
        for r in mismatch_rows:
            gap = r["relative_adjusted_gap"]
            if gap is None:
                gap_buckets["no_terminal_value"] += 1
            elif gap < 0.05:
                gap_buckets["2_to_5pct"] += 1
            elif gap < 0.10:
                gap_buckets["5_to_10pct"] += 1
            elif gap < 0.25:
                gap_buckets["10_to_25pct"] += 1
            else:
                gap_buckets["25pct_plus"] += 1

        state = load_state(args.accepted_state.resolve())

        summary = {
            "loss_rows": len(rows),
            "reason_counts": dict(sorted(reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
            "exchange_counts": dict(sorted(exchange_counts.items())),
            "snapshot_source_counts": dict(sorted(source_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
            "current_price_mismatch_gap_buckets": gap_buckets,
            "official_bse_promoted_histories_among_losses": promoted_losses,
            "blocked_bse_histories_among_losses": blocked_losses,
            "missing_history_files_among_losses": terminal_missing,
            "accepted_state_exists": state is not None,
            "accepted_state": state,
        }

        outroot = args.output_root.resolve()
        outroot.mkdir(parents=True, exist_ok=True)
        with (outroot / "losses_detailed.csv").open("w", encoding="utf-8", newline="") as f:
            fields = list(rows[0].keys()) if rows else [
                "isin","ticker","exchange","reason","snapshot_source","latest_price",
                "history_last_date","history_terminal_raw","history_terminal_adjusted",
                "relative_raw_gap","relative_adjusted_gap",
                "official_bse_promoted_history","blocked_bse_code"
            ]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

        (outroot / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

        print(json.dumps(summary, indent=2, sort_keys=True))
        print(f"Detailed losses: {outroot / 'losses_detailed.csv'}")
        print("PRODUCT BASELINE LOSS DIAGNOSTIC: PASS")
        print("No accepted or candidate state was modified.")
        return 0

    except Exception as exc:
        print(f"PRODUCT BASELINE LOSS DIAGNOSTIC FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
