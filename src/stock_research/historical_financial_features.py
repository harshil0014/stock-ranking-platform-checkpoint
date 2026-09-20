"""Local, versioned financial observations; filing clocks never backdate values.

Modern vendor workbooks are usable from their recorded observation time, not
automatically from the original filing time. Historical as-published verification
must be supplied by a separate accounting-evidence route; this exporter cannot
assert it on the strength of an exchange timestamp alone.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd

from stock_ranker.screener_statements import _candidate_records
from stock_ranker.screener_historical_fundamentals import (
    _XlsxCells, _cell, _excel_date, inspect_screener_historical_workbook,
)
from stock_research.platform import validate_feature_evidence

SECTIONS = {
    "annual": (16, {17: "sales", 18: "raw_material", 19: "inventory_change",
        20: "power_fuel", 21: "manufacturing", 22: "employee_cost", 23: "selling_admin",
        24: "other_expenses", 25: "other_income", 26: "depreciation", 27: "interest",
        28: "pbt", 29: "tax", 30: "pat", 31: "dividends"}),
    "quarterly": (41, {42: "sales", 43: "expenses", 44: "other_income", 45: "depreciation",
        46: "interest", 47: "pbt", 48: "tax", 49: "pat", 50: "operating_profit"}),
    "balance": (56, {57: "equity_capital", 58: "reserves", 59: "borrowings",
        60: "other_liabilities", 61: "total_liabilities", 62: "fixed_assets", 63: "cwip",
        64: "investments", 65: "other_assets", 66: "total_assets", 67: "receivables",
        68: "inventory", 69: "cash_bank"}),
    "cash_flow": (81, {82: "operating_cash_flow", 83: "investing_cash_flow",
        84: "financing_cash_flow", 85: "net_cash_flow"}),
}


def usable_observation_time(observed_at: str, period_end: str) -> str:
    value = pd.Timestamp(observed_at)
    if pd.isna(value) or value.tzinfo is None:
        raise ValueError("vendor observation requires an explicit timezone")
    if pd.Timestamp(period_end).date() > value.date():
        raise ValueError("financial period ends after vendor observation")
    return value.tz_convert("UTC").isoformat()


def to_research_evidence(observations: pd.DataFrame, *, ranking_date: str,
                         sectors_by_isin: dict[str, str], mode: str) -> pd.DataFrame:
    """Explicit current/reference bridge. No implicit historical admission."""
    if mode != "current":
        raise ValueError("vendor history lacks original-as-published verification; historical training blocked")
    cutoff = pd.Timestamp(ranking_date, tz="Asia/Kolkata") + pd.Timedelta(hours=15, minutes=30)
    frame = observations.loc[pd.to_datetime(observations.available_at, utc=True).le(cutoff)].copy()
    frame["sector"] = frame["isin"].map(sectors_by_isin)
    frame = frame.dropna(subset=["sector"])
    # Conflicting values at the same known vintage are never hash-tiebroken.
    conflict = frame.groupby(["isin", "feature", "period_end", "available_at"]).value.nunique()
    if conflict.gt(1).any():
        raise ValueError("conflicting financial values at the same vintage")
    frame = frame.sort_values(["period_end", "available_at", "source_hash"], kind="stable")
    frame = frame.drop_duplicates(["isin", "feature"], keep="last")
    frame["as_of_date"] = ranking_date
    frame["availability_status"] = "current_only"
    frame["source_id"] = "screener_vendor_historical_reference"
    frame["evidence_fingerprint"] = frame["source_hash"]
    return validate_feature_evidence(frame, mode=mode)


def derived_ratios(rows: list[dict]) -> list[dict]:
    """Same-workbook, same-period component ratios; never statutory ROCE."""
    by_period = {}
    for row in rows:
        by_period.setdefault(row["period_end"], {})[row["feature"]] = row
    result = []
    for period, group in sorted(by_period.items()):
        definitions = {
            "derived_net_margin": (["annual_pat"], ["annual_sales"]),
            "derived_debt_to_equity": (["balance_borrowings"], ["balance_equity_capital", "balance_reserves"]),
            "derived_roe_closing_equity": (["annual_pat"], ["balance_equity_capital", "balance_reserves"]),
            "derived_cfo_to_assets": (["cash_flow_operating_cash_flow"], ["balance_total_assets"]),
        }
        for feature, (numerators, denominators) in definitions.items():
            names = numerators + denominators
            if not all(name in group for name in names):
                continue
            denominator = sum(group[n]["value"] for n in denominators)
            if denominator <= 0:
                continue
            row = dict(group[numerators[0]])
            row.update(feature=feature, section="derived", unit="ratio",
                       value=sum(group[n]["value"] for n in numerators) / denominator,
                       source_cell=";".join(group[n]["source_cell"] for n in names))
            result.append(row)
    return result


def official_clock_catalogue(root: Path) -> pd.DataFrame:
    """Retain accepted official facts and clocks without borrowing vendor values."""
    state = json.loads((root / "accepted_state.json").read_text())
    batch = (root / state["accepted_batch"]).resolve()
    if root.resolve() not in batch.parents:
        raise ValueError("official evidence escapes provider root")
    manifest = json.loads((batch / "manifest.json").read_text())
    if manifest["fingerprint"] != state["fingerprint"]:
        raise ValueError("official manifest fingerprint mismatch")
    for name in ("financial_facts.csv", "raw_evidence_inventory.csv"):
        if sha256((batch / name).read_bytes()).hexdigest() != manifest["artifacts"][name]:
            raise ValueError(f"official artifact hash mismatch: {name}")
    parts = []
    for frame in pd.read_csv(batch / "financial_facts.csv", chunksize=100000, low_memory=False):
        keep = frame.statement_basis.eq("STANDALONE") & ~frame.canonical_concept.str.startswith("unknown:")
        parts.append(frame.loc[keep].copy())
    facts = pd.concat(parts, ignore_index=True)
    inventory = pd.read_csv(batch / "raw_evidence_inventory.csv")
    valid = set()
    wanted = set(facts.source_sha256)
    for row in inventory.loc[inventory.sha256.isin(wanted)].to_dict("records"):
        path = (batch / row["relative_path"]).resolve()
        if batch not in path.parents or not path.is_file():
            continue
        if path.stat().st_size == row["size"] and sha256(path.read_bytes()).hexdigest() == row["sha256"]:
            valid.add(row["sha256"])
    facts["clock_evidence_status"] = "UNVERIFIED"
    times = pd.to_datetime(facts.available_at, utc=True, errors="coerce", format="mixed")
    dates = pd.to_datetime(facts.period_end, utc=True, errors="coerce")
    official = facts.source_url.map(lambda u: urlparse(str(u)).hostname in {
        "nsearchives.nseindia.com", "archives.nseindia.com", "www.nseindia.com", "www.bseindia.com", "www.bseindia.in"})
    aware = facts.available_at.astype(str).str.contains(r"(?:Z|[+-]\d{2}:\d{2})$", regex=True)
    valid_rows = facts.source_sha256.isin(valid) & official & aware & times.notna() & dates.notna() & times.ge(dates)
    facts.loc[valid_rows, "clock_evidence_status"] = "HASH_VERIFIED_OFFICIAL_FACT_CLOCK"
    return facts.sort_values(["isin", "period_end", "available_at", "source_sha256", "context_id", "source_concept"], kind="stable")


def export_historical_financial_features(output: str | Path) -> dict:
    destination = Path(output)
    if destination.exists():
        raise ValueError("output must be fresh")
    records = _candidate_records()
    unique = {}
    for record, path, manifest in records:
        unique.setdefault((str(record["isin"]), str(record["workbook_sha256"])), (record, path, manifest))
    rows, rejected = [], []
    for (isin, digest), (record, path, manifest) in sorted(unique.items()):
        try:
            if sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("workbook hash mismatch")
            inspect_screener_historical_workbook(path)
            with _XlsxCells(path) as book:
                cells = book.sheet("Data Sheet")
            pending = []
            for section, (date_row, fields) in SECTIONS.items():
                for column in "BCDEFGHIJK":
                    try:
                        period = _excel_date(_cell(cells, f"{column}{date_row}")).isoformat()
                    except (ValueError, TypeError):
                        continue
                    observed = usable_observation_time(str(record["source_observed_at"]), period)
                    for number, name in fields.items():
                        raw = _cell(cells, f"{column}{number}")
                        if raw is None or raw == "":
                            continue
                        try:
                            value = float(raw)
                        except (ValueError, TypeError):
                            continue
                        if not np.isfinite(value):
                            continue
                        pending.append({"isin": isin, "ticker": record["ticker"],
                            "period_end": period, "section": section, "feature": f"{section}_{name}",
                            "value": value, "unit": "INR_crore", "reporting_basis": "STANDALONE",
                            "available_at": observed, "source_hash": digest,
                            "source_path": path.as_posix(), "source_cell": f"Data Sheet!{column}{number}",
                            "original_public_value_verified": False,
                            "historical_status": "VENDOR_VINTAGE_NOT_VERIFIED"})
            rows.extend(pending + derived_ratios(pending))
        except (ValueError, OSError) as exc:
            rejected.append({"isin": isin, "source_hash": digest, "reason": str(exc)})
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("no valid financial observations")
    # Retain vintage differences as conflicts, not arbitrary winner selection.
    keys = ["isin", "period_end", "feature"]
    conflicts = frame.groupby(keys, sort=True).value.nunique().reset_index(name="distinct_values")
    conflicts = conflicts.loc[conflicts.distinct_values.gt(1)]
    frame = frame.sort_values([*keys, "available_at", "source_hash"], kind="stable")
    official = official_clock_catalogue(Path(__file__).resolve().parents[2] / "data/company_facts/providers/official_exchange")
    clocks = official.loc[official.clock_evidence_status.eq("HASH_VERIFIED_OFFICIAL_FACT_CLOCK")].groupby(
        ["isin", "period_end"], sort=True
    ).available_at.min().rename("official_fact_available_at").reset_index()
    clock_links = frame[["isin", "period_end", "available_at"]].drop_duplicates().merge(clocks, on=["isin", "period_end"], how="left", validate="many_to_one")
    clock_links["vendor_original_value_verified"] = False
    clock_links["status"] = np.where(clock_links.official_fact_available_at.notna(), "OFFICIAL_PERIOD_CLOCK_ONLY_NOT_VENDOR_VINTAGE_PROOF", "NO_MATCHING_VERIFIED_OFFICIAL_FACT_CLOCK")
    summary = {"schema_version": "vendor_financial_observations_v1",
        "workbooks": len(unique), "rejected_workbooks": len(rejected),
        "issuers": int(frame['isin'].nunique()), "observations": len(frame),
        "features": int(frame.feature.nunique()), "conflicting_keys": len(conflicts),
        "historical_pit_promotions": 0,
        "official_standalone_fact_rows": len(official),
        "official_hash_verified_clock_rows": int(official.clock_evidence_status.eq("HASH_VERIFIED_OFFICIAL_FACT_CLOCK").sum()),
        "periods_with_official_fact_clock": int(clock_links.official_fact_available_at.notna().sum()),
        "reason": "Official filing clocks alone do not establish the vintage of modern vendor values"}
    destination.mkdir(parents=True)
    for name, data in [("observations.csv", frame), ("conflicts.csv", conflicts),
                       ("official_fact_clock_catalogue.csv", official), ("period_clock_links.csv", clock_links),
                       ("quarantine.csv", pd.DataFrame(rejected, columns=["isin", "source_hash", "reason"]))]:
        data.to_csv(destination / name, index=False, float_format="%.17g", lineterminator="\n")
    inventory = {p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(destination.glob("*.csv"))}
    summary["artifact_hashes"] = inventory
    summary["fingerprint"] = sha256(json.dumps(summary, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (destination / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
