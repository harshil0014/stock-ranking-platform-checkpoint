"""Railway entrypoint with explicit diagnostics for professor deployment."""
from __future__ import annotations

import os
import subprocess
import sys
import traceback


def main() -> int:
    print("RAILWAY_ENTRYPOINT_START", flush=True)
    print(f"PORT={os.environ.get('PORT', '<unset>')}", flush=True)
    print(f"DATA_ROOT={os.environ.get('STOCK_RANKER_DATA_ROOT', '<unset>')}", flush=True)
    print(f"RESEARCH_ROOT={os.environ.get('STOCK_RANKER_RESEARCH_ROOT', '<unset>')}", flush=True)
    try:
        print("BOOTSTRAP_START", flush=True)
        subprocess.run(
            [sys.executable, "marketdata/runners/bootstrap_railway_runtime.py"],
            check=True,
        )
        print("BOOTSTRAP_OK", flush=True)

        print("WEBAPP_IMPORT_START", flush=True)
        from stock_ranker import webapp
        print("WEBAPP_IMPORT_OK", flush=True)

        port = int(os.environ.get("PORT", "8765"))
        print(f"WEBAPP_START host=0.0.0.0 port={port}", flush=True)
        return int(webapp.main(["--host", "0.0.0.0", "--port", str(port), "--no-auto-refresh"]))
    except BaseException:
        print("RAILWAY_ENTRYPOINT_FATAL", flush=True)
        traceback.print_exc()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
