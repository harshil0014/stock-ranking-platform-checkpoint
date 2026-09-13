"""Local manual-document intake for the existing official recovery pack.

Never uses archive filenames as issuer identity or calls any provider.
"""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path, PurePosixPath
import re
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from financial_recovery_pack import immutable, sha, targets, csv_bytes, atomic_write_json
from stock_ranker.exchange_backbone import parse_exchange_xbrl, FINANCIAL_COLUMNS


def name_key(value):
    value = re.sub(r"\bLTD\b", "LIMITED", value.upper())
    return re.sub(r"[^A-Z0-9]", "", value)


def supplement_archive(pack, inputs):
    """Deterministic cumulative local intake; retain prior batch and nested ZIP provenance."""
    members, sources = {}, []
    pointer = pack / "manual_latest.json"
    paths = list(inputs)
    if pointer.exists():
        prior = (pack / json.loads(pointer.read_text())["batch"]).resolve()
        if not prior.is_relative_to(pack.resolve()): raise ValueError("manual batch path escapes pack")
        paths.insert(0, prior / "archive.zip")
    def visit(raw, name, depth=0):
        if depth > 4 or len(raw) > 1_000_000_000: raise ValueError("archive safety limit")
        if zipfile.is_zipfile(io.BytesIO(raw)):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for entry in sorted(archive.infolist(), key=lambda e:e.filename):
                    if entry.is_dir(): continue
                    path = PurePosixPath(entry.filename.replace("\\", "/"))
                    if path.is_absolute() or ".." in path.parts or entry.file_size > 100_000_000:
                        raise ValueError("unsafe archive member")
                    visit(archive.read(entry), (name + "/" if name else "") + path.as_posix(), depth+1)
        else:
            if len(raw) > 100_000_000: raise ValueError("document safety limit")
            if sum(len(v) for v in members.values()) + len(raw) > 1_000_000_000:
                raise ValueError("expanded archive safety limit")
            members[name] = raw
    for path in paths:
        raw = path.read_bytes(); digest = sha(raw)
        immutable(pack / "manual_inputs" / digest / path.name, raw)
        sources.append({"name":path.name, "sha256":digest})
        visit(raw, "" if pointer.exists() and path == paths[0] else digest + "/" + path.name)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(members.items()):
            archive.writestr(zipfile.ZipInfo(name, date_time=(1980,1,1,0,0,0)), raw)
    body = output.getvalue(); target = pack / "manual_inputs" / (sha(body)+".zip")
    immutable(target, body)
    source_bytes = json.dumps(sources,sort_keys=True).encode()
    immutable(target.with_suffix("." + sha(source_bytes) + ".sources.json"), source_bytes)
    return target


def identify(text, registry, kind, raw):
    """Exact ISIN, or exact embedded scrip code AND normalized legal name."""
    isins = set(re.findall(r"\bINE[A-Z0-9]{8}[0-9]\b", text))
    if kind == "xml":
        root = ET.fromstring(raw)
        isins = {(e.text or "").strip() for e in root if e.tag.endswith("}ISIN")}
        codes = {(e.text or "").strip() for e in root.iter() if e.tag.endswith("}identifier") and "ScripCode" in e.get("scheme", "")}
    else:
        codes = set(re.findall(r"(?i)(?:stock\s*code(?:\s*no\.?)?|scrip\s*code|bse\s*(?:code|scrip\s*code|security\s*code))(?:\s+of\s+the\s+company\s+is)?\s*[:\-]?\s*(\d{6})\b", text))
    matches = [r for r in registry if r["isin"] in isins]
    if len(matches) == 1:
        r = matches[0]
        xml_code_valid = codes == {r["exchange_security_id"]}
        if kind == "xml" and r.get("primary_exchange", "BSE") == "NSE" and len(codes) == 1:
            names = {(e.text or "").strip() for e in root if e.tag.endswith("}NameOfTheCompany")}
            xml_code_valid = xml_code_valid or names == {r["company"]} or {name_key(n) for n in names} == {name_key(r["company"])}
        if kind == "xml" and (isins != {r["isin"]} or not xml_code_valid):
            return None, "XML_ENTITY_IDENTITY_CONFLICT"
        other_codes = {x["exchange_security_id"] for x in registry if x["isin"] != r["isin"] and x.get("primary_exchange", "BSE") == "BSE"}
        if codes & other_codes or (codes and r.get("primary_exchange", "BSE") == "BSE" and r["exchange_security_id"] not in codes):
            return None, "ISIN_SCRIP_CONFLICT"
        return r, "EXACT_EMBEDDED_ISIN"
    if matches:
        return None, "MULTIPLE_CANONICAL_ISINS"
    matches = [r for r in registry if r["exchange_security_id"] in codes and name_key(r["company"]) in name_key(text)]
    if len(matches) == 1 and not isins:
        return matches[0], "EXACT_SCRIP_AND_LEGAL_NAME"
    return None, "IDENTITY_UNRESOLVED"


def candidate_identity(text, registry, kind, raw):
    """Associate rejected evidence to one exact target without accepting identity."""
    found, status = identify(text, registry, kind, raw)
    if found:
        return found, status
    isins, codes, names = set(), set(), set()
    if kind == "xml":
        root = ET.fromstring(raw)
        isins = {(e.text or "").strip() for e in root if e.tag.endswith("}ISIN")}
        codes = {(e.text or "").strip() for e in root.iter() if e.tag.endswith("}identifier")}
        names = {(e.text or "").strip() for e in root if e.tag.endswith("}NameOfTheCompany")}
    else:
        isins = set(re.findall(r"\bINE[A-Z0-9]{8}[0-9]\b", text))
        codes = set(re.findall(r"(?i)(?:scrip\s*code|stock\s*code|bse\s*(?:code|scrip\s*code|security\s*code))(?:\s+of\s+the\s+company\s+is)?\s*[:\-]?(?:\s*no\.?)?\s*(\d{6})\b", text))
    candidates = []
    normalized_text = name_key(text)
    for row in registry:
        exact_name = any(name_key(n) == name_key(row["company"]) for n in names)
        normalized_company = name_key(row["company"])
        embedded_name = len(normalized_company) >= 12 and normalized_company in normalized_text
        if row["isin"] in isins or (row["primary_exchange"] == "BSE" and row["exchange_security_id"] in codes) or exact_name or embedded_name:
            candidates.append(row)
    unique = {r["isin"]: r for r in candidates}
    if len(unique) == 1:
        candidate = next(iter(unique.values()))
        if isins and candidate["isin"] not in isins:
            return candidate, "EMBEDDED_ISIN_CANONICAL_CONFLICT"
        return candidate, status
    return None, status


