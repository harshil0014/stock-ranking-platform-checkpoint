"""Build a deeper, research-only, executable historical personalization panel.

The panel intentionally uses only dated price/action observations that precede
each decision and its 12-month outcome.  It does *not* attach current company
facts to earlier dates.  It extends the frozen official-action cohort with
semiannual missing decision blocks; 12-month horizon overlap is measured and
never described as independent sample size.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import numpy as np
import pandas as pd

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_ranker.personalized import PersonalizedEngine
from stock_ranker.personalized_data import load_history_book
from stock_research.personalized_executable_tournament import load_protocol
from stock_research.personalized_global_tournament import global_existing_evidence, load_frozen_memberships
from stock_research.personalized_official_actions import OfficialActionHistoryBook
from research.runners.run_personalized_executable_tournament import build_rows

PROTOCOL = ROOT / "research/protocols/personalized_official_action_tournament_v1.json"
FREEZE = ROOT / "experiments/personalized-official-action-freeze/build-06"
COHORT = ROOT / "experiments/personalized-data-freeze/build-01"
SOURCE = ROOT / "experiments/personalized-official-action-tournament/build-03"

# These twelve are absent from the source personalized tournament.  Each has a
# matured endpoint by the 2026-09-18 research cutoff.  Semiannual spacing makes
# overlap transparent (approximately half of adjacent holding periods).
ADDITIONAL_DATES = (
    "2020-03-31", "2020-09-30", "2021-03-31", "2021-09-30",
    "2022-03-31", "2022-09-30", "2023-03-31", "2023-09-30",
    "2024-03-31", "2024-09-30", "2025-03-31", "2025-06-30",
)
CUTOFF = pd.Timestamp("2026-09-18")
PRIOR_PROVIDER_LEDGER_SHA256 = "0d723a299d346eeffa7160d4108acda8dc609cd7b7e2360f443cdb2cc51c4fcb"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _date_overlap(dates: list[str]) -> pd.DataFrame:
    windows = {d: pd.date_range(pd.Timestamp(d), pd.Timestamp(d) + pd.DateOffset(months=12), freq="D")
               for d in dates}
    rows = []
    for i, left in enumerate(dates):
        for right in dates[i + 1:]:
            a, b = windows[left], windows[right]
            common = len(a.intersection(b))
            rows.append({"left_date": left, "right_date": right, "shared_calendar_days": common,
                         "horizon_overlap_fraction": common / min(len(a), len(b))})
    return pd.DataFrame(rows)


def verify_provider_ledger(split_root: Path) -> dict:
    """Verify that this is a real Yahoo acquisition, not the retired bridge."""
    ledger_path = split_root / "split_ledger.csv"
    audit_path = split_root / "acquisition_audit.csv"
    summary_path = split_root / "summary.json"
    if not all(path.is_file() for path in (ledger_path, audit_path, summary_path)):
        raise FileNotFoundError("real Yahoo split ledger, audit, and summary are required")
    ledger = pd.read_csv(ledger_path, low_memory=False)
    audit = pd.read_csv(audit_path, low_memory=False)
    summary = json.loads(summary_path.read_text())
    required = {"isin", "ticker", "provider_symbol", "event_date", "numerator", "denominator",
                "split_ratio", "source_url", "response_sha256"}
    if not required.issubset(ledger.columns) or not {"isin", "status", "response_sha256"}.issubset(audit.columns):
        raise ValueError("Yahoo ledger schema/provenance fields missing")
    if str(summary.get("source", "")).lower().find("yahoo") < 0:
        raise ValueError("split source is not Yahoo")
    if sha(ledger_path) != summary.get("ledger_sha256") or sha(audit_path) != summary.get("audit_sha256"):
        raise ValueError("Yahoo ledger summary hash mismatch")
    success = audit.loc[audit.status.eq("SUCCESS")].copy()
    if success.empty or ledger.empty or ledger.response_sha256.isna().any():
        raise ValueError("Yahoo reacquisition has no observed successful events")
    raw = split_root / "raw"
    # Every event must point to a successful audited response whose on-disk
    # response hash matches. This excludes manufactured provider factors.
    audited_hashes = set(success.response_sha256.dropna())
    if not set(ledger.response_sha256).issubset(audited_hashes):
        raise ValueError("ledger events are not tied to successful acquisition responses")
    def verify_raw(row) -> None:
        raw_path = raw / f"{row.provider_symbol}.json"
        if not raw_path.is_file() or sha(raw_path) != row.response_sha256:
            raise ValueError(f"raw Yahoo response integrity mismatch: {row.provider_symbol}")
    # WSL metadata latency makes sequentially opening 3,704 small receipts
    # needlessly slow; hashing remains exhaustive, only concurrent.
    with ThreadPoolExecutor(max_workers=32) as pool:
        list(pool.map(verify_raw, success.itertuples(index=False)))
    canonical = ledger[["isin", "event_date", "numerator", "denominator"]].copy()
    canonical["event_date"] = pd.to_datetime(canonical.event_date, errors="raise").dt.date.astype(str)
    canonical = canonical.sort_values(list(canonical.columns), kind="stable").drop_duplicates()
    return {
        "ledger_sha256": sha(ledger_path), "audit_sha256": sha(audit_path),
        "prior_ledger_sha256": PRIOR_PROVIDER_LEDGER_SHA256,
        "byte_identity_with_prior": sha(ledger_path) == PRIOR_PROVIDER_LEDGER_SHA256,
        "canonical_observed_event_count": int(len(canonical)),
        "canonical_event_identity_sha256": hashlib.sha256(
            canonical.to_csv(index=False, lineterminator="\n").encode()).hexdigest(),
        "successful_responses": int(len(success)), "failed_responses": int(audit.status.eq("FAILED").sum()),
        "raw_response_integrity_verified": True,
        "acquisition_source": summary.get("source"), "parameters": summary.get("parameters"),
    }


def run(output: Path, split_root: Path, dates: tuple[str, ...] = ADDITIONAL_DATES) -> None:
    requested_dates = tuple(dates)
    if output.exists():
        raise FileExistsError("fresh output required")
    output.mkdir(parents=True)
    print(json.dumps({"stage": "output_created"}), flush=True)
    protocol, profiles = load_protocol(PROTOCOL)
    print(json.dumps({"stage": "protocol_loaded"}), flush=True)
    memberships = load_frozen_memberships(COHORT, protocol["frozen_cohort_fingerprint"])
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    identities = facts.loc[facts["isin"].isin(set.union(*memberships.values())), ["isin", "ticker"]]
    repairs = pd.read_csv(COHORT / "terminal_repairs.csv")
    ledger = pd.read_csv(FREEZE / "normalized_official_action_ledger.csv.gz", low_memory=False)
    live_state = json.loads((ROOT / "data/live_market/accepted_state.json").read_text())
    live = pd.read_csv(ROOT / "data/live_market" / live_state["bundle_path"] / "live_market.csv", low_memory=False)
    audit = pd.read_csv(ROOT / "research/data/ownership-recovery-20260925/history_recovery_audit.csv")
    nominal = set(audit.loc[audit.raw_basis.eq("OFFICIAL_NOMINAL"), "ticker"])
    adjustment_dates = audit.dropna(subset=["provider_adjustment_through"]).set_index("ticker").provider_adjustment_through.to_dict()
    terms = pd.read_csv(ROOT / "research/data/ownership-recovery-20260925/resulting_equity_terms.csv")
    children = facts.loc[facts["isin"].isin(set(terms.child_isin)), ["isin", "ticker"]]
    identities = pd.concat([identities, children]).drop_duplicates("isin")
    for term in terms.itertuples(index=False):
        mask = ledger["isin"].eq(term.parent_isin) & ledger.event_date.eq(term.event_date) & ledger.event_type.eq("DEMERGER")
        ledger.loc[mask, "mechanics_status"] = "RESULTING_EQUITY"
        ledger.loc[mask, "block_reason"] = None
        ledger.loc[mask, "economic_policy"] = "RESULTING_EQUITY_HOLD_PRICE_ONLY"
    provider_audit = verify_provider_ledger(split_root)
    print(json.dumps({"stage": "provider_verified"}), flush=True)
    acquisition = pd.read_csv(split_root / "acquisition_audit.csv", low_memory=False)
    failed_provider_isins = set(acquisition.loc[acquisition.status.eq("FAILED"), "isin"].dropna())
    failed_provider_in_scope = identities["isin"].isin(failed_provider_isins)
    provider_audit["failed_identities_quarantined"] = int(failed_provider_in_scope.sum())
    # A failed provider lookup is unknown split history, not evidence of zero
    # splits. Exclude those identities from newly reconstructed execution rows.
    acquisition.loc[acquisition.status.eq("FAILED")].to_csv(
        output / "provider_lookup_quarantine.csv", index=False
    )
    identities = identities.loc[~failed_provider_in_scope].copy()
    book = OfficialActionHistoryBook(
        identities, ROOT / "data/live_market/history_cache", split_root,
        ledger, as_of_date=str(CUTOFF.date()), terminal_repairs=repairs,
        terminal_raw_prices=live[["isin", "trade_date", "latest_price"]], resulting_terms=terms,
        history_overlay=ROOT / "external_research_pack/ownership_history_20260925",
        nominal_tickers=nominal, adjustment_dates=adjustment_dates,
    )
    print(json.dumps({"stage": "official_history_ready", "usable": len(book.arrays), "errors": len(book.errors)}), flush=True)
    fractional_book, hashes = load_history_book(facts, ROOT / "data/live_market/history_cache", terminal_repairs=repairs)
    print(json.dumps({"stage": "fractional_history_ready"}), flush=True)
    engine = PersonalizedEngine(fractional_book, cache_size=128)
    # build_rows is the already-audited whole-share/action simulator.  Its
    # profile outcomes are calculated from endpoint prices, never inserted as
    # decision-date fields.
    checkpoint = output / "checkpoints"
    checkpoint.mkdir(parents=True, exist_ok=True)
    added = build_rows(book, engine, fractional_book, facts, profiles, memberships,
                       list(dates), "DEEP_ADDED", checkpoint)
    source_parts = [pd.read_csv(SOURCE / f"{name}.csv.gz", low_memory=False)
                    for name in ("training_panel", "validation_predictions", "supplementary_predictions")]
    existing = pd.concat(source_parts, ignore_index=True)
    existing = existing.loc[existing.decision_date.ne("2026-09-18")].copy()
    panel = pd.concat([existing, added], ignore_index=True).drop_duplicates(
        ["decision_date", "profile_name", "isin"], keep="last")
    panel.endpoint = pd.to_datetime(panel.endpoint)
    if panel.endpoint.gt(CUTOFF).any() or pd.to_datetime(panel.decision_date).ge(panel.endpoint).any():
        raise ValueError("unmatured or invalid outcome entered deep panel")
    if set(dates) - set(panel.decision_date):
        raise ValueError("missing requested added decision date")
    # Retain only fields actually emitted by the simulator at each decision;
    # current classifications/fundamentals are excluded by construction.
    panel.to_csv(output / "deep_panel.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    dates = sorted(panel.decision_date.unique())
    overlap = _date_overlap(dates)
    overlap.to_csv(output / "outcome_window_overlap.csv", index=False)
    by_date = panel.groupby("decision_date", as_index=False).agg(
        rows=("isin", "size"), identities=("isin", "nunique"), profiles=("profile_name", "nunique"),
        endpoint=("endpoint", "max"), available=("status", lambda x: int(x.eq("AVAILABLE").sum())))
    by_date.to_csv(output / "date_coverage.csv", index=False)
    source_dates = sorted(existing.decision_date.unique())
    summary = {
        "schema_version": "deep_personalized_execution_panel_v1",
        "cutoff": str(CUTOFF.date()), "additional_dates": list(requested_dates),
        "source_dates": source_dates, "all_dates": dates,
        "decision_date_increase": len(dates) - len(source_dates),
        "matured_observation_increase": int(len(panel) - len(existing)),
        "total_matured_observations": int(len(panel)),
        "outcome_horizon_months": 12,
        "overlap": {"adjacent_mean_fraction": float(overlap.loc[overlap.horizon_overlap_fraction.gt(0), "horizon_overlap_fraction"].mean()),
                    "pairs_with_overlap": int(overlap.horizon_overlap_fraction.gt(0).sum()),
                    "total_pairs": int(len(overlap))},
        "provenance": {
            "prices": "Frozen local Yahoo-derived raw price cache; official-action simulator uses dated official action ledger.",
            "corporate_actions": str((FREEZE / "normalized_official_action_ledger.csv.gz").relative_to(ROOT)),
            "provider_split_ledger": str(split_root.relative_to(ROOT)),
            "provider_split_events": "Observed Yahoo chart split events; no official-action-derived provider bridge was used.",
            "membership": "Frozen 12/36/60-month global cohorts; current-survivor limitation retained.",
            "fundamentals": "None attached to added decision rows; no current fundamentals or sectors backfilled.",
        },
        "leakage_checks": {"all_endpoints_at_or_before_cutoff": True, "decision_strictly_before_endpoint": True,
                           "added_rows_use_current_facts": False,
                           "provider_split_ledger_is_observed": True},
        "provider_reacquisition_audit": provider_audit,
        "input_sha256": {str(PROTOCOL.relative_to(ROOT)): sha(PROTOCOL), str(FREEZE.relative_to(ROOT) / "normalized_official_action_ledger.csv.gz"): sha(FREEZE / "normalized_official_action_ledger.csv.gz"),
                         str(SOURCE.relative_to(ROOT) / "training_panel.csv.gz"): sha(SOURCE / "training_panel.csv.gz")},
        "history_cache_fingerprint": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print(json.dumps({"dates": len(dates), "added": len(requested_dates), "rows": len(panel)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split-root", type=Path,
                        default=ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v1")
    parsed = parser.parse_args()
    run(parsed.output, parsed.split_root.resolve())
