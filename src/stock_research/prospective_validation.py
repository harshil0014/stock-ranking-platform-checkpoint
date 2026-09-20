"""Freeze outcome-blind production challengers for genuine future validation."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_research.exploratory_benchmark import strict_price_factors


SCHEMA_VERSION = "prospective_rank_challengers_v2"
ARTIFACTS = {"exclusions.csv", "frozen_signals.csv", "protocol.json", "provenance.json", "summary.json"}


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")


def freeze_prospective_challengers(
    *, state_root: str | Path, history_root: str | Path, output: str | Path,
    frozen_at: str | None = None,
) -> str:
    """Freeze current rankings; never reads or constructs an outcome."""
    root, histories, destination = Path(state_root).resolve(), Path(history_root).resolve(), Path(output)
    if destination.exists():
        raise ValueError(f"output directory already exists: {destination}")
    if frozen_at is not None:
        raise ValueError("frozen_at is recorded automatically after construction; caller timestamps are not permitted")
    started_at = pd.Timestamp.now(tz="UTC")
    state_bytes = (root / "accepted_state.json").read_bytes()
    state = json.loads(state_bytes)
    accepted_at = pd.Timestamp(state["accepted_at"])
    if accepted_at.tzinfo is None or accepted_at > started_at:
        raise ValueError("accepted snapshot availability is invalid or in the future")
    snapshot = resolve_company_fact_snapshot(root)
    if snapshot.resolve() != (root / state["snapshot_path"]).resolve():
        raise ValueError("accepted state changed before snapshot resolution")
    loaded = load_company_fact_snapshot(snapshot)
    required = {
        "ticker", "isin", "company", "product_sector", "product_baseline_eligible",
        "product_baseline_score", "product_baseline_sector_rank", "history_end_date",
    }
    if missing := required.difference(loaded.facts.columns):
        raise ValueError(f"accepted facts are missing fields: {sorted(missing)}")
    facts = loaded.facts.loc[
        loaded.facts["product_baseline_eligible"].fillna(False).astype(bool),
        sorted(required),
    ].copy()
    if facts["isin"].isna().any() or facts.duplicated("isin").any() or facts.duplicated("ticker").any():
        raise ValueError("eligible challenger universe lacks unique exact identities")
    decision_date = str(state["trade_date"])
    rows, exclusions, history_hashes = [], [], {}
    for row in facts.sort_values("ticker", kind="stable").to_dict("records"):
        path = histories / f"{row['ticker']}.csv"
        if not path.is_file():
            exclusions.append({"ticker": row["ticker"], "isin": row["isin"], "reason": "PRICE_HISTORY_FILE_MISSING"})
            continue
        try:
            source_bytes = path.read_bytes()
            history = pd.read_csv(BytesIO(source_bytes), usecols=["date", "adjusted_close"])
            factors = strict_price_factors(history, decision_date)
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            exclusions.append({"ticker": row["ticker"], "isin": row["isin"], "reason": f"MOM12M_UNAVAILABLE: {exc}"})
            continue
        history_hashes[str(row["ticker"])] = sha256(source_bytes).hexdigest()
        rows.append({
            "as_of_date": decision_date, "ticker": str(row["ticker"]),
            "isin": str(row["isin"]), "company": str(row["company"]),
            "sector": str(row["product_sector"]),
            "baseline_score": float(row["product_baseline_score"]),
            "baseline_sector_rank": float(row["product_baseline_sector_rank"]),
            **factors, "history_end_date": str(row["history_end_date"]),
        })
    signals = pd.DataFrame(rows)
    if signals.empty:
        raise ValueError("no prospective challenger signal could be constructed")
    grouped = signals.groupby("sector", sort=True)
    signals["baseline_percentile"] = grouped["baseline_sector_rank"].rank(method="average", ascending=False, pct=True)
    signals["mom12m_percentile"] = grouped["mom12m"].rank(method="average", ascending=True, pct=True)
    signals["mom6m_percentile"] = grouped["mom6m"].rank(method="average", ascending=True, pct=True)
    signals["reversal1m_percentile"] = grouped["reversal1m"].rank(method="average", ascending=True, pct=True)
    signals["low_volatility_percentile"] = grouped["low_volatility_12m"].rank(method="average", ascending=True, pct=True)
    signals["shallow_drawdown_percentile"] = grouped["shallow_drawdown_12m"].rank(method="average", ascending=True, pct=True)
    signals["baseline_mom12m_equal_weight_score"] = (signals["baseline_percentile"] + signals["mom12m_percentile"]) / 2.0
    signals["price_multifactor_equal_weight_score"] = (
        signals["mom12m_percentile"] + signals["low_volatility_percentile"]
        + signals["shallow_drawdown_percentile"]
    ) / 3.0
    signals["baseline_price_multifactor_equal_weight_score"] = (
        signals["baseline_percentile"] + signals["mom12m_percentile"]
        + signals["low_volatility_percentile"] + signals["shallow_drawdown_percentile"]
    ) / 4.0
    signals["mom12m_sector_rank"] = grouped["mom12m"].rank(method="min", ascending=False)
    signals["baseline_mom12m_sector_rank"] = signals.groupby("sector", sort=True)["baseline_mom12m_equal_weight_score"].rank(method="min", ascending=False)
    signals["price_multifactor_sector_rank"] = signals.groupby("sector", sort=True)["price_multifactor_equal_weight_score"].rank(method="min", ascending=False)
    signals["baseline_price_multifactor_sector_rank"] = signals.groupby("sector", sort=True)["baseline_price_multifactor_equal_weight_score"].rank(method="min", ascending=False)
    signals = signals.sort_values(["sector", "ticker"], kind="stable").reset_index(drop=True)
    excluded = pd.DataFrame(exclusions, columns=["ticker", "isin", "reason"]).sort_values(["ticker"], kind="stable").reset_index(drop=True)
    if (root / "accepted_state.json").read_bytes() != state_bytes:
        raise ValueError("accepted state changed during prospective construction")
    for ticker, digest in history_hashes.items():
        if _hash(histories / f"{ticker}.csv") != digest:
            raise ValueError(f"history changed during prospective construction: {ticker}")
    timestamp = pd.Timestamp.now(tz="UTC")
    protocol: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "FROZEN_OUTCOME_BLIND_AWAITING_FUTURE_DATA",
        "frozen_at": timestamp.isoformat(), "ranking_date": decision_date,
        "identity_key": "ISIN", "sector_source": "accepted product sector at freeze",
        "challengers": {
            "opensourceap_mom12m_strict": "complete calendar months t-1 through t-11; no missing-return zero-fill",
            "baseline_mom12m_equal_weight": "fixed 50/50 within-sector percentile mean; no fitted weight",
            "price_multifactor_equal_weight": "fixed equal weight Mom12m, low volatility and shallow drawdown percentiles",
            "baseline_price_multifactor_equal_weight": "fixed equal weight Baseline, Mom12m, low volatility and shallow drawdown percentiles",
        },
        "incumbent": "baseline_v1", "product_default_changed": False,
        "outcomes_accessed": False, "selection_performed": False,
        "future_evaluation": {
            "entry": "first accepted EOD close strictly after frozen_at",
            "horizons_months": [3, 6, 12], "primary_horizon_months": 12,
            "metric": "equal-weight sector-date Spearman Rank IC",
            "promotion_gate": "new challenger must beat incumbent across multiple independent dates and pass coverage, concentration, turnover and cost diagnostics",
            "earliest_primary_maturity": (timestamp + pd.DateOffset(months=12)).date().isoformat(),
        },
        "scientific_limits": [
            "Current enriched fundamentals are not backfilled into historical training.",
            "The 2022-2025 exploratory result motivated this prospective test but is not promotion evidence.",
            "No investment, profitability, or superiority claim is authorized.",
        ],
    }
    provenance = {
        "accepted_company_fingerprint": state["fingerprint"],
        "accepted_market_fingerprint": state["market_fingerprint"],
        "accepted_snapshot": state["snapshot_path"],
        "accepted_at": accepted_at.isoformat(),
        "build_started_at": started_at.isoformat(),
        "accepted_state_sha256": sha256(state_bytes).hexdigest(),
        "history_file_sha256": history_hashes,
    }
    summary = {
        "schema_version": SCHEMA_VERSION, "ranking_date": decision_date,
        "incumbent_eligible": int(len(facts)), "challenger_eligible": int(len(signals)),
        "challenger_excluded": int(len(excluded)), "sector_count": int(signals["sector"].nunique()),
        "outcomes_accessed": False, "product_default_changed": False,
    }
    destination.mkdir(parents=True)
    _write_csv(signals, destination / "frozen_signals.csv")
    _write_csv(excluded, destination / "exclusions.csv")
    for name, value in (("protocol.json", protocol), ("provenance.json", provenance), ("summary.json", summary)):
        (destination / name).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    artifacts = []
    for name in ("exclusions.csv", "frozen_signals.csv", "protocol.json", "provenance.json", "summary.json"):
        path = destination / name
        artifacts.append({"path": name, "sha256": _hash(path), "size": path.stat().st_size})
    manifest = {"schema_version": SCHEMA_VERSION, "artifacts": artifacts}
    fingerprint = sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    manifest["fingerprint"] = fingerprint
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return fingerprint


def validate_prospective_freeze(root: str | Path) -> dict[str, Any]:
    directory = Path(root)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unexpected prospective manifest schema")
    payload = {key: value for key, value in manifest.items() if key != "fingerprint"}
    if sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest() != manifest.get("fingerprint"):
        raise ValueError("prospective manifest fingerprint mismatch")
    paths = [item["path"] for item in manifest["artifacts"]]
    if len(paths) != len(ARTIFACTS) or set(paths) != ARTIFACTS:
        raise ValueError("prospective artifact inventory is incomplete or unexpected")
    for item in manifest["artifacts"]:
        path = directory / item["path"]
        if not path.is_file() or path.stat().st_size != item["size"] or _hash(path) != item["sha256"]:
            raise ValueError(f"prospective artifact changed: {item['path']}")
    protocol = json.loads((directory / "protocol.json").read_text(encoding="utf-8"))
    if protocol.get("outcomes_accessed") is not False or protocol.get("product_default_changed") is not False:
        raise ValueError("prospective outcome/default boundary was violated")
    provenance = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    times = [pd.Timestamp(provenance["accepted_at"]), pd.Timestamp(provenance["build_started_at"]), pd.Timestamp(protocol["frozen_at"])]
    if any(value.tzinfo is None or pd.isna(value) for value in times) or not times[0] <= times[1] <= times[2] <= pd.Timestamp.now(tz="UTC"):
        raise ValueError("prospective source/freeze chronology is invalid")
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    signals = pd.read_csv(directory / "frozen_signals.csv")
    excluded = pd.read_csv(directory / "exclusions.csv")
    if signals["isin"].isna().any() or signals["isin"].duplicated().any() or signals["ticker"].duplicated().any():
        raise ValueError("prospective identities are not unique")
    if set(signals["ticker"]) != set(provenance["history_file_sha256"]):
        raise ValueError("prospective history provenance is incomplete")
    if len(signals) != summary["challenger_eligible"] or len(excluded) != summary["challenger_excluded"] or len(signals) + len(excluded) != summary["incumbent_eligible"]:
        raise ValueError("prospective coverage counts disagree")
    return summary
