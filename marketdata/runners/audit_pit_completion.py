"""Read-only accepted-evidence PIT audit; writes only a fresh diagnostic directory.

No acquisition, ratio derivation, eligibility modification or state promotion.
Concept-name hits and clock matches are leads, never accounting acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, time, timedelta, timezone
import hashlib
import json
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f)


def clock_before_cutoff(value, cutoff):
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.tzinfo is not None and stamp <= cutoff
    except (ValueError, AttributeError):
        return False


def write_csv(path, items, fields):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(items)


def audit(root: Path, output: Path):
    if output.exists():
        raise ValueError("audit output must be fresh")
    protected = {}
    def track(path):
        protected[str(path.relative_to(root)).replace("\\", "/")] = digest(path)
        return path
    def read_json(path):
        return json.loads(track(path).read_text(encoding="utf-8"))

    base = root / "data/company_facts"
    state = read_json(base / "accepted_state.json")
    snapshot = base / state["snapshot_path"]
    for p in sorted(snapshot.rglob("*")):
        if p.is_file():
            track(p)
    companies = list(rows(snapshot / "company_facts.csv"))
    isins = {r["isin"] for r in companies if r["isin"]}
    cutoff = datetime.combine(datetime.fromisoformat(state["trade_date"]).date(), time(15, 30),
                              tzinfo=timezone(timedelta(hours=5, minutes=30)))
    provider = base / "providers/official_exchange"
    official_state = read_json(provider / "accepted_state.json")
    accepted = provider / official_state["accepted_batch"]
    evidence = defaultdict(Counter)
    source_concepts = Counter()
    row_count = 0
    clock_index = set()
    for r in rows(track(accepted / "financial_facts.csv")):
        row_count += 1
        source_concepts[r["source_concept"]] += 1
        isin = r["isin"]
        if isin not in isins:
            continue
        evidence[isin]["official_rows"] += 1
        if not clock_before_cutoff(r["available_at"], cutoff):
            continue
        if r["source_sha256"]:
            clock_index.add((isin, r["source_sha256"]))
        if r["statement_basis"] == "STANDALONE":
            evidence[isin]["standalone_clocked_rows"] += 1
            if r["canonical_concept"] == "pat":
                evidence[isin]["standalone_pat_rows"] += 1
            concept = r["source_concept"].lower().replace("_", "")
            if "capitalemployed" in concept or concept == "roce":
                evidence[isin]["roce_concept_leads"] += 1
            if concept in {"debtequityratio", "debttoequityratio"}:
                evidence[isin]["debt_equity_concept_leads"] += 1
    for r in rows(track(accepted / "documents.csv")):
        if r["isin"] in isins and r["source_sha256"] and clock_before_cutoff(r["available_at"], cutoff):
            clock_index.add((r["isin"], r["source_sha256"]))

    recovery = root / "data/recovery_packs/official_financial_tail_20260908"
    manual = read_json(recovery / "manual_latest.json")
    manual_rows = list(rows(track(recovery / manual["batch"] / "manual_current_reference_facts.csv")))
    clock_matches = []
    for r in manual_rows:
        evidence[r["isin"]]["manual_current_reference_rows"] += 1
        matched = (r["isin"], r["source_sha256"]) in clock_index
        if matched:
            evidence[r["isin"]]["manual_exact_hash_clock_leads"] += 1
        clock_matches.append({k: r[k] for k in ("ticker", "isin", "source_sha256", "canonical_concept", "period_end")} | {
            "exact_official_hash_clock_match": matched,
            "status": "REQUIRES_ACCOUNTING_AND_REVISION_REVIEW" if matched else "NO_EXACT_OFFICIAL_DOCUMENT_CLOCK",
        })
    spec = read_json(root / "marketdata/specifications/pit_independently_validated_additions_v1.json")
    adjudication = read_json(root / "marketdata/specifications/pit_near_complete_adjudication_v1.json")
    by_ticker = {r["ticker"]: r for r in adjudication["records"]}
    exclusions = {r["ticker"]: r["reason_code"] for r in spec.get("reviewed_exclusions", [])}
    promoted = {r["ticker"] for r in spec["records"]}
    deep = read_json(root / "data/marketdata/pit-accounting-pdfium-deep-safe-final-179-20260829/pdfium_validation_records.json")
    reviews = []
    for r in deep:
        ticker = r["ticker"]
        resolution = by_ticker.get(ticker, {}).get("resolution", exclusions.get(ticker, ""))
        reviews.append({"ticker": ticker, "isin": r["isin"], "source_sha256": r["pdf_sha256"],
                        "already_promoted": ticker in promoted, "latest_adjudication": resolution,
                        "field_status": json.dumps(r["field_status"], sort_keys=True),
                        "status": "ALREADY_ACCEPTED" if ticker in promoted else "NOT_CLEARED_FOR_PROMOTION"})
    residual = []
    for r in sorted(companies, key=lambda x: (x["isin"], x["ticker"])):
        e = evidence[r["isin"]]
        residual.append({"ticker": r["ticker"], "isin": r["isin"], "v2_reason_code": r["v2_reason_code"],
                         **{k: e[k] for k in ("official_rows", "standalone_clocked_rows", "standalone_pat_rows",
                            "roce_concept_leads", "debt_equity_concept_leads", "manual_current_reference_rows", "manual_exact_hash_clock_leads")}})
    # Protect frozen research contracts/results too; no regenerated rankings.
    for folder in ("experiments/walk_forward", "research/specifications", "research/manifests"):
        for p in sorted((root / folder).rglob("*")):
            if p.is_file():
                track(p)
    summary = {
        "scope": "Accepted local official backbone, current manual recovery and latest adjudicated annual-report evidence; not an exhaustive search of external filings",
        "accepted_company_fingerprint": state["fingerprint"], "market_fingerprint": state["market_fingerprint"],
        "cutoff": cutoff.isoformat(), "universe": len(companies),
        "v2_reason_counts": dict(sorted(Counter(r["v2_reason_code"] for r in companies).items())),
        "product_baseline_reason_counts": dict(sorted(Counter(r["product_baseline_reason_code"] for r in companies).items())),
        "official_fact_rows": row_count,
        "roce_concept_hits": {k: v for k, v in sorted(source_concepts.items()) if "capitalemployed" in k.lower().replace("_", "") or k.lower() == "roce"},
        "manual_reference_facts": len(manual_rows), "manual_reference_issuers": len({r["isin"] for r in manual_rows}),
        "manual_exact_hash_clock_leads": sum(r["exact_official_hash_clock_match"] for r in clock_matches),
        "reviewed_annual_reports": len(reviews), "reviewed_already_promoted": sum(r["already_promoted"] for r in reviews),
        "newly_accepted_facts": 0, "new_pit_additions": 0,
        "boundary": "No promotion. Concept hits do not certify ratios, periods, units, definitions, revisions, or accounting basis. Current/reference evidence is not PIT evidence.",
        "protected_file_sha256": dict(sorted(protected.items())),
    }
    for name, expected in protected.items():
        if digest(root / name) != expected:
            raise ValueError(f"input changed during audit: {name}")
    output.mkdir(parents=True)
    for name, items in (("issuer_pit_residual.csv", residual), ("manual_clock_reconciliation.csv", clock_matches), ("annual_report_reconciliation.csv", reviews)):
        write_csv(output / name, items, list(items[0]))
    (output / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "protected_file_sha256"}, sort_keys=True))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(Path(__file__).resolve().parents[2], args.output)
