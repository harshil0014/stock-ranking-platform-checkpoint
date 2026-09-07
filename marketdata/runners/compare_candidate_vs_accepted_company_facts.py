from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys


HOME = Path.home()
PROJECT = HOME / "Downloads" / "stock-ranking-platform"
DEFAULT_ACCEPTED_ROOT = PROJECT / "data" / "company_facts"
DEFAULT_CANDIDATE = PROJECT / "data" / "company_facts_candidate_bse_20260907" / "company_facts.csv"
DEFAULT_OUTPUT = PROJECT / "data" / "company_facts_candidate_bse_20260907" / "comparison_vs_accepted"


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def truthy(v) -> bool:
    return str(v or "").strip().lower() in {"true", "1", "yes"}


def recursive_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for x in value.values():
            yield from recursive_strings(x)
    elif isinstance(value, list):
        for x in value:
            yield from recursive_strings(x)


def resolve_accepted_facts(root: Path) -> Path:
    pointer = root / "accepted_state.json"
    if pointer.is_file():
        state = json.loads(pointer.read_text(encoding="utf-8"))
        candidates = []
        # Common pointer keys used by this project.
        for key in ("accepted_batch", "bundle_path", "snapshot_path", "path"):
            value = state.get(key)
            if isinstance(value, str) and value.strip():
                p = (root / value).resolve()
                candidates += [p, p / "company_facts.csv"]
        # Generic fallback for any relative path stored in pointer.
        for value in recursive_strings(state):
            p = (root / value).resolve()
            candidates += [p, p / "company_facts.csv"]
        for p in candidates:
            if p.is_file() and p.name == "company_facts.csv":
                return p
            if p.is_dir() and (p / "company_facts.csv").is_file():
                return p / "company_facts.csv"

    # Fallback to most recent snapshot-like file.
    files = list(root.glob("snapshots/**/company_facts.csv"))
    files += list(root.glob("**/company_facts.csv"))
    files = [p for p in files if "candidate_bse_20260907" not in str(p)]
    if files:
        return max(files, key=lambda p: p.stat().st_mtime)

    raise FileNotFoundError(f"Could not resolve accepted company_facts.csv under {root}")


def unique_by_isin(rows: list[dict], label: str) -> dict[str, dict]:
    out = {}
    for r in rows:
        isin = str(r.get("isin", "")).strip().upper()
        if not isin:
            raise ValueError(f"{label}: blank ISIN")
        if isin in out:
            raise ValueError(f"{label}: duplicate ISIN {isin}")
        out[isin] = r
    return out


def counts(rows: list[dict]) -> dict:
    def n(pred):
        return sum(1 for r in rows if pred(r))

    return {
        "rows": len(rows),
        "history_accepted": n(lambda r: str(r.get("history_status", "")) == "ACCEPTED_ADJUSTED_HISTORY"),
        "history_1y_usable": n(lambda r: truthy(r.get("history_1y_usable"))),
        "history_3y_usable": n(lambda r: truthy(r.get("history_3y_usable"))),
        "history_5y_usable": n(lambda r: truthy(r.get("history_5y_usable"))),
        "product_classified": n(
            lambda r: str(r.get("product_classification_evidence", "")) != "UNCLASSIFIED"
        ),
        "product_baseline_eligible": n(lambda r: truthy(r.get("product_baseline_eligible"))),
    }


def by_exchange(rows: list[dict]) -> dict:
    result = {}
    exchanges = sorted({str(r.get("primary_exchange", "")).strip().upper() for r in rows})
    for ex in exchanges:
        result[ex or "<blank>"] = counts([
            r for r in rows
            if str(r.get("primary_exchange", "")).strip().upper() == ex
        ])
    return result