def recovery_tail_targets(registry, discovery, docs, pack):
    statuses = {"NO_LINKED_IXBRL_IN_CATALOGUE", "NO_FINANCIAL_LINK_IN_CACHED_NSE_CATALOGUE"}
    chosen = {r["isin"]: r for r in registry if discovery.get(r["isin"], {}).get("status") in statuses}
    for doc in docs:
        if "last_remaining.zip" not in doc["uploaded_file"] or doc["type"] != "xml":
            continue
        raw = (pack / doc["path"]).read_bytes()
        pages = json.loads((pack / doc["pages_file"]).read_text())["pages"]
        candidate, _ = candidate_identity("\n".join(pages), registry, "xml", raw)
        if candidate:
            chosen[candidate["isin"]] = candidate
    return [chosen[k] for k in sorted(chosen)]


def xml_facts(raw, identity, digest):
    root = ET.fromstring(raw)
    local = lambda e: e.tag.rsplit("}", 1)[-1]
    direct = {}
    for e in root:
        direct.setdefault(local(e), set()).add((e.text or "").strip())
    basis = direct.get("NatureOfReportStandaloneConsolidated", set())
    rounding = direct.get("LevelOfRoundingUsedInFinancialStatements", set()) | direct.get("LevelOfRounding", set())
    audits = direct.get("WhetherResultsAreAuditedOrUnaudited", set())
    opinions = direct.get("OpinionOfAuditors", set())
    contexts = {e.get("id"): e for e in root if local(e) == "context"}
    units = {e.get("id"): e for e in root if local(e) == "unit"}
    if len(contexts) != sum(local(e) == "context" for e in root) or len(units) != sum(local(e) == "unit" for e in root):
        raise ValueError("duplicate XML context/unit identifiers")
    nodes = {}
    for e in root:
        if e.get("unitRef"):
            nodes.setdefault((local(e), e.get("contextRef")), []).append(e)
    frame = parse_exchange_xbrl(raw, filename="content_verified.xml", metadata={
        "symbol": identity["ticker"], "isin": identity["isin"], "exchange": "BSE",
        "consolidated": next(iter(basis)) if len(basis) == 1 else "UNKNOWN",
        "filing_id": digest, "revision_status": "UNVERIFIED_NO_PRECEDENCE_OVERRIDE"})
    rows = []
    for item in frame.to_dict("records"):
        alternatives = nodes.get((item["source_concept"], item["context_id"]), [])
        if not alternatives:
            continue
        node = alternatives[0]
        reasons = []
        if len({(e.text, e.get("unitRef")) for e in alternatives}) > 1: reasons.append("CONFLICTING_DUPLICATE_XML_FACT")
        context = contexts[item["context_id"]]
        measures = [(e.text or "").strip() for e in units.get(node.get("unitRef"), []) if local(e) == "measure"]
        if basis != {"Standalone"}: reasons.append("BASIS_NOT_UNAMBIGUOUS_STANDALONE")
        if audits != {"Audited"}: reasons.append("AUDIT_CONTEXT_UNRESOLVED")
        if any(local(e) in {"scenario", "segment"} for e in context): reasons.append("DIMENSIONAL_NOT_COMPANY_TOTAL")
        if item["canonical_concept"].startswith("unknown:"): reasons.append("UNMAPPED_TAXONOMY_CONCEPT")
        if not re.match(r"\{(?:http://www\.bseindia\.com/xbrl/fin/(?:2018-03-31|2020-03-31)/in-bse-fin|http://www\.sebi\.gov\.in/xbrl/2026-01-31/in-capmkt)\}", node.tag): reasons.append("UNVERIFIED_TAXONOMY_NAMESPACE")
        ratio = item["canonical_concept"] == "debt_to_equity"
        if ratio:
            if measures not in (["xbrli:pure"], ["pure"]): reasons.append("RATIO_UNIT_REQUIRES_REVIEW")
        elif measures != ["iso4217:INR"]: reasons.append("NON_MONETARY_UNIT_REQUIRES_REVIEW")
        value = Decimal(node.text.strip())
        if not value.is_finite(): reasons.append("NONFINITE")
        if Decimal(str(item["value"])) != value: reasons.append("PARSER_NUMERIC_MISMATCH")
        # XBRL monetary facts are already in INR. Presentation rounding is NOT
        # an instruction to multiply these instance values a second time.
        item.update(value=str(value), unit="ratio" if ratio else "INR", source_sha256=digest,
            source_url=None, available_at=None, revision_at=None, pit_usable=False,
            pit_reason="NO_VERIFIED_EXCHANGE_DISSEMINATION_CLOCK",
            accounting_family=node.tag.split("}")[0].lstrip("{") + ";DIRECT_MAPPED_FACTS", dimensions=ET.tostring(context, encoding="unicode"),
            source_type="OFFICIAL_EXCHANGE_XBRL_XML", audit_status="|".join(sorted(audits | opinions)), presentation_rounding="|".join(sorted(rounding)),
            review_status="REJECTED" if reasons else "ACCEPTED_CURRENT_REFERENCE",
            rejection_reasons="|".join(reasons), evidence_label=item["source_concept"], evidence_page=1)
        rows.append(item)
    # Verify the accounting identities where the instance supplies all terms.
    for cid in contexts:
        group = {r["canonical_concept"]: Decimal(r["value"]) for r in rows if r["context_id"] == cid}
        failed = ((all(k in group for k in ("assets", "equity", "liabilities")) and group["assets"] != group["equity"] + group["liabilities"])
            or (all(k in group for k in ("pbt", "tax", "pat")) and group["pbt"] - group["tax"] != group["pat"]))
        if failed:
            for row in rows:
                if row["context_id"] == cid:
                    row.update(review_status="REJECTED", rejection_reasons=row["rejection_reasons"] + "|ACCOUNTING_RECONCILIATION_FAILED")
    return rows


