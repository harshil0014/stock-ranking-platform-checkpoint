"""Run the isolated, user-authorized vendor-restatement-risk experiment."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from stock_research.vendor_risk_experiment import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(run(args.output))
