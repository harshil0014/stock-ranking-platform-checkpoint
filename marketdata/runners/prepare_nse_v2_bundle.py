"""Prepare a deterministic offline real Research V2 bundle from frozen inputs."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from stock_ranker.real_research_v2 import prepare_real_research_v2_bundle  # noqa: E402

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--raw-root",type=Path,required=True)
    parser.add_argument("--baseline-root",type=Path,required=True)
    parser.add_argument("--mapping",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--annual-report-acquisition-root",type=Path)
    parser.add_argument("--annual-report-audit-root",type=Path)
    parser.add_argument("--annual-report-mapping",type=Path)
    args=parser.parse_args(argv)
    try:
        print(prepare_real_research_v2_bundle(
            args.raw_root,args.baseline_root,args.mapping,args.output,
            args.annual_report_acquisition_root,args.annual_report_audit_root,
            args.annual_report_mapping,
        ))
        return 0
    except Exception as exc:
        print(f"preparation failed: {exc}",file=sys.stderr); return 1
if __name__=="__main__": raise SystemExit(main())
