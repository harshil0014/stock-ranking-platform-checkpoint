"""Build a safe, compact runtime cache from the accepted personalized evidence."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import numpy as np
import pandas as pd

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_research.personalized_official_actions import OfficialActionHistoryBook


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def build(runtime_root: Path, output: Path, audit_output: Path) -> dict:
    freeze = ROOT / "research/freezes/personalized-d499580"
    features = pd.read_csv(freeze / "features.csv.gz", low_memory=False)
    snapshot = load_company_fact_snapshot(resolve_company_fact_snapshot(runtime_root / "data/company_facts"))
    facts = snapshot.facts
    recovery = runtime_root / "research/data/ownership-recovery-20260925"
    terms_path = recovery / "resulting_equity_terms.csv"
    terms = pd.read_csv(terms_path)
    identities = set(features["isin"]) | set(terms.child_isin)
    identities = facts.loc[facts["isin"].isin(identities), ["isin", "ticker"]].drop_duplicates("isin")
    ledger_path = ROOT / "experiments/personalized-official-action-freeze/build-06/normalized_official_action_ledger.csv.gz"
    ledger = pd.read_csv(ledger_path, low_memory=False)
    repairs_path = ROOT / "experiments/personalized-data-freeze/build-01/terminal_repairs.csv"
    repairs = pd.read_csv(repairs_path)
    state_path = runtime_root / "data/live_market/accepted_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    live_path = runtime_root / "data/live_market" / state["bundle_path"] / "live_market.csv"
    live = pd.read_csv(live_path, low_memory=False)
    history_audit_path = recovery / "history_recovery_audit.csv"
    history_audit = pd.read_csv(history_audit_path)
    nominal = set(history_audit.loc[history_audit.raw_basis.eq("OFFICIAL_NOMINAL"), "ticker"])
    adjustment_dates = history_audit.dropna(subset=["provider_adjustment_through"]).set_index(
        "ticker").provider_adjustment_through.to_dict()
    book = OfficialActionHistoryBook(
        identities, runtime_root / "data/live_market/history_cache",
        runtime_root / "external_research_pack/corporate_actions/yahoo_secondary", ledger,
        as_of_date="2026-09-18", terminal_repairs=repairs,
        terminal_raw_prices=live[["isin", "trade_date", "latest_price"]], resulting_terms=terms,
        history_overlay=runtime_root / "external_research_pack/ownership_history_20260925",
        nominal_tickers=nominal, adjustment_dates=adjustment_dates,
    )
    names, offsets, arrays = [], [0], [[] for _ in range(5)]
    for identity, values in sorted(book.arrays.items()):
        names.append(identity)
        for target, value in zip(arrays, values):
            target.append(value)
        offsets.append(offsets[-1] + len(values[0]))
    dates = np.concatenate(arrays[0]).astype("datetime64[D]").astype(np.int32)
    errors = json.dumps(book.errors, sort_keys=True, separators=(",", ":")).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, identities=np.asarray(names), offsets=np.asarray(offsets, dtype=np.int64),
                        dates=dates, raw=np.concatenate(arrays[1]), adjusted=np.concatenate(arrays[2]),
                        nominal=np.concatenate(arrays[3]), factor=np.concatenate(arrays[4]),
                        errors_json=np.frombuffer(errors, dtype=np.uint8))
    audit = {
        "schema_version": "personalized_ui_runtime_pack_v1",
        "challenger_commit": "d4995807163bef1ec4b297179e6c54a59c71f390",
        "as_of_date": "2026-09-18", "identities": len(names), "errors": len(book.errors),
        "observations": int(offsets[-1]), "pack_sha256": digest(output), "pack_bytes": output.stat().st_size,
        "official_action_ledger": ledger_path.relative_to(ROOT).as_posix(),
        "resulting_terms": "research/data/ownership-recovery-20260925/resulting_equity_terms.csv",
        "source_hashes": {
            "freeze_manifest": digest(freeze / "manifest.json"), "features": digest(freeze / "features.csv.gz"),
            "official_action_ledger": digest(ledger_path), "terminal_repairs": digest(repairs_path),
            "accepted_live_state": digest(state_path), "live_market": digest(live_path),
            "history_recovery_audit": digest(history_audit_path), "resulting_terms": digest(terms_path),
        },
        "large_raw_data_policy": "NPZ runtime cache remains outside Git; this compact audit is versioned.",
    }
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "research/runtime/personalized-ui-d499580.npz")
    parser.add_argument("--audit-output", type=Path,
                        default=ROOT / "research/specifications/personalized_ui_runtime_pack_20260926.json")
    print(json.dumps(build(**vars(parser.parse_args())), indent=2))
