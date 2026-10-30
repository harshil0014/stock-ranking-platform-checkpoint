from pathlib import Path
from research.runners.build_deep_personalized_panel_20261002 import run, ROOT
dates=('2016-06-30','2017-06-30','2018-06-30','2019-06-30','2020-03-31','2020-06-30','2020-09-30','2020-12-31','2021-03-31','2021-06-30','2021-09-30','2021-12-31','2022-03-31','2022-09-30','2023-03-31','2023-09-30','2024-03-31','2024-06-30','2024-09-30','2024-12-31','2025-01-31','2025-02-28','2025-04-30','2025-05-31','2025-07-31','2025-08-31')
run(ROOT/'experiments/personalized-deep-history-20261002/real-panel-v8', ROOT/'experiments/personalized-deep-history-20261002/yahoo-split-ledger-v1', dates)
