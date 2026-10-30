from pathlib import Path
import sys

ROOT = Path(r"C:\Users\Harshil\Downloads\stock-ranking-platform-fresh-canonical-verified")
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from research.runners.build_deep_personalized_panel_20261002 import run

SHARDS = {
    "A": ("2015-03-31","2015-06-30","2015-09-30","2015-12-31","2016-03-31","2016-06-30","2016-09-30","2017-03-31","2017-06-30","2017-09-30"),
    "B": ("2018-03-31","2018-06-30","2018-09-30","2019-03-31","2019-06-30","2019-09-30","2020-03-31","2020-06-30","2020-09-30","2020-12-31"),
    "C": ("2021-03-31","2021-06-30","2021-09-30","2021-12-31","2022-03-31","2022-09-30","2023-03-31","2023-09-30","2024-03-31"),
    "D": ("2024-06-30","2024-09-30","2024-12-31","2025-01-31","2025-02-28","2025-04-30","2025-05-31","2025-07-31","2025-08-31"),
}

name = sys.argv[1].upper()
if name not in SHARDS:
    raise SystemExit(f"choose one of {sorted(SHARDS)}")

run(
    ROOT / f"experiments/personalized-deep-history-20261002/real-panel-v12-v2-shard{name}",
    ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2",
    SHARDS[name],
)
