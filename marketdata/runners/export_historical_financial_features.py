"""Offline historical financial feature export. Never promotes production state."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from stock_research.historical_financial_features import export_historical_financial_features


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(export_historical_financial_features(args.output))
