"""Resumable exact-code BSE action acquisition for 2026-09-19..30."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
import pandas as pd
import requests
from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from marketdata.runners.download_bse_structured_corporate_actions import normalize_row

OUT = ROOT / "experiments/personalized-v13-20261002/prospective-2025-09-30/official_actions"
START, END = date(2026, 9, 19), date(2026, 9, 30)
API = "https://api.bseindia.com/BseIndiaAPI/api/DefaultData/w"
HOME = "https://www.bseindia.com/corporates/corporates_act.html"
LOCAL = threading.local()


def sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def session(code: str) -> requests.Session:
    if not hasattr(LOCAL, "session"):
        value = requests.Session()
        value.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
                              "Accept": "application/json, text/plain, */*", "Origin": "https://www.bseindia.com"})
        # The public HTML shell may independently return 403 even while the
        # exact-code JSON endpoint returns a valid signed exchange response.
        value.get(f"{HOME}?scripcode={code}", timeout=25)
        LOCAL.session = value
    return LOCAL.session


def fetch(code: str) -> dict:
    raw_path = OUT / "raw" / f"{code}.json"
    if raw_path.exists():
        payload = raw_path.read_bytes()
    else:
        problem = "unknown"
        for attempt in range(3):
            try:
                connection = session(code)
                response = connection.get(API, params={"ddlcategorys": "E", "ddlindustrys": "",
                    "segment": "0", "strSearch": "D", "Fdate": "20260919",
                    "TDate": "20260930", "scripcode": code},
                    headers={"Referer": f"{HOME}?scripcode={code}"}, timeout=25)
                response.raise_for_status()
                payload = response.content
                data = json.loads(payload)
                if not isinstance(data, list):
                    raise ValueError("BSE result is not a list")
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_bytes(payload)
                break
            except Exception as exc:
                problem = f"{type(exc).__name__}: {exc}"
                if hasattr(LOCAL, "session"):
                    del LOCAL.session
                time.sleep(attempt + 1)
        else:
            return {"bse_code": code, "status": "FAILED", "reason": problem}
    try:
        data = json.loads(payload)
        if not isinstance(data, list):
            raise ValueError("BSE result is not a list")
        rows = [normalize_row(item, code, (START, END)) for item in data]
        relevant = [row for row in rows if row["event_type"] in
                    {"SPLIT", "BONUS", "RIGHTS", "MERGER_DEMERGER_SCHEME"}]
        return {"bse_code": code, "status": "SUCCESS", "source_sha256": sha(payload),
                "rows": len(rows), "relevant": len(relevant), "events": relevant}
    except Exception as exc:
        return {"bse_code": code, "status": "FAILED", "source_sha256": sha(payload),
                "reason": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    codes = sorted(facts.loc[facts.primary_exchange.eq("BSE"), "ticker"].str.replace("BSE-", "", regex=False).unique())
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        jobs = {executor.submit(fetch, code): code for code in codes}
        for index, future in enumerate(as_completed(jobs), 1):
            results.append(future.result())
            if index % 200 == 0:
                print(json.dumps({"completed": index, "total": len(codes),
                                  "success": sum(r["status"] == "SUCCESS" for r in results)}), flush=True)
    simple = [{key: value for key, value in row.items() if key != "events"} for row in results]
    pd.DataFrame(simple).sort_values("bse_code").to_csv(OUT / "bse_acquisition_audit.csv", index=False)
    events = [dict(item, bse_code=row["bse_code"], response_sha256=row.get("source_sha256"))
              for row in results for item in row.get("events", [])]
    pd.DataFrame(events).to_csv(OUT / "bse_recent_events.csv", index=False)
    summary = {"schema": "v13_prospective_bse_actions_v1",
               "retrieved_at": datetime.now(timezone.utc).isoformat(),
               "start": START.isoformat(), "end": END.isoformat(),
               "codes": len(codes), "success": sum(r["status"] == "SUCCESS" for r in results),
               "failed": sum(r["status"] != "SUCCESS" for r in results),
               "relevant_events": len(events), "source": API}
    (OUT / "bse_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
