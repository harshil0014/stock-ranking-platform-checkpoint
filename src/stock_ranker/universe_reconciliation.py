"""Deterministic reconciliation of historical and final accepted universes."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class UniverseReconciliation:
    historical: pd.DataFrame
    final_additions: pd.DataFrame
    summary: dict


def _frame_sha(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return sha256(payload).hexdigest()


def reconcile_universes(historical: pd.DataFrame, final: pd.DataFrame) -> UniverseReconciliation:
    """Give every historical identity and every final addition an explicit disposition."""
    required = {"ticker", "isin", "company", "primary_exchange", "exchange_security_id"}
    for label, frame in (("historical", historical), ("final", final)):
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"{label} universe lacks columns: {sorted(missing)}")
        if frame["isin"].isna().any() or frame["isin"].duplicated().any():
            raise ValueError(f"{label} universe requires unique nonblank ISINs")
        if frame["ticker"].isna().any() or frame["ticker"].duplicated().any():
            raise ValueError(f"{label} universe requires unique nonblank tickers")

    historical_columns = [
        "ticker", "isin", "company", "primary_exchange", "exchange_security_id",
    ]
    historical_audit = historical[historical_columns].copy()
    final_identity = final[historical_columns].rename(columns={
        "ticker": "final_ticker", "isin": "final_isin", "company": "final_company",
    })
    historical_audit = historical_audit.merge(
        final_identity[["final_ticker", "final_isin", "final_company"]],
        left_on="isin", right_on="final_isin", how="left", validate="one_to_one",
    )
    exact = historical_audit["final_isin"].notna()
    historical_audit.loc[exact, "disposition"] = "RETAINED_EXACT_IDENTITY"
    historical_audit.loc[exact, "disposition_reason"] = (
        "The historical ISIN is present exactly once in the final accepted universe."
    )

    unresolved = historical_audit.loc[~exact, historical_columns].copy()
    replacements = unresolved.merge(
        final_identity,
        on=["primary_exchange", "exchange_security_id"],
        how="left", validate="one_to_one",
    )
    replacement_by_isin = replacements.set_index("isin")
    for index in historical_audit.index[~exact]:
        old_isin = historical_audit.at[index, "isin"]
        replacement = replacement_by_isin.loc[old_isin]
        if pd.notna(replacement["final_isin"]):
            historical_audit.at[index, "final_ticker"] = replacement["final_ticker"]
            historical_audit.at[index, "final_isin"] = replacement["final_isin"]
            historical_audit.at[index, "final_company"] = replacement["final_company"]
            historical_audit.at[index, "disposition"] = "SUPERSEDED_IDENTITY_RETAINED"
            historical_audit.at[index, "disposition_reason"] = (
                "The same exchange security ID remains accepted under a superseding ISIN."
            )
        else:
            historical_audit.at[index, "disposition"] = "EXCLUDED_FROM_FINAL_ACCEPTED_SNAPSHOT"
            historical_audit.at[index, "disposition_reason"] = (
                "No matching ISIN or same-exchange security ID exists in the final accepted "
                "snapshot; the historical identity is preserved here and is not silently ranked."
            )

    additions = final.loc[~final["isin"].isin(historical["isin"]), historical_columns].copy()
    replacement_final_isins = set(
        historical_audit.loc[
            historical_audit["disposition"].eq("SUPERSEDED_IDENTITY_RETAINED"), "final_isin"
        ].dropna()
    )
    additions["addition_disposition"] = additions["isin"].map(
        lambda value: "SUPERSEDING_IDENTITY" if value in replacement_final_isins else "NEW_FINAL_IDENTITY"
    )
    additions["addition_reason"] = additions["addition_disposition"].map({
        "SUPERSEDING_IDENTITY": "Replaces a historical ISIN under the same exchange security ID.",
        "NEW_FINAL_IDENTITY": "Present in the final accepted snapshot and absent from the historical ISIN set.",
    })

    disposition_counts = historical_audit["disposition"].value_counts().sort_index().to_dict()
    summary = {
        "schema_version": "historical_to_final_universe_reconciliation_v1",
        "historical_count": int(len(historical)),
        "final_count": int(len(final)),
        "historical_disposition_count": int(len(historical_audit)),
        "exact_retained_count": int(disposition_counts.get("RETAINED_EXACT_IDENTITY", 0)),
        "superseded_identity_count": int(disposition_counts.get("SUPERSEDED_IDENTITY_RETAINED", 0)),
        "excluded_historical_count": int(disposition_counts.get("EXCLUDED_FROM_FINAL_ACCEPTED_SNAPSHOT", 0)),
        "final_addition_count": int(len(additions)),
        "new_final_identity_count": int(additions["addition_disposition"].eq("NEW_FINAL_IDENTITY").sum()),
        "historical_counts_reconcile": len(historical_audit) == len(historical),
        "final_counts_reconcile": (
            disposition_counts.get("RETAINED_EXACT_IDENTITY", 0)
            + len(additions) == len(final)
        ),
        "missing_disposition_count": int(historical_audit["disposition"].isna().sum()),
        "duplicate_historical_isin_count": int(historical["isin"].duplicated().sum()),
        "duplicate_final_isin_count": int(final["isin"].duplicated().sum()),
        "historical_frame_sha256": _frame_sha(historical[historical_columns]),
        "final_frame_sha256": _frame_sha(final[historical_columns]),
    }
    if not summary["historical_counts_reconcile"] or not summary["final_counts_reconcile"]:
        raise ValueError("universe reconciliation counts do not balance")
    if summary["missing_disposition_count"]:
        raise ValueError("historical universe contains silent dispositions")
    return UniverseReconciliation(
        historical_audit.sort_values(["disposition", "ticker"], kind="stable").reset_index(drop=True),
        additions.sort_values(["addition_disposition", "ticker"], kind="stable").reset_index(drop=True),
        summary,
    )


def write_reconciliation(result: UniverseReconciliation, output: Path) -> dict:
    if output.exists():
        raise ValueError("fresh output directory required")
    output.mkdir(parents=True)
    result.historical.to_csv(output / "historical_universe_dispositions.csv", index=False, lineterminator="\n")
    result.final_additions.to_csv(output / "final_universe_additions.csv", index=False, lineterminator="\n")
    (output / "summary.json").write_text(
        json.dumps(result.summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifacts = []
    for path in sorted(output.iterdir()):
        artifacts.append({
            "path": path.name,
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        })
    fingerprint = sha256(json.dumps(
        artifacts, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    manifest = {
        "schema_version": "historical_to_final_universe_reconciliation_manifest_v1",
        "fingerprint": fingerprint,
        "artifacts": artifacts,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result.summary | {"fingerprint": fingerprint}
