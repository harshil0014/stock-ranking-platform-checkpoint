"""Audit recovery evidence and export precise review gaps; never promote facts."""
import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path

from financial_recovery_pack import atomic_write_json, csv_bytes, sha, targets


def audit(pack):
    identities = targets(pack)
    discovery = json.loads((pack / "financial_discovery_v2.json").read_text())
    ownership = json.loads((pack / "progress.json").read_text())
    inventory = json.loads((pack / "raw_inventory.json").read_text())
    for relative, expected in inventory.items():
        path = (pack / relative).resolve()
        if not path.is_relative_to(pack.resolve()):
            raise ValueError("inventory path escapes pack")
        if path.stat().st_size != expected["bytes"] or sha(path.read_bytes()) != expected["sha256"]:
            raise ValueError("raw inventory mismatch: " + relative)
    rows, canonical_facts = [], []
    filings = quarantined = empty = conflicts = 0
    for target in identities:
        entry = discovery.get(target["isin"], {})
        fact_count = source_count = conflict_count = empty_count = 0
        periods, bases = set(), set()
        for source in entry.get("filings", []):
            filings += 1
            if sha((pack / source["path"]).read_bytes()) != source["sha256"]:
                raise ValueError("filing hash mismatch")
            if source["status"].startswith("QUARANTINED"):
                quarantined += 1
                continue
            file = pack / "arelle_review_v2" / (source["sha256"] + ".json")
            parsed = json.loads(file.read_text(encoding="utf-8"))
            if parsed["isin"] != target["isin"] or parsed["source_sha256"] != source["sha256"] or parsed["accepted"]:
                raise ValueError("review identity/hash/acceptance violation")
            facts = parsed["facts"]
            if not facts:
                empty += 1
                empty_count += 1
            else:
                source_count += 1
            fact_count += len(facts)
            keyed = {}
            for fact in facts:
                if not Decimal(fact["value"]).is_finite():
                    raise ValueError("nonfinite fact")
                key = (fact["source_concept"], fact["context_id"], json.dumps(fact["unit"]))
                keyed.setdefault(key, set()).add(Decimal(fact["value"]))
                if fact["period_end"]:
                    periods.add(fact["period_end"])
            conflict_count += sum(len(values) > 1 for values in keyed.values())
            bases.update(parsed.get("identity_fields", {}).get("NatureOfReportStandaloneConsolidated", []))
            canonical_facts.append({"source_sha256": source["sha256"], "isin": parsed["isin"],
                                    "facts": facts, "identity_fields": parsed.get("identity_fields", {})})
        conflicts += conflict_count
        holding = ownership.get(target["isin"] + ":shareholding", {})
        rows.append({"ticker": target["ticker"], "isin": target["isin"], "exchange": target["primary_exchange"],
                     "financial_collection_status": entry.get("status", "NOT_ATTEMPTED"),
                     "financial_documents": len(entry.get("filings", [])), "documents_with_review_facts": source_count,
                     "empty_extractions": empty_count, "review_facts": fact_count,
                     "conflicting_numeric_contexts": conflict_count, "period_ends": "|".join(sorted(periods)),
                     "reported_bases": "|".join(sorted(bases)),
                     "ownership_status": holding.get("status", "NOT_ATTEMPTED"),
                     "ownership_review_candidate": bool(holding.get("candidate_fact")),
                     "accepted_new_facts": 0,
                     "remaining_action": "VALIDATE_TAXONOMY_ACCOUNTING_CONTEXT_UNITS_REVISIONS" if fact_count
                     else "REVIEW_RENDERED_TABLE_OR_STRUCTURED_XML" if empty_count
                     else "RESOLVE_IDENTITY_OR_ALTERNATE_OFFICIAL_FILING_LINK",
                     "pit_status": "NOT_APPROVED"})
    body = csv_bytes(rows, list(rows[0]))
    temp = pack / "issuer_recovery_audit.csv.tmp"
    temp.write_bytes(body)
    temp.replace(pack / "issuer_recovery_audit.csv")
    canonical_facts.sort(key=lambda r: (r["isin"], r["source_sha256"]))
    result = {"targets": len(rows), "financial_documents": filings,
              "identity_quarantined_documents": quarantined, "zero_fact_documents": empty,
              "issuers_with_review_facts": sum(r["review_facts"] > 0 for r in rows),
              "review_facts": sum(r["review_facts"] for r in rows),
              "conflicting_numeric_contexts": conflicts,
              "ownership_review_candidates": sum(r["ownership_review_candidate"] for r in rows),
              "raw_inventory_entries_verified": len(inventory), "accepted_new_facts": 0,
              "auto_promotion": False, "accounting_validation_complete": False,
              "financial_collection_states": dict(sorted(Counter(r["financial_collection_status"] for r in rows).items())),
              "canonical_extraction_sha256": sha(json.dumps(canonical_facts, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()),
              "issuer_audit_sha256": sha(body)}
    atomic_write_json(pack / "recovery_audit.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    print(json.dumps(audit(parser.parse_args().pack), sort_keys=True))