LABELS = {
    "revenue": r"(?:total\s+)?revenue\s+from\s+operations\b",
    "total_income": r"total\s+income\b",
    "finance_costs": r"finance\s+costs?\b",
    "assets": r"total\s+assets\b",
    "liabilities": r"total\s+liabilities(?!\s+and)\b",
    "equity": r"total\s+equity(?!\s+and)\b",
    "cash": r"cash\s+and\s+cash\s+equivalents\b",
    "pat": r"(?:profit|loss)(?:\s*/?\s*\(?loss\)?)?\s+for\s+(?:the\s+)?(?:year|period)\b",
    "pbt": r"(?:profit|loss)(?:\s*/?\s*\(?loss\)?)?\s+before\s+tax(?:es)?\b",
    "operating_cash_flow": r"net\s+cash\s+(?:flows?\s+)?(?:from|used\s+in|generated\s+from|provided\s+by)\s+operating\s+activities\b",
    "investing_cash_flow": r"net\s+cash\s+(?:flows?\s+)?(?:from|used\s+in|generated\s+from|provided\s+by)\s+investing\s+activities\b",
    "financing_cash_flow": r"net\s+cash\s+(?:flows?\s+)?(?:from|used\s+in|generated\s+from|provided\s+by)\s+financing\s+activities\b",
}
AMOUNT = re.compile(r"(?<![\w.])\(?-?\d[\d,]*(?:\.\d+)?\)?(?![\w.%])")


def compact(text):
    return re.sub(r"\s+", " ", text).strip()


def amount(token):
    return Decimal(token.replace(",", "").strip("()")) * (-1 if token.startswith("(") else 1)


