"""Build the largest existing-data, date-specific historical research panel."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
from stock_research.expanded_historical_panel import run

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    print(run(args.output))
