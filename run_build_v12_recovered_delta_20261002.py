from pathlib import Path
import json, sys
import pandas as pd

ROOT = Path(r"C:\Users\Harshil\Downloads\stock-ranking-platform-fresh-canonical-verified")
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from dataclasses import replace
from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_ranker.personalized import PersonalizedEngine
from stock_ranker.personalized_data import load_history_book
from stock_research.personalized_global_tournament import load_frozen_memberships
from stock_research.personalized_official_actions import OfficialActionHistoryBook
from research.runners.run_personalized_executable_tournament import build_rows
from research.runners.build_deep_personalized_panel_20261002 import (
    PROTOCOL, FREEZE, COHORT, CUTOFF, verify_provider_ledger
)
from stock_research.personalized_executable_tournament import load_protocol

V1 = ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v1"
V2 = ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2"
V11 = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v11"
OUT = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v12-recovered-delta"

if OUT.exists():
    raise FileExistsError(f"fresh output required: {OUT}")
OUT.mkdir(parents=True)
a1 = pd.read_csv(V1 / "acquisition_audit.csv", low_memory=False)
a2 = pd.read_csv(V2 / "acquisition_audit.csv", low_memory=False)
old_failed = set(a1.loc[a1.status.eq("FAILED"), "isin"].dropna())
new_success = set(a2.loc[a2.status.eq("SUCCESS"), "isin"].dropna())
recovered = old_failed & new_success
if len(recovered) != 86:
    raise ValueError(f"expected 86 recovered identities, got {len(recovered)}")
provider_audit = verify_provider_ledger(V2)

summary11 = json.loads((V11 / "summary.json").read_text(encoding="utf-8"))
dates = tuple(d for d in summary11["additional_dates"] if d not in {"2015-01-31","2015-02-28"})
if len(dates) != 38:
    raise ValueError(f"expected 38 patch dates, got {len(dates)}")

protocol, profiles = load_protocol(PROTOCOL)
memberships = load_frozen_memberships(COHORT, protocol["frozen_cohort_fingerprint"])
member_isins = set.union(*memberships.values())
scope = recovered & member_isins

facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
repairs = pd.read_csv(COHORT / "terminal_repairs.csv")
ledger = pd.read_csv(FREEZE / "normalized_official_action_ledger.csv.gz", low_memory=False)
live_state = json.loads((ROOT / "data/live_market/accepted_state.json").read_text())
live = pd.read_csv(ROOT / "data/live_market" / live_state["bundle_path"] / "live_market.csv", low_memory=False)
audit = pd.read_csv(ROOT / "research/data/ownership-recovery-20260925/history_recovery_audit.csv")
nominal = set(audit.loc[audit.raw_basis.eq("OFFICIAL_NOMINAL"), "ticker"])
adjustment_dates = audit.dropna(subset=["provider_adjustment_through"]).set_index("ticker").provider_adjustment_through.to_dict()
terms = pd.read_csv(ROOT / "research/data/ownership-recovery-20260925/resulting_equity_terms.csv")

for term in terms.itertuples(index=False):
    mask = ledger["isin"].eq(term.parent_isin) & ledger.event_date.eq(term.event_date) & ledger.event_type.eq("DEMERGER")
    ledger.loc[mask, "mechanics_status"] = "RESULTING_EQUITY"
    ledger.loc[mask, "block_reason"] = None
    ledger.loc[mask, "economic_policy"] = "RESULTING_EQUITY_HOLD_PRICE_ONLY"

related = terms.loc[terms.parent_isin.isin(scope) | terms.child_isin.isin(scope)]
support = set(related.child_isin) | set(related.parent_isin)
book_ids = scope | support
identities = facts.loc[facts["isin"].isin(book_ids), ["isin","ticker"]].drop_duplicates("isin")
if set(scope) - set(identities["isin"]):
    raise ValueError("recovered in-scope identities missing from facts")

book = OfficialActionHistoryBook(
    identities, ROOT / "data/live_market/history_cache", V2, ledger,
    as_of_date=str(CUTOFF.date()), terminal_repairs=repairs,
    terminal_raw_prices=live[["isin","trade_date","latest_price"]],
    resulting_terms=terms,
    history_overlay=ROOT / "external_research_pack/ownership_history_20260925",
    nominal_tickers=nominal, adjustment_dates=adjustment_dates,
)
fractional_book, _ = load_history_book(
    facts, ROOT / "data/live_market/history_cache", terminal_repairs=repairs)
engine = PersonalizedEngine(fractional_book, cache_size=128)
checkpoints = OUT / "checkpoints"
checkpoints.mkdir()
built = build_rows(
    book, engine, fractional_book, facts, profiles, memberships,
    list(dates), "DEEP_ADDED", checkpoints)
delta = built.loc[built["isin"].isin(scope)].copy()
if set(delta["decision_date"].astype(str).unique()) != set(dates):
    raise ValueError("delta date coverage incomplete")
delta.to_csv(OUT / "recovered_delta_rows.csv.gz", index=False,
             compression={"method":"gzip","mtime":0})

meta = {
    "schema_version": "v12_recovered_identity_delta_v1",
    "recovered_provider_identities": len(recovered),
    "recovered_in_frozen_memberships": len(scope),
    "book_identity_count_with_action_support": len(identities),
    "usable_book_arrays": len(book.arrays),
    "book_errors": len(book.errors),
    "dates": list(dates),
    "delta_rows": len(delta),
    "provider_v2": provider_audit,
    "sealed_final_outcomes_inspected_for_collection": False,
}
(OUT / "summary.json").write_text(json.dumps(meta, indent=2, default=str)+"\n", encoding="utf-8")
print(json.dumps({k:meta[k] for k in (
    "recovered_provider_identities","recovered_in_frozen_memberships",
    "book_identity_count_with_action_support","usable_book_arrays","book_errors","delta_rows"
)}, indent=2))