def pdf_facts(pages, independent, identity, digest):
    rows = []
    for page_no, text in enumerate(pages, 1):
        normalized_page = compact(text)
        is_profit = bool(re.search(r"statement of profit|revenue from operations.*total income.*(?:profit|loss).*before tax", normalized_page, re.I))
        is_balance = bool(re.search(r"balance sheet|total assets.*liabilities.*equity", normalized_page, re.I))
        is_cash_flow = bool(re.search(r"cash flow statement|statement of cash flow|cash flows? from operating activities.*cash flows? from investing activities", normalized_page, re.I))
        if not (is_profit or is_balance or is_cash_flow): continue
        # Explicit basis on the statement page only. No document-wide inference
        # across standalone/consolidated sections or prospectus subsidiaries.
        basis = "CONSOLIDATED" if "consolidated" in text.lower() else "STANDALONE" if "standalone" in text.lower() else "UNKNOWN"
        heading = compact(text)[:2200]
        statement_heading = heading[:900].lower()
        basis_page = page_no if basis != "UNKNOWN" else None
        audit_context = bool(re.search(r"as per.*report|chartered accountants|auditor", text, re.I))
        examined_restated = False
        for earlier in range(page_no-2, max(-1, page_no-80), -1):
            earlier_text = compact(pages[earlier])
            statement = (re.search(r"we\s+have\s+audited\s+(?:the\s+)?(?:accompanying\s+)?(standalone|consolidated)\s+(?:ind\s+as\s+)?financial\s+statements", earlier_text, re.I)
                         or re.search(r"report\s+on\s+(?:the\s+)?audit\s+of\s+(?:the\s+)?(standalone|consolidated)(?:\s+ind\s+as)?\s+financial", earlier_text, re.I))
            examination = (re.search(r"independent auditor(?:'s|s’)?\s+(?:examination\s+)?report.*restated\s+(standalone|consolidated)\s+financial", earlier_text, re.I)
                           or re.search(r"independent auditor.*report\s+on\s+restated\s+(standalone|consolidated)\s+financial", earlier_text, re.I))
            if statement or examination:
                evidence = statement or examination
                if basis == "UNKNOWN":
                    basis = evidence.group(1).upper()
                    basis_page = earlier + 1
                audit_context = True
                examined_restated = examined_restated or bool(examination)
        unit_matches = []
        for word, factor in ((r"lakhs?|lacs?", "100000"), (r"crores?", "10000000"), (r"thousands?", "1000"), (r"hundreds?", "100"), (r"millions?", "1000000")):
            if re.search(r"(?:\bin\s+|currency\s*:\s*)(?:(?:indian\s+rupees|inr|rs\.?|₹|`)\s*)?(?:" + word + ")", heading, re.I): unit_matches.append(factor)
        if not unit_matches and re.search(r"(?:amt\.?|amounts?)\s+in\s+(?:indian\s+)?(?:rupees|rs\.?)\b|\(\s*(?:in\s+)?(?:rs\.?|inr)\s*\)", heading, re.I):
            unit_matches.append("1")
        # Exact March year-end headers, retaining source column order.
        years = []
        for match in re.finditer(r"(?:March\s+31(?:st)?[,\s]+|31(?:st)?[\s-]+March[,\s-]+|31[./-]03[./-])(20\d{2})", compact(heading), re.I):
            if match.group(1) not in years: years.append(match.group(1))
        peer = compact(independent[page_no-1]).replace(",", "") if len(independent) >= page_no else ""
        for line in text.splitlines():
            cleaned = compact(line)
            for concept, pattern in LABELS.items():
                if concept in {"revenue", "total_income", "finance_costs", "pat", "pbt"} and not is_profit: continue
                if concept in {"assets", "liabilities", "equity", "cash"} and not is_balance: continue
                if concept.endswith("cash_flow") and not is_cash_flow: continue
                match = re.search(pattern, cleaned, re.I)
                if not match: continue
                tail = cleaned[match.end():]
                if concept == "pat" and re.search(r"continuing|discontinued|margin|attributable", tail, re.I): continue
                tokens = AMOUNT.findall(tail)
                if not tokens: continue
                if len(years) >= 2 and len(tokens) > len(years):
                    tokens = tokens[-len(years):]
                reasons = []
                nearby_audit = " ".join(pages[max(0,page_no-24):page_no]).lower()
                if "disclaimer of opinion" in nearby_audit: reasons.append("AUDITOR_DISCLAIMER_REQUIRES_REVIEW")
                if basis != "STANDALONE": reasons.append("BASIS_NOT_EXPLICIT_ON_STATEMENT_PAGE")
                if len(unit_matches) != 1: reasons.append("UNIT_SCALING_UNRESOLVED")
                if len(years) < 2 or len(tokens) != len(years): reasons.append("PERIOD_OR_COLUMN_ALIGNMENT_UNRESOLVED")
                peer_values = {t.replace(",", "").strip("()") for t in AMOUNT.findall(peer)}
                source_values = {t.replace(",", "").strip("()") for t in tokens}
                if not re.search(pattern, peer, re.I) or not source_values <= peer_values:
                    reasons.append("INDEPENDENT_EXTRACTION_DISAGREEMENT")
                restated = "restated" in text.lower()
                if restated and not (basis == "STANDALONE" and examined_restated):
                    reasons.append("RESTATED_REVISION_REVIEW_REQUIRED")
                if concept == "investing_cash_flow" and re.search(r"cash\s+flow\s+from\s+investing.*?issue\s+of\s+preferential\s+equity.*?cash\s+flow\s+from\s+financing", compact(text), re.I):
                    reasons.append("ISSUER_CASHFLOW_CLASSIFICATION_REVIEW_REQUIRED")
                if not audit_context: reasons.append("AUDITOR_CONTEXT_REVIEW_REQUIRED")
                for index, token in enumerate(tokens):
                    value = amount(token)
                    rows.append({"ticker": identity["ticker"], "isin": identity["isin"], "exchange": identity.get("primary_exchange", "BSE"),
                        "accounting_family": "DIRECT_DISCLOSURE_NO_RATIO_DERIVATION", "statement_basis": basis,
                        "period_type": ("INSTANT" if concept in {"assets", "liabilities", "equity", "cash"} else "ANNUAL") if len(years) >= 2 else "UNKNOWN", "period_start": None,
                        "period_end": years[index] + "-03-31" if index < len(years) and len(tokens) == len(years) else None,
                        "value": str(value * Decimal(unit_matches[0])) if len(unit_matches) == 1 else str(value),
                        "unit": "INR" if len(unit_matches) == 1 else "UNRESOLVED_AS_REPORTED",
                        "reported_value": str(value), "presentation_rounding": unit_matches[0] if len(unit_matches) == 1 else "UNKNOWN",
                        "canonical_concept": concept, "source_concept": match.group(), "context_id": f"page_{page_no}_column_{index+1}",
                        "source_type": "PROSPECTUS_RESTATED" if restated else "ANNUAL_REPORT_PDF",
                        "audit_status": "AUDITOR_CONTEXT_ON_PAGE" if not any("AUDITOR" in r for r in reasons) else "REVIEW_REQUIRED",
                        "source_sha256": digest, "source_url": None, "filing_id": digest,
                        "available_at": None, "revision_at": None,
                        "revision_status": "RESTATED_AUDITOR_EXAMINED;NO_PRECEDENCE_OVERRIDE" if restated and examined_restated else "UNVERIFIED_NO_PRECEDENCE_OVERRIDE",
                        "pit_usable": False, "pit_reason": "NO_VERIFIED_EXCHANGE_DISSEMINATION_CLOCK",
                        "evidence_page": page_no, "evidence_label": cleaned,
                        "basis_evidence_page": basis_page,
                        "review_status": "REJECTED" if reasons else "ACCEPTED_CURRENT_REFERENCE",
                        "rejection_reasons": "|".join(reasons)})
    return rows


