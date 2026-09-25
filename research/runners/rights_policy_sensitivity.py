"""Record-date cash-only rights exercise sensitivity for recovered rights."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_research.personalized_executable_tournament import load_protocol
from stock_research.personalized_official_actions import OfficialActionHistoryBook, affordable_rights_allotment


def replay(book, identity, profile, end, *, exercise):
    end = pd.Timestamp(end)
    start = end - pd.DateOffset(months=profile.lookback_months)
    schedule = pd.date_range(start, end - pd.Timedelta(days=1), freq=f"{profile.interval_days}D")
    dates, _, _, nominal, _ = book.arrays[identity]
    buy = np.searchsorted(dates, schedule.to_numpy(dtype="datetime64[D]"))
    last = np.searchsorted(dates, np.datetime64(end.date(), "D"), side="right") - 1
    actions = book.actions[identity]
    actions = actions.loc[actions.event_date.between(start, end)].sort_values(
        ["event_date", "mechanics_status", "event_type"], kind="stable")
    action_rows = list(actions.itertuples(index=False))
    position = 0
    shares = cash = rights_spend = 0.0
    rights_shares = 0

    def apply_through(day):
        nonlocal position, shares, cash, rights_spend, rights_shares
        while position < len(action_rows) and np.datetime64(action_rows[position].event_date.date(), "D") <= day:
            action = action_rows[position]
            if action.mechanics_status == "AUTO_MULTIPLIER":
                shares *= float(action.total_share_multiplier)
                if not np.isclose(shares, round(shares), atol=1e-8):
                    raise ValueError("fractional automatic action in rights replay")
            elif action.mechanics_status == "PASSIVE_RIGHTS" and exercise and action.economic_policy != "WITHDRAWN_NO_ALLOTMENT":
                offered, held = map(int, str(action.entitlement_terms).split(":"))
                quantity, cash = affordable_rights_allotment(
                    int(round(shares)), cash, offered, held, float(action.issue_price_inr))
                shares += quantity
                rights_shares += quantity
                rights_spend += quantity * float(action.issue_price_inr)
            elif action.mechanics_status == "BLOCKING":
                raise ValueError("other unresolved action in rights replay")
            position += 1

    for scheduled_day, price_index in zip(schedule, buy):
        cash += profile.amount
        if price_index > last:
            continue
        apply_through(dates[price_index])
        quantity = math.floor(cash / float(nominal[price_index]))
        shares += quantity
        cash -= quantity * float(nominal[price_index])
    apply_through(np.datetime64(end.date(), "D"))
    return {"shares": shares, "cash": cash, "wealth": shares * float(nominal[last]) + cash,
            "rights_shares": rights_shares, "rights_spend_inr": rights_spend}


def run(args):
    protocol, profiles = load_protocol(args.protocol)
    ledger = pd.read_csv(args.freeze / "normalized_official_action_ledger.csv.gz", low_memory=False)
    rights = ledger.loc[ledger.mechanics_status.eq("PASSIVE_RIGHTS")].copy()
    ids = set(rights["isin"])
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    identities = facts.loc[facts["isin"].isin(ids), ["isin", "ticker"]]
    repairs = pd.read_csv(args.frozen_root / "terminal_repairs.csv")
    state = json.loads((ROOT / "data/live_market/accepted_state.json").read_text(encoding="utf-8"))
    live = pd.read_csv(ROOT / "data/live_market" / state["bundle_path"] / "live_market.csv", low_memory=False)
    book = OfficialActionHistoryBook(identities, args.history_cache, args.split_root, ledger,
                                     as_of_date=protocol["current_profile_date"], terminal_repairs=repairs,
                                     terminal_raw_prices=live[["isin", "trade_date", "latest_price"]])
    rows = []
    for name, profile in profiles.items():
        passive = book.simulate(profile, protocol["current_profile_date"],
                                mode="enhanced_carry", include_journal=False).set_index("isin")
        for identity in sorted(ids):
            events = rights.loc[rights["isin"].eq(identity)]
            events = events.loc[pd.to_datetime(events.event_date).between(
                pd.Timestamp(protocol["current_profile_date"]) - pd.DateOffset(months=profile.lookback_months),
                pd.Timestamp(protocol["current_profile_date"]))]
            if events.empty:
                continue
            row = {"profile": name, "isin": identity, "recovered_rights_events_in_window": len(events),
                   "scenario": "EXERCISE_IF_AFFORDABLE_AT_RECORD_DATE_HYPOTHETICAL",
                   "passive_status": passive.loc[identity, "status"],
                   "status": "NOT_EVALUABLE"}
            if identity not in book.arrays or passive.loc[identity, "status"] != "AVAILABLE":
                row["reason"] = "PASSIVE_PROFILE_UNAVAILABLE_OR_BLOCKED"
            else:
                try:
                    base = replay(book, identity, profile, protocol["current_profile_date"], exercise=False)
                    active = replay(book, identity, profile, protocol["current_profile_date"], exercise=True)
                    if not np.isclose(base["wealth"], passive.loc[identity, "total_wealth"], atol=1e-5):
                        raise ValueError("passive replay does not reconcile")
                    row.update({"status": "HYPOTHETICAL_ONLY", "passive_wealth_inr": base["wealth"],
                                "exercise_wealth_inr": active["wealth"],
                                "wealth_delta_inr": active["wealth"] - base["wealth"],
                                "rights_shares_exercised": active["rights_shares"],
                                "portfolio_cash_spent_inr": active["rights_spend_inr"],
                                "external_cash_injected_inr": 0.0,
                                "reason": "Record date used as subscription proxy; actual issue-period cash availability and entitlement trading are not reproduced."})
                except (ValueError, TypeError, KeyError) as exc:
                    row["reason"] = str(exc)
            rows.append(row)
    pd.DataFrame(rows).to_csv(args.tournament / "rights_policy_sensitivity.csv", index=False, lineterminator="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tournament", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--history-cache", type=Path, required=True)
    parser.add_argument("--split-root", type=Path, required=True)
    run(parser.parse_args())
