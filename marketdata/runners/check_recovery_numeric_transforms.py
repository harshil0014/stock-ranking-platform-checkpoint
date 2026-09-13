"""Independent HTML/Decimal cross-check of simple iXBRL lexical numbers.

This is a validation diagnostic, not a financial parser or approval engine.
Unsupported transforms and duplicate/context ambiguity remain unverified.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
from bs4 import BeautifulSoup
from financial_recovery_pack import sha, csv_bytes


def simple_number(text, scale, sign):
    text = text.strip()
    if not re.fullmatch(r"-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", text):
        return None
    value = Decimal(text.replace(",", "")) * Decimal(10) ** int(scale or 0)
    if sign == "-":
        value = -value
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pack", type=Path, required=True)
    args = p.parse_args()
    pack = args.pack
    results = []
    for file in sorted((pack / "arelle_review_v2").glob("*.json")):
        if file.name == "summary.json":
            continue
        extracted = json.loads(file.read_text(encoding="utf-8"))
        raw = (pack / "raw" / (extracted["source_sha256"] + ".bin")).read_bytes()
        if sha(raw) != extracted["source_sha256"]:
            raise ValueError("source hash changed")
        soup = BeautifulSoup(raw, "html.parser")
        lexical = {}
        for fact in soup.find_all("ix:nonfraction"):
            if fact.get("xsi:nil", "").lower() == "true" or fact.get("continuedat"):
                continue
            format_name = (fact.get("format") or "").split(":")[-1].lower()
            if format_name not in {"", "numdotdecimal", "num-dot-decimal"}:
                continue
            value = simple_number(fact.get_text(), fact.get("scale"), fact.get("sign"))
            if value is not None:
                lexical.setdefault((fact.get("name"), fact.get("contextref")), set()).add(value)
        checked = 0
        mismatches = []
        for fact in extracted["facts"]:
            values = lexical.get((fact["source_concept"], fact["context_id"]), set())
            if len(values) != 1:
                continue
            checked += 1
            if Decimal(fact["value"]) != next(iter(values)):
                mismatches.append((fact["source_concept"], fact["context_id"]))
        results.append({"isin": extracted["isin"], "source_sha256": extracted["source_sha256"],
                        "extracted_facts": len(extracted["facts"]), "independently_checked": checked,
                        "mismatches": len(mismatches), "mismatch_keys": json.dumps(mismatches),
                        "accounting_approved": False})
    (pack / "independent_numeric_checks.csv").write_bytes(csv_bytes(results,
        ["isin", "source_sha256", "extracted_facts", "independently_checked", "mismatches", "mismatch_keys", "accounting_approved"]))
    print(json.dumps({"filings": len(results), "checked": sum(r["independently_checked"] for r in results),
                      "mismatches": sum(r["mismatches"] for r in results), "accounting_approved": False}))
    if any(r["mismatches"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