def visual_review_facts(pack, batch, registry):
    """Load human-adjudicated scanned pages with hash-bound evidence."""
    path = batch / "visual_reviews.json"
    if not path.exists():
        return [], []
    reviews = json.loads(path.read_text(encoding="utf-8"))
    facts, audits = [], []
    for review in reviews:
        raw = pack / "raw" / (review["source_sha256"] + ".bin")
        if sha(raw.read_bytes()) != review["source_sha256"]:
            raise ValueError("visual-review raw evidence mismatch")
        identity = next((r for r in registry if r["isin"] == review["isin"]), None)
        if not identity or name_key(identity["company"]) != name_key(review["company"]):
            raise ValueError("visual-review canonical identity mismatch")
        for page, expected in review["rendered_page_sha256"].items():
            rendered = batch / "pdfium" / f'{review["source_sha256"]}-{page}.png'
            if sha(rendered.read_bytes()) != expected:
                raise ValueError("visual-review rendered page mismatch")
        for source in review["facts"]:
            value = Decimal(source["reported_value"])
            factor = Decimal(source["scale_factor"])
            if not value.is_finite() or factor <= 0:
                raise ValueError("invalid visual-review numeric value")
            facts.append({"ticker": identity["ticker"], "isin": identity["isin"], "exchange": identity["primary_exchange"],
                "accounting_family": "AUDITED_STANDALONE_VISUAL_PAGE_ADJUDICATION", "statement_basis": "STANDALONE",
                "period_type": source["period_type"], "period_start": source.get("period_start"), "period_end": source["period_end"],
                "available_at": None, "revision_at": None, "revision_status": "ORIGINAL_AUDITED;NO_PRECEDENCE_OVERRIDE",
                "filing_id": review["source_sha256"], "canonical_concept": source["canonical_concept"],
                "source_concept": source["source_label"], "value": str(value * factor), "unit": "INR",
                "context_id": f'visual_page_{source["page"]}_{source["period_end"]}', "source_url": None,
                "source_sha256": review["source_sha256"], "source_type": "AUDITED_FINANCIAL_STATEMENTS_SCANNED_PDF",
                "audit_status": review["audit_status"], "presentation_rounding": source["display_unit"],
                "reported_value": str(value), "dimensions": "", "basis_evidence_page": review["basis_evidence_page"],
                "review_status": "ACCEPTED_CURRENT_REFERENCE", "rejection_reasons": "", "evidence_page": source["page"],
                "evidence_label": source["source_label"], "pit_usable": False,
                "pit_reason": "NO_VERIFIED_EXCHANGE_DISSEMINATION_CLOCK", "uploaded_file": review["uploaded_file"],
                "archive_sha256": batch.name, "source_provenance": review["source_provenance"],
                "duplicate_provenance": ""})
        audits.append({"source_sha256": review["source_sha256"], "isin": identity["isin"],
            "target_isin": identity["isin"], "company": identity["company"],
            "identity_status": review["identity_status"], "visual_review": True,
            "uploaded_file": review["uploaded_file"], "source_type": "AUDITED_FINANCIAL_STATEMENTS_SCANNED_PDF",
            "facts_extracted": len(review["facts"]), "type": "pdf", "error": None,
            "restated": False, "basis_mentions": ["standalone"], "cin_evidence": []})
    return facts, audits


def classify_residual_blocker(documents, review_facts, accepted, missing):
    if not missing:
        return "RESOLVED"
    if not documents:
        return "SOURCE_EVIDENCE_NOT_ASSOCIATED"
    statuses = {d.get("identity_status", "") for d in documents} | {d.get("candidate_identity_status", "") for d in documents}
    if not accepted and statuses & {"XML_ENTITY_IDENTITY_CONFLICT", "ISIN_SCRIP_CONFLICT", "MULTIPLE_CANONICAL_ISINS", "EMBEDDED_ISIN_CANONICAL_CONFLICT"}:
        return "IDENTITY_AMBIGUITY"
    if not accepted and all(d.get("source_type") in {"GENERAL_INFORMATION_DOCUMENT", "UNSUPPORTED_NON_FINANCIAL_CONTENT"} for d in documents):
        return "SOURCE_EVIDENCE_INSUFFICIENT"
    if review_facts and not accepted:
        reasons = sorted({reason for fact in review_facts for reason in fact.get("rejection_reasons", "").split("|") if reason})
        if reasons:
            return "ACCOUNTING_CONTEXT_VALIDATION_FAILED:" + "|".join(reasons)
    if not review_facts:
        if any(d.get("error") for d in documents):
            return "PARSER_LIMITATION"
        if not any(d.get("identity_status", "").startswith("EXACT_") for d in documents):
            return "IDENTITY_VALIDATION_FAILED:NO_EXACT_ISIN_OR_CANONICAL_EXCHANGE_CODE_LINK"
        return "PARSER_LIMITATION:NO_VALIDATED_STATEMENT_FACTS_FROM_SUPPORTED_LAYOUT"
    return "MISSING_REQUIRED_METRIC"


def another_document_required(documents, review_facts, accepted):
    if not documents:
        return True
    statuses = {d.get("identity_status", "") for d in documents} | {d.get("candidate_identity_status", "") for d in documents}
    if not accepted and statuses & {"XML_ENTITY_IDENTITY_CONFLICT", "ISIN_SCRIP_CONFLICT", "MULTIPLE_CANONICAL_ISINS", "EMBEDDED_ISIN_CANONICAL_CONFLICT"}:
        return True
    return not review_facts and all(d.get("source_type") in {"GENERAL_INFORMATION_DOCUMENT", "UNSUPPORTED_NON_FINANCIAL_CONTENT"} for d in documents)


def required_document(documents, review_facts, accepted):
    if not another_document_required(documents, review_facts, accepted):
        return ""
    statuses = {d.get("identity_status", "") for d in documents} | {d.get("candidate_identity_status", "") for d in documents}
    if statuses & {"XML_ENTITY_IDENTITY_CONFLICT", "ISIN_SCRIP_CONFLICT", "MULTIPLE_CANONICAL_ISINS", "EMBEDDED_ISIN_CANONICAL_CONFLICT"}:
        return "OFFICIAL_SECURITY_MASTER_OR_CORPORATE_ACTION_RECORD_LINKING_DOCUMENT_ISIN_TO_CURRENT_CANONICAL_ISIN"
    return "AUDITED_STANDALONE_FINANCIAL_STATEMENTS_FOR_LATEST_COMPLETED_FINANCIAL_YEAR"


