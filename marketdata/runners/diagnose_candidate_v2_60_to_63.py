from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

PROJECT = Path.home() / "Downloads" / "stock-ranking-platform"

ACCEPTED_LIVE = PROJECT / "data/live_market/snapshots/2026-09-07-4565a7d0b547bbdd09ad7560b659e9dbf50970b18b8da9bfdc93c43a85911ece"
CANDIDATE_LIVE = PROJECT / "data/live_market/candidate_bse_20260907_refreshed"
CANDIDATE_HISTORY = PROJECT / "data/live_market/history_cache_candidate_bse_price_return_20260907"
OUTPUT = PROJECT / "data/diagnostics/candidate_v2_60_to_63_20260907"


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def truthy(v) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes"}


def by_isin(rows: list[dict]) -> dict[str, dict]:
    out = {}
    for r in rows:
        isin = str(r.get("isin", "")).strip().upper()
        if not isin:
            continue
        if isin in out:
            raise ValueError(f"duplicate ISIN {isin}")
        out[isin] = r
    return out


def hist_summary(ticker: str) -> dict:
    p = CANDIDATE_HISTORY / f"{ticker}.csv"
    if not p.is_file():
        return {"exists": False}
    rows = read_csv(p)
    if not rows:
        return {"exists": True, "rows": 0}
    return {
        "exists": True,
        "rows": len(rows),
        "first_date": rows[0].get("date"),
        "last_date": rows[-1].get("date"),
        "last_adjusted_close": rows[-1].get("adjusted_close"),
        "last_raw_close": rows[-1].get("raw_close"),
    }


def pick(r: dict) -> dict:
    keys = [
        "ticker", "company", "isin", "primary_exchange", "trade_date", "latest_price",
        "v2_eligible", "v2_reason_code", "research_v2_score", "research_v2_sector_rank",
        "roce", "debt_to_equity", "profit_growth_yoy",
    ]
    return {k: r.get(k, "") for k in keys if k in r}


def main() -> int:
    try:
        accepted_manifest = json.loads(
            (ACCEPTED_LIVE / "bundle_manifest.json").read_text(encoding="utf-8")
        )
        candidate_manifest = json.loads(
            (CANDIDATE_LIVE / "bundle_manifest.json").read_text(encoding="utf-8")
        )

        accepted_rows = read_csv(ACCEPTED_LIVE / "live_market.csv")
        candidate_rows = read_csv(CANDIDATE_LIVE / "live_market.csv")

        accepted = by_isin(accepted_rows)
        candidate = by_isin(candidate_rows)

        accepted_v2 = {isin for isin, r in accepted.items() if truthy(r.get("v2_eligible"))}
        candidate_v2 = {isin for isin, r in candidate.items() if truthy(r.get("v2_eligible"))}

        gained = sorted(candidate_v2 - accepted_v2)
        lost = sorted(accepted_v2 - candidate_v2)

        detail = []
        for isin in sorted(set(gained) | set(lost)):
            a = accepted.get(isin, {})
            c = candidate.get(isin, {})
            ticker = str(c.get("ticker") or a.get("ticker") or "").strip()
            detail.append({
                "isin": isin,
                "transition": "GAINED" if isin in gained else "LOST",
                "accepted": pick(a),
                "candidate": pick(c),
                "candidate_history": hist_summary(ticker) if ticker else {},
            })

        summary = {
            "accepted_v2_count_manifest": accepted_manifest.get("research_v2_eligible_count"),
            "accepted_v2_count_rows": len(accepted_v2),
            "candidate_v2_count_manifest": candidate_manifest.get("research_v2_eligible_count"),
            "candidate_v2_count_rows": len(candidate_v2),
            "gained_isins": gained,
            "lost_isins": lost,
            "accepted_frozen_evidence_fingerprint": accepted_manifest.get(
                "research_v2_frozen_evidence_fingerprint"
            ),
            "candidate_frozen_evidence_fingerprint": candidate_manifest.get(
                "research_v2_frozen_evidence_fingerprint"
            ),
            "frozen_evidence_unchanged": accepted_manifest.get(
                "research_v2_frozen_evidence_fingerprint"
            ) == candidate_manifest.get("research_v2_frozen_evidence_fingerprint"),
            "accepted_current_additions_fingerprint": accepted_manifest.get(
                "research_v2_current_additions_fingerprint"
            ),
            "candidate_current_additions_fingerprint": candidate_manifest.get(
                "research_v2_current_additions_fingerprint"
            ),
            "current_additions_unchanged": accepted_manifest.get(
                "research_v2_current_additions_fingerprint"
            ) == candidate_manifest.get("research_v2_current_additions_fingerprint"),
        }

        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )
        (OUTPUT / "details.json").write_text(
            json.dumps(detail, indent=2, sort_keys=True), encoding="utf-8"
        )

        print(json.dumps(summary, indent=2, sort_keys=True))
        print("\nDETAILS")
        print(json.dumps(detail, indent=2, sort_keys=True))
        print(f"\nSaved: {OUTPUT}")
        print("CANDIDATE V2 60-to-63 DIAGNOSTIC: PASS")
        print("No data or tests were modified.")
        return 0

    except Exception as exc:
        print(
            f"CANDIDATE V2 60-to-63 DIAGNOSTIC FAILED: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