def reason_counts(rows: list[dict]) -> dict[str, int]:
    out = {}
    for r in rows:
        reason = str(r.get("product_baseline_reason_code", "")).strip() or "<blank>"
        out[reason] = out.get(reason, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Compare isolated candidate company facts against the currently accepted company-fact snapshot by exact ISIN."
    )
    p.add_argument("--accepted-root", type=Path, default=DEFAULT_ACCEPTED_ROOT)
    p.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = p.parse_args(argv)

    try:
        accepted_path = resolve_accepted_facts(args.accepted_root.resolve())
        candidate_path = args.candidate.resolve()

        accepted_rows = read_csv(accepted_path)
        candidate_rows = read_csv(candidate_path)

        accepted = unique_by_isin(accepted_rows, "accepted")
        candidate = unique_by_isin(candidate_rows, "candidate")

        common = sorted(set(accepted) & set(candidate))
        added = sorted(set(candidate) - set(accepted))
        removed = sorted(set(accepted) - set(candidate))

        transitions = {
            "eligible_to_eligible": 0,
            "eligible_to_ineligible": 0,
            "ineligible_to_eligible": 0,
            "ineligible_to_ineligible": 0,
        }
        lost = []
        gained = []

        for isin in common:
            a = accepted[isin]
            c = candidate[isin]
            ae = truthy(a.get("product_baseline_eligible"))
            ce = truthy(c.get("product_baseline_eligible"))

            if ae and ce:
                transitions["eligible_to_eligible"] += 1
            elif ae and not ce:
                transitions["eligible_to_ineligible"] += 1
                lost.append({
                    "isin": isin,
                    "accepted_ticker": a.get("ticker", ""),
                    "candidate_ticker": c.get("ticker", ""),
                    "accepted_exchange": a.get("primary_exchange", ""),
                    "candidate_exchange": c.get("primary_exchange", ""),
                    "accepted_reason": a.get("product_baseline_reason_code", ""),
                    "candidate_reason": c.get("product_baseline_reason_code", ""),
                    "candidate_reason_text": c.get("product_baseline_reason", ""),
                    "accepted_history_status": a.get("history_status", ""),
                    "candidate_history_status": c.get("history_status", ""),
                    "accepted_history_end": a.get("history_end_date", ""),
                    "candidate_history_end": c.get("history_end_date", ""),
                })
            elif not ae and ce:
                transitions["ineligible_to_eligible"] += 1
                gained.append({
                    "isin": isin,
                    "accepted_ticker": a.get("ticker", ""),
                    "candidate_ticker": c.get("ticker", ""),
                    "accepted_exchange": a.get("primary_exchange", ""),
                    "candidate_exchange": c.get("primary_exchange", ""),
                    "accepted_reason": a.get("product_baseline_reason_code", ""),
                    "candidate_reason": c.get("product_baseline_reason_code", ""),
                    "accepted_history_status": a.get("history_status", ""),
                    "candidate_history_status": c.get("history_status", ""),
                })
            else:
                transitions["ineligible_to_ineligible"] += 1

        added_eligible = [candidate[i] for i in added if truthy(candidate[i].get("product_baseline_eligible"))]
        removed_eligible = [accepted[i] for i in removed if truthy(accepted[i].get("product_baseline_eligible"))]

        summary = {
            "accepted_path": str(accepted_path),
            "candidate_path": str(candidate_path),
            "accepted": {
                **counts(accepted_rows),
                "by_exchange": by_exchange(accepted_rows),
            },
            "candidate": {
                **counts(candidate_rows),
                "by_exchange": by_exchange(candidate_rows),
            },
            "identity_overlap": {
                "common_isins": len(common),
                "new_candidate_isins": len(added),
                "removed_accepted_isins": len(removed),
            },
            "common_identity_transitions": transitions,
            "new_candidate_eligible": len(added_eligible),
            "removed_accepted_eligible": len(removed_eligible),
            "lost_eligibility_candidate_reasons": reason_counts([
                candidate[r["isin"]] for r in lost
            ]),
            "gained_eligibility_previous_reasons": reason_counts([
                accepted[r["isin"]] for r in gained
            ]),
        }

        output = args.output_root.resolve()
        output.mkdir(parents=True, exist_ok=True)
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        loss_fields = [
            "isin", "accepted_ticker", "candidate_ticker",
            "accepted_exchange", "candidate_exchange",
            "accepted_reason", "candidate_reason", "candidate_reason_text",
            "accepted_history_status", "candidate_history_status",
            "accepted_history_end", "candidate_history_end",
        ]
        gain_fields = [
            "isin", "accepted_ticker", "candidate_ticker",
            "accepted_exchange", "candidate_exchange",
            "accepted_reason", "candidate_reason",
            "accepted_history_status", "candidate_history_status",
        ]
        write_csv(output / "eligibility_losses.csv", lost, loss_fields)
        write_csv(output / "eligibility_gains.csv", gained, gain_fields)

        print(json.dumps(summary, indent=2, sort_keys=True))
        print(f"Losses: {output / 'eligibility_losses.csv'}")
        print(f"Gains: {output / 'eligibility_gains.csv'}")
        print(f"Summary: {output / 'summary.json'}")
        print("CANDIDATE VS ACCEPTED COMPARISON: PASS")
        print("No accepted state was modified.")
        return 0

    except Exception as exc:
        print(
            f"CANDIDATE VS ACCEPTED COMPARISON FAILED: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