def ingest_archive(pack, archive):
    data = archive.read_bytes()
    batch = pack / "manual" / sha(data)
    batch.mkdir(parents=True, exist_ok=True)
    immutable(batch / "archive.zip", data)
    if not (batch / "before_recovery_audit.json").exists():
        immutable(batch / "before_recovery_audit.json", (pack / "recovery_audit.json").read_bytes())
    manifest = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for member in sorted(z.infolist(), key=lambda m: m.filename):
            if member.is_dir():
                continue
            name = PurePosixPath(member.filename.replace("\\", "/"))
            if name.is_absolute() or ".." in name.parts or member.file_size > 100_000_000:
                raise ValueError("unsafe archive member")
            raw = z.read(member)
            digest = sha(raw)
            kind = "pdf" if raw.startswith(b"%PDF-") else "xml" if raw.lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"<") else "unknown"
            relative = "raw/" + digest + ".bin"
            immutable(pack / relative, raw)
            cached = batch / (digest + ".pages.json")
            if not cached.exists():
                previous = sorted((pack / "manual").glob("*/" + cached.name))
                if previous: immutable(cached, previous[0].read_bytes())
            if not cached.exists():
                try:
                    if kind == "pdf":
                        from pypdf import PdfReader
                        pages = [p.extract_text(extraction_mode="layout") for p in PdfReader(io.BytesIO(raw)).pages]
                    elif kind == "xml":
                        if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                            raise ValueError("unsafe XML")
                        root = ET.fromstring(raw)
                        pages = ["\n".join(e.tag.rsplit("}", 1)[-1] + ": " + (e.text or "") for e in root.iter() if e.text and e.text.strip())]
                    else:
                        raise ValueError("unsupported content signature")
                    result = {"pages": pages, "error": None}
                except Exception as exc:
                    result = {"pages": [], "error": f"{type(exc).__name__}: {exc}"}
                immutable(cached, json.dumps(result, sort_keys=True, ensure_ascii=True).encode())
            parsed = json.loads(cached.read_text())
            text = "\n".join(parsed["pages"])
            manifest.append({"uploaded_file": member.filename, "source_sha256": digest,
                "path": relative, "type": kind, "page_count": len(parsed["pages"]), "error": parsed["error"],
                "embedded_isins": sorted(set(re.findall(r"\bIN[A-Z0-9]{9}[0-9]\b", text))),
                "embedded_codes": sorted(set(re.findall(r"(?i)(?:scrip|security|bse)[^\n]{0,45}?\b(\d{6})\b", text))),
                "pages_file": cached.relative_to(pack).as_posix()})
            print(json.dumps({"file": member.filename, "pages": len(parsed["pages"]), "isins": manifest[-1]["embedded_isins"], "codes": manifest[-1]["embedded_codes"], "error": parsed["error"]}), flush=True)
    immutable(batch / "documents.json", json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
    return batch


def validate_batch(pack, batch):
    registry = targets(pack)
    discovery = json.loads((pack / "financial_discovery_v2.json").read_text())
    docs = json.loads((batch / "documents.json").read_text())
    selected = recovery_tail_targets(registry, discovery, docs, pack)
    if len(selected) != 41:
        raise ValueError(f"expected exact 41-issuer recovery tail, got {len(selected)}")
    prior_accepted = []
    if (pack / "manual_latest.json").exists():
        try:
            prior_accepted = load_current_reference(pack)
        except ValueError as exc:
            # A prior interrupted derived-report publication may leave the
            # recomputed CSV ahead of its terminal hash manifest. Treat it only
            # as a no-loss comparison input after validating every source hash
            # and the strict current/reference boundary; it is never published
            # or consumed as accepted state until this validation completes.
            if str(exc) != "manual artifact mismatch":
                raise
            import csv
            prior_path = batch / "manual_current_reference_facts.csv"
            prior_accepted = list(csv.DictReader(prior_path.open(encoding="utf-8")))
            known = {r["isin"] for r in registry}
            for row in prior_accepted:
                raw = pack / "raw" / (row["source_sha256"] + ".bin")
                if (row["isin"] not in known or row["review_status"] != "ACCEPTED_CURRENT_REFERENCE"
                        or row["pit_usable"] != "False" or row["available_at"]
                        or not raw.exists() or sha(raw.read_bytes()) != row["source_sha256"]):
                    raise ValueError("unpublished manual current/reference boundary violation") from exc
    prior_review_path = batch / "manual_review_facts.csv"
    prior_review_count = sum(1 for _ in __import__('csv').DictReader(prior_review_path.open(encoding="utf-8"))) if prior_review_path.exists() else 0
    all_facts, audits, texts = [], [], {}
    for doc in docs:
        raw = (pack / doc["path"]).read_bytes()
        if sha(raw) != doc["source_sha256"]: raise ValueError("manual raw hash mismatch")
        pages = json.loads((pack / doc["pages_file"]).read_text())["pages"]
        text = "\n".join(pages)
        identity, match_status = identify(text, registry, doc["type"], raw)
        candidate = identity
        candidate_status = match_status
        if not candidate:
            candidate, candidate_status = candidate_identity(text, registry, doc["type"], raw)
        facts = []
        if identity:
            texts.setdefault(identity["isin"], []).append(text)
            if doc["type"] == "xml": facts = xml_facts(raw, identity, doc["source_sha256"])
            elif doc["type"] == "pdf":
                other = batch / "pdfium" / (doc["source_sha256"] + ".json")
                if other.exists():
                    independent = json.loads(other.read_text())
                    if independent["source_sha256"] != doc["source_sha256"]: raise ValueError("independent source mismatch")
                    # Either engine may preserve a table better. Candidates
                    # from both directions still require cross-engine numeric
                    # concordance and all accounting-context checks below.
                    facts = (pdf_facts(pages, independent["pages"], identity, doc["source_sha256"])
                             + pdf_facts(independent["pages"], pages, identity, doc["source_sha256"]))
            for fact in facts:
                fact["uploaded_file"] = doc["uploaded_file"]
                fact["archive_sha256"] = batch.name
                fact["source_provenance"] = "USER_SUPPLIED_DOCUMENT; SOURCE_BYTES_HASHED; NO_DOWNLOAD_URL_INVENTED"
            all_facts.extend(facts)
        source_type = "BSE_XBRL_XML" if doc["type"] == "xml" else "DRHP" if "draft red herring prospectus" in compact(text[:18000]).lower() else "RHP" if "red herring prospectus" in compact(text[:18000]).lower() else "PROSPECTUS" if "prospectus" in compact(text[:18000]).lower() else "ANNUAL_REPORT_PDF"
        if doc["type"] not in {"xml", "pdf"}: source_type = "UNSUPPORTED_NON_FINANCIAL_CONTENT"
        elif doc["type"] == "pdf" and "general information document" in compact(text[:600]).lower(): source_type = "GENERAL_INFORMATION_DOCUMENT"
        audits.append({**doc, "source_type": source_type, "isin": identity["isin"] if identity else None,
            "target_isin": (identity or candidate or {}).get("isin"),
            "candidate_identity_status": candidate_status,
            "bse_code": identity["exchange_security_id"] if identity and identity["primary_exchange"] == "BSE" else None,
            "company": identity["company"] if identity else None, "identity_status": match_status,
            "cin_evidence": sorted(set(re.findall(r"\b[LU]\d{5}[A-Z]{2}\d{4}PLC\d{6}\b", text))),
            "basis_mentions": sorted(set(re.findall(r"standalone|consolidated", text.lower()))),
            "restated": "restated" in text.lower(), "facts_extracted": len(facts)})
    visual_facts, visual_audits = visual_review_facts(pack, batch, registry)
    all_facts.extend(visual_facts)
    audits.extend(visual_audits)
    valid_identity_sources = {d["source_sha256"] for d in audits if d.get("isin")}
    prior_accepted = [r for r in prior_accepted if r.get("source_sha256") in valid_identity_sources]
    # Same period/basis/concept with conflicting values is NOT resolved by ZIP
    # order or filenames. Identical repeats are deduplicated in the export.
    groups = {}
    for row in all_facts:
        if row["review_status"] == "ACCEPTED_CURRENT_REFERENCE":
            key = tuple(row.get(k) for k in ("isin", "statement_basis", "period_type", "period_end", "canonical_concept", "unit"))
            groups.setdefault(key, []).append(row)
    accepted = []
    for key, group in sorted(groups.items()):
        if len({r["value"] for r in group}) > 1:
            for row in group:
                row.update(review_status="REJECTED", rejection_reasons="CONFLICTING_DISCLOSURES_REVISION_UNRESOLVED")
        else:
            accepted.append({**group[0], "duplicate_provenance": json.dumps(sorted({r["source_sha256"] for r in group}))})
    accepted_exact = {tuple(str(r.get(k) or "") for k in ("isin", "statement_basis", "period_type", "period_end", "canonical_concept", "unit", "value")) for r in accepted}
    for row in prior_accepted:
        exact = tuple(str(row.get(k) or "") for k in ("isin", "statement_basis", "period_type", "period_end", "canonical_concept", "unit", "value"))
        if exact not in accepted_exact:
            accepted.append(row)
            accepted_exact.add(exact)
    accepted.sort(key=lambda r: tuple(str(r.get(k) or "") for k in ("isin", "period_end", "statement_basis", "period_type", "canonical_concept", "value", "source_sha256")))
    columns = [*FINANCIAL_COLUMNS, "source_type", "audit_status", "presentation_rounding", "reported_value", "dimensions", "basis_evidence_page",
        "review_status", "rejection_reasons", "evidence_page", "evidence_label", "pit_usable", "pit_reason",
        "uploaded_file", "archive_sha256", "source_provenance", "duplicate_provenance"]
    if prior_accepted:
        keys = ("isin", "statement_basis", "period_type", "period_end", "canonical_concept", "unit", "value")
        previous = {tuple(str(r.get(k) or "") for k in keys) for r in prior_accepted}
        current = {tuple(str(r.get(k) or "") for k in keys) for r in accepted}
        if not previous <= current:
            lost = sorted(previous-current)
            context = sorted(row for row in current if row[:5] == lost[0][:5])
            raise ValueError(f"Prior accepted recovery facts would be lost/conflicted; publication stopped: {lost[:5]}; current={context[:5]}")
    outputs = {"manual_review_facts.csv": csv_bytes(all_facts, columns),
               "manual_current_reference_facts.csv": csv_bytes(accepted, columns)}
    fields = {"annual_financials": lambda r:r["period_type"] == "ANNUAL" and r["canonical_concept"] in {"pat","revenue","total_income"},
              "quarterly_financials": lambda r:r["period_type"] == "QUARTERLY" and r["canonical_concept"] in {"pat","revenue","total_income"},
              "balance_sheet": lambda r:r["canonical_concept"] in {"assets","equity","liabilities"},
              "cash_flow": lambda r:r["canonical_concept"] in {"operating_cash_flow","investing_cash_flow","financing_cash_flow"},
              **{c:(lambda r,c=c:r["canonical_concept"] == c) for c in ("revenue","pat","borrowings","equity","roce","roe","debt_to_equity")}}
    company_rows, residual = [], []
    for target in selected:
        isin = target["isin"]
        own = [r for r in all_facts if r["isin"] == isin]
        approved = [r for r in accepted if r["isin"] == isin]
        documents = [r for r in audits if r.get("target_isin", r.get("isin")) == isin or r.get("isin") == isin]
        missing = [f for f, rule in fields.items() if not any(rule(r) for r in approved)]
        row = {"bse_code": target["exchange_security_id"] if target["primary_exchange"] == "BSE" else "", "exchange_code": target["exchange_security_id"],
            "exchange": target["primary_exchange"], "ticker":target["ticker"], "issuer": target["company"], "isin": isin, "company": target["company"],
            "uploaded_files": "|".join(r["uploaded_file"] for r in documents),
            "document_hashes": "|".join(r["source_sha256"] for r in documents),
            "source_types": "|".join(sorted({r["source_type"] for r in documents})),
            "financial_periods": "|".join(sorted({str(r["period_end"]) for r in own if r.get("period_end")})),
            "fy_start": "|".join(sorted({str(r["period_start"]) for r in own if r.get("period_start")})) or "NOT_EXPLICITLY_NORMALIZED",
            "statement_basis": "|".join(sorted({r["statement_basis"] for r in own})),
            "audit_restated_status": "|".join(sorted({r["audit_status"] for r in own})),
            "units_scaling": "|".join(sorted({r["unit"] + ";presentation=" + r["presentation_rounding"] for r in own})),
            "source_available": bool(documents), "review_facts_count": len(own),
            "accepted_current_reference_facts_count": len(approved),
            "accepted_pit_facts_count": sum(bool(r.get("pit_usable")) for r in approved),
            "facts_extracted": len(own), "facts_accepted": len(approved),
            "facts_rejected": sum(r["review_status"] == "REJECTED" for r in own),
            "exact_rejection_reasons": "|".join(sorted({reason for r in own for reason in r["rejection_reasons"].split("|") if reason})) or ("IDENTITY_OR_DOCUMENT_REVIEW_REQUIRED" if not documents else ""),
            "remaining_missing_fields": "|".join(missing), "pit_usable": False,
            "pit_reason": "NO_VERIFIED_EXCHANGE_DISSEMINATION_CLOCK; BOARD_OR_REPORT_DATE_NOT_SUBSTITUTED",
            "exact_unresolved_fields": "|".join(missing),
            "exact_blocker": classify_residual_blocker(documents, own, approved, missing),
            "another_document_required": another_document_required(documents, own, approved),
            "exact_document_required": required_document(documents, own, approved),
            "needs_manual_acquisition": another_document_required(documents, own, approved),
            "next_action": "REVIEW_EXISTING_SUPPLIED_EVIDENCE" if documents else "SUPPLY_EXACT_OFFICIAL_SOURCE_DOCUMENT"}
        company_rows.append(row)
        if missing: residual.append(row)
    outputs["manual_company_audit.csv"] = csv_bytes(company_rows, list(company_rows[0]))
    outputs["still_missing_after_manual_ingest.csv"] = csv_bytes(residual, list(company_rows[0]))
    final_columns = ["issuer", "isin", "exchange", "exchange_code", "source_available", "review_facts_count",
        "accepted_current_reference_facts_count", "accepted_pit_facts_count", "exact_unresolved_fields",
        "exact_blocker", "another_document_required", "exact_document_required"]
    outputs["final_41_issuer_residual.csv"] = csv_bytes(company_rows, final_columns)
    for name, body in outputs.items():
        target = batch / name
        temporary = target.with_suffix(".tmp"); temporary.write_bytes(body); temporary.replace(target)
    existing = {r["isin"] for r in __import__('csv').DictReader((pack / "issuer_recovery_audit.csv").open()) if int(r["review_facts"]) > 0}
    recovered = {r["isin"] for r in accepted}
    report = {"documents": len(docs), "documents_identity_matched": sum(bool(r["isin"]) for r in audits),
        "document_audits": audits, "target_issuers": len(selected),
        "before": {"issuers_with_usable_recovery_facts": len({r["isin"] for r in prior_accepted}),
                   "review_facts": prior_review_count, "accepted_normalized_facts": len(prior_accepted),
                   "unresolved_companies_without_accepted_facts": len(selected) - len({r["isin"] for r in prior_accepted})},
        "after": {"issuers_with_review_facts": len({r["isin"] for r in all_facts}), "issuers_with_accepted_current_reference_facts": len(recovered), "review_facts": len(all_facts),
                  "accepted_normalized_facts": len(accepted), "newly_recovered_issuers": sorted(recovered-existing),
                  "unresolved_companies_without_accepted_facts": sum(not any(r["isin"] == t["isin"] for r in accepted) for t in selected),
                  "unresolved_companies_all_requested_fields": len(residual)},
        "current_reference_only": True, "pit_approved": False, "product_snapshot_promoted": False,
        "source_policy": "UPLOADED_STATUTORY_DOCUMENTS_ONLY; NO_SCREENER_FINANCIALS",
        "artifacts": {name:sha(body) for name,body in outputs.items()}}
    atomic_write_json(batch / "manual_validation.json", report)
    atomic_write_json(pack / "manual_latest.json", {"batch": batch.relative_to(pack).as_posix(), "report_sha256": sha((batch / "manual_validation.json").read_bytes())})
    # A stable residual at the user-requested location, all supporting files in
    # the same recovery pack. No prior raw/review/accepted snapshot is replaced.
    temp = pack / "still_missing_after_manual_ingest.tmp"
    temp.write_bytes(outputs["still_missing_after_manual_ingest.csv"])
    temp.replace(pack / "still_missing_after_manual_ingest.csv")
    return {k:v for k,v in report.items() if k != "document_audits"}


def load_current_reference(pack):
    """Verified current/reference-only input boundary for the recovery pipeline.

    Deliberately not a historical PIT provider or automatic snapshot promotion.
    """
    pointer = json.loads((pack / "manual_latest.json").read_text())
    batch = (pack / pointer["batch"]).resolve()
    if not batch.is_relative_to(pack.resolve()): raise ValueError("manual batch path escapes pack")
    report_path = batch / "manual_validation.json"
    if sha(report_path.read_bytes()) != pointer["report_sha256"]: raise ValueError("manual report hash mismatch")
    report = json.loads(report_path.read_text())
    for name, expected in report["artifacts"].items():
        path = (batch / name).resolve()
        if not path.is_relative_to(batch) or sha(path.read_bytes()) != expected: raise ValueError("manual artifact mismatch")
    known = {r["isin"] for r in targets(pack)}
    import csv
    rows = list(csv.DictReader((batch / "manual_current_reference_facts.csv").open(encoding="utf-8")))
    for row in rows:
        if row["isin"] not in known or row["review_status"] != "ACCEPTED_CURRENT_REFERENCE" or row["pit_usable"] != "False" or row["available_at"]:
            raise ValueError("manual current/PIT boundary violation")
        raw = pack / "raw" / (row["source_sha256"] + ".bin")
        if sha(raw.read_bytes()) != row["source_sha256"]: raise ValueError("manual evidence hash mismatch")
    return rows


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pack", type=Path, required=True)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--validate", action="store_true")
    args = p.parse_args()
    batch = ingest_archive(args.pack, args.archive)
    print(json.dumps(validate_batch(args.pack, batch), sort_keys=True) if args.validate else batch)
