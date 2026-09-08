"""Bounded residual probe; raw evidence only, never changes accepted pointers."""
from pathlib import Path
import sys
import json
import argparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from acquire_exchange_backbone import _bse_shareholding
from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_ranker.data_state import atomic_write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10:
        parser.error("limit must be 1 through 10")
    if args.output.exists():
        parser.error("fresh output directory required; existing evidence is preserved")
    snapshot = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts"))
    facts = snapshot.facts
    fields = ["promoter_holding_pct", "public_holding_pct", "screener_promoter_holding_pct", "screener_public_holding_pct"]
    residual = facts.loc[facts[fields].isna().all(axis=1) & facts.primary_exchange.eq("BSE")]
    holdings, documents, counts = _bse_shareholding(args.output, residual, args.limit, prioritize_professor=False)
    holdings.to_csv(args.output / "candidate_shareholding.csv", index=False, lineterminator="\n")
    documents.to_csv(args.output / "candidate_documents.csv", index=False, lineterminator="\n")
    report = {"counts": counts, "accepted": False, "snapshot": snapshot.manifest["fingerprint"],
              "reason": "Probe only; candidate filings require independent review before promotion."}
    atomic_write_json(args.output / "probe_report.json", report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
