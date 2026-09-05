from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from marketdata.runners.acquire_nse_annual_reports import (  # noqa: E402
    download_selected_metadata_reports,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download a bounded official NSE annual-report batch from frozen PIT metadata."
    )
    parser.add_argument("--metadata-root", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = download_selected_metadata_reports(
            args.metadata_root, args.batch, args.output, resume=args.resume,
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if summary["failed_count"] == 0 else 1
    except Exception as exc:
        print(f"annual-report batch download failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
