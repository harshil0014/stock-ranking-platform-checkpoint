"""Read-only localhost HTTP smoke against a selected accepted company-fact store."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import threading
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from stock_ranker import live_website
from stock_ranker.webapp import create_server
from stock_ranker.data_state import atomic_write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    live_website.COMPANY_FACT_STATE_ROOT = args.state_root.resolve()
    server = create_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    result = {}
    try:
        for path in ("/", "/api/live/company-facts-coverage", "/api/live/stock?ticker=RELIANCE",
                     "/api/live/stock?ticker=BSE-500051", "/api/live/stock?ticker=BSE-526477"):
            with urlopen(base + path, timeout=180) as response:
                raw = response.read()
                assert response.status == 200
            evidence = {"status": 200, "bytes": len(raw)}
            if "stock?" in path:
                payload = json.loads(raw)
                sections = payload["company_facts"]
                checked = 0
                for section in sections.values():
                    if not isinstance(section, dict) or "values" not in section:
                        continue
                    assert set(section["values"]) == set(section["field_states"])
                    assert all(v["state"] and v["reason"] for v in section["field_states"].values())
                    checked += len(section["values"])
                assert checked > 0
                evidence["fields_with_explicit_states"] = checked
            result[path] = evidence
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    atomic_write_json(args.output, result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
