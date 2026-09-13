from pathlib import Path
from datetime import datetime
import shutil
import re

path = Path(r"marketdata\runners\backfill_bse_history.py")
text = path.read_text(encoding="utf-8")

if "\nimport re\n" not in "\n" + text:
    if "import argparse\n" not in text:
        raise SystemExit("Could not locate argparse import; no changes made.")
    text = text.replace("import argparse\n", "import argparse\nimport re\n", 1)

old_select = """        pending = bse.loc[~already_covered_mask].copy()
        if not args.all:
            pending = pending.head(args.limit).copy()
"""

new_select = """        pending = bse.loc[~already_covered_mask].copy()

        requested_tickers: list[str] = []
        if args.tickers_file is not None:
            tickers_path = Path(args.tickers_file).resolve()
            if not tickers_path.exists():
                raise FileNotFoundError(f"tickers file does not exist: {tickers_path}")
            requested_tickers = [
                line.strip()
                for line in tickers_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
            requested_tickers = list(dict.fromkeys(requested_tickers))
            invalid = [ticker for ticker in requested_tickers if not re.fullmatch(r"BSE-\\d+", ticker)]
            if invalid:
                raise ValueError(
                    "tickers file contains invalid BSE ticker(s): " + ", ".join(invalid[:10])
                )
            requested_set = set(requested_tickers)
            pending = pending.loc[pending["ticker"].astype(str).isin(requested_set)].copy()
        elif not args.all:
            pending = pending.head(args.limit).copy()
"""

if old_select not in text:
    raise SystemExit("Expected pending-selection block not found; no changes made.")
text = text.replace(old_select, new_select, 1)

old_summary = """            "selected_this_run": int(len(pending)),
            "identity_contract": "OFFICIAL_BSE_TRADE_RECORD + numeric scrip code + exact ISIN",
"""

new_summary = """            "selected_this_run": int(len(pending)),
            "requested_ticker_count": int(len(requested_tickers)),
            "requested_tickers_already_covered": int(
                len(set(requested_tickers) & set(bse.loc[already_covered_mask, "ticker"].astype(str)))
            ) if requested_tickers else 0,
            "requested_tickers_not_in_bse_universe": int(
                len(set(requested_tickers) - set(bse["ticker"].astype(str)))
            ) if requested_tickers else 0,
            "identity_contract": "OFFICIAL_BSE_TRADE_RECORD + numeric scrip code + exact ISIN",
"""

if old_summary not in text:
    raise SystemExit("Expected summary block not found; no changes made.")
text = text.replace(old_summary, new_summary, 1)

old_parser = """    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--workers", type=int, default=2)
"""

new_parser = """    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--tickers-file",
        type=Path,
        default=None,
        help="Optional UTF-8 file with one exact BSE-<scrip> ticker per line; only those pending histories are selected.",
    )
    parser.add_argument("--workers", type=int, default=2)
"""

if old_parser not in text:
    raise SystemExit("Expected parser block not found; no changes made.")
text = text.replace(old_parser, new_parser, 1)

old_main = """    if args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    if not 1 <= args.workers <= 6:
"""

new_main = """    if args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    if args.all and args.tickers_file is not None:
        raise SystemExit("--all and --tickers-file are mutually exclusive")
    if not 1 <= args.workers <= 6:
"""

if old_main not in text:
    raise SystemExit("Expected main-validation block not found; no changes made.")
text = text.replace(old_main, new_main, 1)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_dir = Path("local_backups") / f"targeted_bse_history_backfill_{stamp}"
backup_dir.mkdir(parents=True, exist_ok=False)
backup = backup_dir / path.name
shutil.copy2(path, backup)

path.write_text(text, encoding="utf-8", newline="\n")

print(f"Patched: {path}")
print(f"Backup:  {backup}")
print("Added: --tickers-file targeted pending-history selection.")
print("Ranking logic and history validation were not changed.")
