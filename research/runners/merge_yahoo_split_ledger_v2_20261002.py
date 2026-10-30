"""Merge exact-BSE Yahoo split recovery into a verified provider ledger V2."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v1"
RECOVERY = ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-bse-recovery-v1"
OUT = ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2"

def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def link_or_copy(source: Path, target: Path) -> str:
    try:
        os.link(source, target)
        return "HARDLINK"
    except OSError:
        shutil.copy2(source, target)
        return "COPY"

def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"fresh output required: {OUT}")
    OUT.mkdir(parents=True)
    raw = OUT / "raw"
    raw.mkdir()
    base_audit = pd.read_csv(BASE / "acquisition_audit.csv", low_memory=False)
    base_ledger = pd.read_csv(BASE / "split_ledger.csv", low_memory=False)
    recovery_audit = pd.read_csv(RECOVERY / "recovery_audit.csv", low_memory=False)
    recovery_ledger = pd.read_csv(RECOVERY / "split_ledger_recovered.csv", low_memory=False)
    base_summary = json.loads((BASE / "summary.json").read_text(encoding="utf-8"))

    if len(base_audit) != 3808 or base_audit["isin"].duplicated().any():
        raise ValueError("base audit identity contract drift")
    recovered = recovery_audit.loc[recovery_audit.status.eq("SUCCESS")].copy()
    if recovered["isin"].duplicated().any():
        raise ValueError("recovery audit contains duplicate successful identities")

    merged_audit = base_audit.copy()
    by_isin = merged_audit.set_index("isin", drop=False)
    for row in recovered.itertuples(index=False):
        if row.isin not in by_isin.index:
            raise ValueError(f"recovered ISIN absent from base audit: {row.isin}")
        idx = merged_audit.index[merged_audit["isin"].eq(row.isin)][0]
        merged_audit.loc[idx, "provider_symbol"] = row.provider_symbol
        merged_audit.loc[idx, "status"] = "SUCCESS"
        merged_audit.loc[idx, "event_count"] = int(row.event_count)
        merged_audit.loc[idx, "response_sha256"] = row.response_sha256
        merged_audit.loc[idx, "source_url"] = row.source_url
        merged_audit.loc[idx, "reason"] = None

    merged_ledger = pd.concat([base_ledger, recovery_ledger], ignore_index=True)
    event_key = ["isin", "event_date", "numerator", "denominator"]
    if merged_ledger.duplicated(event_key).any():
        duplicates = merged_ledger.loc[merged_ledger.duplicated(event_key, keep=False), event_key]
        raise ValueError(f"duplicate canonical split events after merge: {duplicates.to_dict('records')[:5]}")
    merged_ledger = merged_ledger.sort_values(["ticker", "event_date"], kind="stable")

    link_modes = {"HARDLINK": 0, "COPY": 0}
    success = merged_audit.loc[merged_audit.status.eq("SUCCESS")].copy()
    recovered_isins = set(recovered["isin"])
    for row in success.itertuples(index=False):
        symbol = str(row.provider_symbol)
        if row.isin in recovered_isins:
            source = RECOVERY / "raw" / f"{symbol}.json"
        else:
            source = BASE / "raw" / f"{symbol}.json"
        target = raw / f"{symbol}.json"
        if not source.is_file():
            raise FileNotFoundError(source)
        if digest(source) != str(row.response_sha256):
            raise ValueError(f"source response hash mismatch: {symbol}")
        mode = link_or_copy(source, target)
        link_modes[mode] += 1
        if digest(target) != str(row.response_sha256):
            raise ValueError(f"V2 raw response hash mismatch: {symbol}")

    merged_audit = merged_audit.sort_values(["ticker", "isin"], kind="stable")
    merged_audit.to_csv(OUT / "acquisition_audit.csv", index=False, lineterminator="\n")
    merged_ledger.to_csv(OUT / "split_ledger.csv", index=False, lineterminator="\n")

    status_counts = merged_audit.status.value_counts().sort_index().to_dict()
    summary = {
        "schema_version": "yahoo_split_ledger_v2_bse_official_symbol_recovery",
        "universe_count": int(len(merged_audit)),
        "status_counts": {k: int(v) for k, v in status_counts.items()},
        "split_event_count": int(len(merged_ledger)),
        "complex_ratio_count": int(
            (~merged_ledger.split_ratio.round().eq(merged_ledger.split_ratio)).sum()
        ),
        "audit_sha256": digest(OUT / "acquisition_audit.csv"),
        "ledger_sha256": digest(OUT / "split_ledger.csv"),
        "source": "Yahoo Finance chart splits; V2 recovers BSE failures with exact frozen official BSE symbols",
        "parameters": base_summary["parameters"],
        "base_ledger_sha256": digest(BASE / "split_ledger.csv"),
        "recovery_ledger_sha256": digest(RECOVERY / "split_ledger_recovered.csv"),
        "recovered_successful_identities": int(len(recovered)),
        "remaining_failed_identities": int(merged_audit.status.eq("FAILED").sum()),
        "raw_materialization": link_modes,
        "accepted_state_mutated": False,
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
