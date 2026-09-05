"""Audit user-supplied Screener Premium CSVs as non-PIT reference evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot  # noqa: E402
from stock_ranker.data_state import atomic_write_json  # noqa: E402
from stock_ranker.screener_premium_reference import exact_isin_coverage, reconcile_screener_exports  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exports", nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    result = reconcile_screener_exports(args.exports)
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    matches, coverage = exact_isin_coverage(result.rows, facts)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    result.rows.to_csv(args.output_dir / "reference_rows.csv", index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")
    result.conflicts.to_csv(args.output_dir / "conflicts.csv", index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")
    matches.to_csv(args.output_dir / "identity_matches.csv", index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")
    manifest = dict(result.manifest)
    manifest["company_fact_coverage"] = coverage
    atomic_write_json(args.output_dir / "manifest.json", manifest)
    print(f"Audited {len(result.rows)} exact-ISIN reference rows; {coverage['exact_isin_match_count']} matched; {len(result.conflicts)} conflicts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
