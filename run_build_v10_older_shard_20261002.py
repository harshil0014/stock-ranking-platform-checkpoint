from pathlib import Path
import sys

ROOT = Path(r"C:\Users\Harshil\Downloads\stock-ranking-platform-fresh-canonical-verified")
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from research.runners.build_deep_personalized_panel_20261002 import run

DATES = (
    "2015-03-31", "2015-06-30", "2015-09-30", "2015-12-31",
    "2016-03-31", "2016-09-30",
    "2017-03-31", "2017-09-30",
    "2018-03-31", "2018-09-30",
    "2019-03-31", "2019-09-30",
)

run(
    ROOT / "experiments/personalized-deep-history-20261002/real-panel-v10-older-shard",
    ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v1",
    DATES,
)
