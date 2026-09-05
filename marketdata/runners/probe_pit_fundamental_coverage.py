"""Run a gated official-NSE point-in-time fundamental coverage probe."""

from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from marketdata.runners.acquire_nse_annual_reports import acquire
from marketdata.runners.audit_nse_annual_reports import audit
from stock_ranker.pit_fundamental_probe import (
    PITFundamentalProbeConfig,
    assess_annual_report_probe,
    select_probe_cohort,
    summarize_structured_fact_coverage,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )


def run_probe(
    company_facts_path: Path,
    reviewed_mapping_path: Path,
    financial_facts_path: Path,
    output: Path,
    config: PITFundamentalProbeConfig,
    evidence_root: Path | None = None,
) -> dict[str, object]:
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    output.mkdir(parents=True)
    facts = pd.read_csv(company_facts_path, low_memory=False)
    cohort = select_probe_cohort(facts, config.sample_size)
    selected_tickers = set(cohort["ticker"].astype(str))
    structured_parts = []
    for chunk in pd.read_csv(financial_facts_path, chunksize=250_000, low_memory=False):
        selected = chunk.loc[chunk["ticker"].astype(str).isin(selected_tickers)]
        if not selected.empty:
            structured_parts.append(selected)
    structured = pd.concat(structured_parts, ignore_index=True) if structured_parts else pd.DataFrame()
    structured_summary = summarize_structured_fact_coverage(
        structured, cohort, config.ranking_date,
    )
    universe_path = output / "probe_universe.csv"
    acquisition_universe = cohort.rename(columns={"product_sector": "sector"})
    acquisition_universe.to_csv(
        universe_path, index=False, lineterminator="\n", encoding="utf-8"
    )
    cutoff = datetime.fromisoformat(config.ranking_date).replace(
        hour=23, minute=59, second=59, tzinfo=ZoneInfo("Asia/Kolkata")
    )
    start_year, end_short = config.financial_year.split("-")
    end_year = str(int(start_year[:2]) * 100 + int(end_short))
    if evidence_root is None:
        acquisition = output / "annual_reports"
        audit_root = output / "annual_report_audit"
        acquire(
            universe_path, acquisition, None, cutoff=cutoff,
            from_year=start_year, to_year=end_year,
        )
        audit(acquisition, audit_root)
        evidence_mode = "FRESH_OFFICIAL_NSE_ACQUISITION"
    else:
        acquisition = evidence_root / "annual_reports"
        audit_root = evidence_root / "annual_report_audit"
        if not (acquisition / "annual_report_provenance.json").is_file():
            raise ValueError("reused evidence lacks annual-report provenance")
        if not (audit_root / "candidate_audit.json").is_file():
            raise ValueError("reused evidence lacks candidate audit")
        evidence_mode = "HASHED_EXISTING_PROBE_EVIDENCE"
    rows, summary = assess_annual_report_probe(
        cohort, acquisition, audit_root, reviewed_mapping_path,
    )
    reviewed_rate = float(summary["reviewed_complete_rate"])
    gate = reviewed_rate >= config.minimum_reviewed_complete_rate
    summary.update({
        "ranking_date": config.ranking_date,
        "financial_year": config.financial_year,
        "sample_selection": "ascending SHA-256 of exact NSE-master ISIN",
        "minimum_reviewed_complete_rate": config.minimum_reviewed_complete_rate,
        "scale_gate_passed": gate,
        "scale_gate_reason": (
            "Reviewed direct standalone disclosures meet the preregistered probe threshold."
            if gate else
            "Probe not scaled: reviewed complete PIT-safe records are below the threshold; "
            "unreviewed text candidates are evidence work items, not model inputs."
        ),
        "no_imputation": True,
        "v2_formula_changes": False,
        "structured_xbrl_coverage": structured_summary,
        "evidence_mode": evidence_mode,
        "evidence_root": str((evidence_root or output).resolve()),
        "annual_report_provenance_sha256": sha256(
            (acquisition / "annual_report_provenance.json").read_bytes()
        ).hexdigest(),
        "candidate_audit_sha256": sha256(
            (audit_root / "candidate_audit.json").read_bytes()
        ).hexdigest(),
    })
    rows.to_csv(output / "coverage_matrix.csv", index=False, lineterminator="\n", encoding="utf-8")
    _write_json(output / "probe_summary.json", summary)
    inventory = []
    for path in sorted(item for item in output.rglob("*") if item.is_file()):
        if path.name == "artifact_inventory.json":
            continue
        content = path.read_bytes()
        inventory.append({
            "path": path.relative_to(output).as_posix(),
            "size": len(content),
            "sha256": sha256(content).hexdigest(),
        })
    _write_json(output / "artifact_inventory.json", inventory)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe strict PIT-safe Research V2 fundamental coverage on 50-100 NSE securities."
    )
    parser.add_argument("--company-facts", type=Path, required=True)
    parser.add_argument("--reviewed-mapping", type=Path, required=True)
    parser.add_argument("--financial-facts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument("--ranking-date", default="2026-08-21")
    parser.add_argument("--financial-year", default="2025-26")
    parser.add_argument("--minimum-reviewed-complete-rate", type=float, default=0.20)
    parser.add_argument("--reuse-evidence-root", type=Path)
    args = parser.parse_args(argv)
    try:
        config = PITFundamentalProbeConfig(
            sample_size=args.sample_size,
            ranking_date=args.ranking_date,
            financial_year=args.financial_year,
            minimum_reviewed_complete_rate=args.minimum_reviewed_complete_rate,
        )
        print(json.dumps(run_probe(
            args.company_facts, args.reviewed_mapping, args.financial_facts,
            args.output, config, args.reuse_evidence_root,
        ), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"PIT fundamental coverage probe failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
