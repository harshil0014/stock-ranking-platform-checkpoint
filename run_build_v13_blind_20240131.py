from pathlib import Path
import sys

ROOT=Path(r"C:\Users\Harshil\Downloads\stock-ranking-platform-fresh-canonical-verified")
sys.path[:0]=[str(ROOT),str(ROOT/"src")]

from research.runners.build_deep_personalized_panel_20261002 import run

run(
    ROOT/"experiments/personalized-v13-20261002/blind-2024-01-31",
    ROOT/"experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2",
    ("2024-01-31",),
)
