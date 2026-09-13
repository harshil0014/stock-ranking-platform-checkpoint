"""Map offline Arelle review facts to existing concepts, WITHOUT acceptance/PIT."""
import argparse
from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from stock_ranker.exchange_backbone import CANONICAL_CONCEPTS, FINANCIAL_COLUMNS
from financial_recovery_pack import csv_bytes, sha, targets


def classify_period(start, end, instant):
    if instant:
        return "INSTANT"
    if not start or not end:
        return "UNKNOWN"
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days
    if days < 0:
        raise ValueError("invalid context duration")
    return "ANNUAL" if 350 <= days <= 380 else "QUARTERLY" if 75 <= days <= 105 else "YTD"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pack", type=Path, required=True)
    args = p.parse_args()
    pack = args.pack
    identities = {r["isin"]: r for r in targets(pack)}
    discovery = json.loads((pack / "financial_discovery_v2.json").read_text())
    mapping = {v: k for k, values in CANONICAL_CONCEPTS.items() for v in values}
    result = []
    for isin, entry in sorted(discovery.items()):
        for filing in entry["filings"]:
            source = pack / "arelle_review_v2" / (filing["sha256"] + ".json")
            if not source.is_file() or filing["status"].startswith("QUARANTINED"):
                continue
            parsed = json.loads(source.read_text(encoding="utf-8"))
            if parsed["isin"] != isin or parsed["source_sha256"] != filing["sha256"]:
                raise ValueError("review identity/hash conflict")
            if sha((pack / filing["path"]).read_bytes()) != parsed["source_sha256"]:
                raise ValueError("raw source hash mismatch")
            bases = parsed.get("identity_fields", {}).get("NatureOfReportStandaloneConsolidated", [])
            basis = bases[0].upper() if len(bases) == 1 else "UNKNOWN"
            for fact in parsed["facts"]:
                if not fact["period_end"]:
                    continue
                start, end = fact["period_start"], fact["period_end"]
                period_type = classify_period(start, end, fact["instant"])
                concept = fact["source_concept"].split(":")[-1]
                result.append({"ticker": identities[isin]["ticker"], "isin": isin, "exchange": identities[isin]["primary_exchange"],
                    "statement_basis": basis, "period_type": period_type, "period_start": start, "period_end": end,
                    "available_at": None, "filing_id": filing["url"].rsplit("/", 1)[-1],
                    "canonical_concept": mapping.get(concept, "unknown:" + concept), "source_concept": fact["source_concept"],
                    "value": fact["value"], "unit": json.dumps(fact["unit"], separators=(",", ":")),
                    "context_id": fact["context_id"], "source_url": filing["url"], "source_sha256": filing["sha256"],
                    "dimensions": json.dumps(fact["dimensions"], separators=(",", ":")),
                    "catalogue_created_at": filing["catalogue_row"].get("Fld_CreateDate"),
                    "validation_status": "REVIEW_ONLY_NOT_ACCEPTED", "clock_status": "DISSEMINATION_NOT_INDEPENDENTLY_VERIFIED"})
    body = csv_bytes(result, [*FINANCIAL_COLUMNS, "dimensions", "catalogue_created_at", "validation_status", "clock_status"])
    target = pack / "financial_review_facts.csv"
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(body)
    temporary.replace(target)
    print(json.dumps({"review_rows": len(result), "issuers": len({r["isin"] for r in result}), "sha256": sha(body), "accepted": 0}))


if __name__ == "__main__":
    main()
