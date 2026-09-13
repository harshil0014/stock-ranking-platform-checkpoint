"""Offline Arelle extraction for review only; no taxonomy validation or promotion.

Run with .venv-recovery, never the product environment. Raw source bytes are
unchanged. DTS loading is disabled: outputs cannot be called validated facts.
"""
from __future__ import annotations
import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re


def extract(path: Path, expected_isin: str):
    from arelle.api.Session import Session
    from arelle.RuntimeOptions import RuntimeOptions
    from lxml import etree
    body = path.read_bytes()
    observed = set(re.findall(r"\bIN[A-Z0-9]{10}\b", body.decode("utf-8", errors="replace")))
    if observed != {expected_isin}:
        raise ValueError("filing ISIN conflict or missing identity")
    options = RuntimeOptions(entrypointFile=str(path.resolve()), internetConnectivity="offline", skipDTS=True,
                             keepOpen=True, logFile="logToBuffer", disablePersistentConfig=True)
    rows, identity = [], {}
    with Session() as session:
        session.run(options)
        for model in session.get_models():
            for fact in model.facts:
                if fact.isNil:
                    continue
                name = str(fact.qname)
                if not fact.get("unitRef"):
                    if name.rsplit(":", 1)[-1] in {"ISIN", "NatureOfReportStandaloneConsolidated", "LevelOfRounding", "DescriptionOfPresentationCurrency"}:
                        identity.setdefault(name.rsplit(":", 1)[-1], set()).add(str(fact.value))
                    continue
                context = fact.context
                if context is None or fact.unit is None:
                    continue
                try:
                    value = Decimal(str(fact.value))
                except InvalidOperation:
                    continue
                if not value.is_finite():
                    continue
                periods = {e.tag.rsplit("}", 1)[-1]: e.text for e in context.iterdescendants()
                           if e.tag.rsplit("}", 1)[-1] in {"startDate", "endDate", "instant"}}
                rows.append({"source_concept": name, "context_id": fact.contextID,
                    "period_start": periods.get("startDate"), "period_end": periods.get("endDate", periods.get("instant")),
                    "instant": "instant" in periods, "value": str(value),
                    "unit": [[str(x) for x in values] for values in fact.unit.measures],
                    "scale": fact.get("scale"), "decimals": fact.get("decimals"), "sign": fact.get("sign"),
                    "dimensions": sorted((str(k), str(v.memberQname) if v.isExplicit else etree.tostring(v.typedMember, method="c14n").decode()) for k, v in context.qnameDims.items())})
        logs = session.get_logs("json")
    return {"source_sha256": hashlib.sha256(body).hexdigest(), "isin": expected_isin,
            "parser": "arelle-release", "parser_version": importlib.metadata.version("arelle-release"),
            "identity_fields": {k: sorted(v) for k, v in identity.items()},
            "status": "REVIEW_ONLY_DTS_NOT_VALIDATED", "accepted": False,
            "facts": sorted(rows, key=lambda r: (r["context_id"], r["source_concept"], r["value"])),
            "log": logs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    args = parser.parse_args()
    pack = args.pack
    progress = json.loads((pack / "financial_discovery_v2.json").read_text())
    output = pack / "arelle_review_v2"
    output.mkdir(exist_ok=True)
    summary = []
    for isin, entry in sorted(progress.items()):
        for filing in entry["filings"]:
            if filing["status"].startswith("QUARANTINED"):
                continue
            digest = filing["sha256"]
            raw = pack / filing["path"]
            if hashlib.sha256(raw.read_bytes()).hexdigest() != digest:
                raise ValueError("raw evidence hash changed")
            target = output / (digest + ".json")
            if not target.exists():
                html = output / (digest + ".html")
                if html.exists() and html.read_bytes() != raw.read_bytes():
                    raise ValueError("parser input conflict")
                if not html.exists():
                    html.write_bytes(raw.read_bytes())
                try:
                    result = extract(html, isin)
                except Exception as exc:
                    result = {"isin": isin, "source_sha256": digest, "accepted": False,
                              "status": "PARSE_FAILED", "error": f"{type(exc).__name__}: {exc}", "facts": []}
                target.write_text(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False), encoding="utf-8")
            result = json.loads(target.read_text(encoding="utf-8"))
            summary.append({"isin": isin, "source_sha256": digest, "status": result["status"], "facts": len(result["facts"])})
    (output / "summary.json").write_text(json.dumps(summary, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"filings": len(summary), "review_facts": sum(x["facts"] for x in summary), "accepted": 0}))


if __name__ == "__main__":
    main()
