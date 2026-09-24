"""Official-action authority for research-only executable simulations."""
from __future__ import annotations

from pathlib import Path
import re

import numpy as np
import pandas as pd

from stock_research.personalized_executable_tournament import ExecutableHistoryBook


AUTO_TYPES = {"BONUS", "SPLIT", "CONSOLIDATION"}
BLOCKING_TYPES = {"RIGHTS", "DEMERGER", "SCHEME_OR_MERGER"}


def _ratio(pattern: str, text: str) -> tuple[float, float] | None:
    match = re.search(pattern, text, flags=re.I)
    if not match:
        return None
    left, right = map(float, match.groups())
    return (left, right) if left > 0 and right > 0 else None


def _expanded_mechanics(row) -> list[dict]:
    """Expand an official source row into automatic multipliers or one blocker."""
    text = str(row.source_text or "")
    output = []
    bonus = _ratio(r"bonus(?:\s+issue)?\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)", text)
    split = None
    if re.search(r"split|sub.?div", text, flags=re.I):
        split = _ratio(
            r"(?:from|rs\.?)\s*(?:rs\.?\s*)?(\d+(?:\.\d+)?)\s*(?:/-)?"
            r"(?:\s*per\s+share)?\s*(?:to|into)\s*(?:rs\.?|re\.?)?\s*(\d+(?:\.\d+)?)",
            text,
        )
        if split is None:
            split = _ratio(
                r"rs\.?\s*(\d+(?:\.\d+)?)\s*(?:/-)?\s*to\s*(?:rs\.?|re\.?)\s*(\d+(?:\.\d+)?)",
                text,
            )
    if bonus:
        issued, held = bonus
        output.append({"event_type": "BONUS", "multiplier_numerator": issued + held,
                       "multiplier_denominator": held})
    if split:
        old_face, new_face = split
        output.append({"event_type": "SPLIT" if old_face >= new_face else "CONSOLIDATION",
                       "multiplier_numerator": old_face, "multiplier_denominator": new_face})
    if output:
        return output
    if row.event_type in BLOCKING_TYPES:
        return [{"event_type": row.event_type, "block_reason": row.event_type}]
    if row.event_type == "CONSOLIDATION" or row.parse_status != "PARSED":
        return [{"event_type": row.event_type, "block_reason": "UNPARSED_" + str(row.event_type)}]
    multiplier = pd.to_numeric(pd.Series([row.total_share_multiplier]), errors="coerce").iloc[0]
    if row.event_type in AUTO_TYPES and np.isfinite(multiplier) and multiplier > 0:
        # Fallback is only used when the source pack already parsed a simple ratio.
        denominator = float(row.ratio_denominator)
        numerator = float(row.ratio_numerator)
        if row.event_type == "BONUS":
            numerator += denominator
        return [{"event_type": row.event_type, "multiplier_numerator": numerator,
                 "multiplier_denominator": denominator}]
    return [{"event_type": str(row.event_type), "block_reason": "UNRESOLVED_OFFICIAL_ACTION"}]


def load_official_action_ledger(facts: pd.DataFrame, source: str | Path,
                                *, as_of_date: str) -> tuple[pd.DataFrame, dict]:
    """Map official actions by primary-exchange identifier and expand mechanics.

    NSE symbol matching intentionally carries actions across ISIN changes caused by
    the action itself. BSE codes are stable primary-exchange identifiers.
    """
    required = {"isin", "ticker", "primary_exchange"}
    if not required.issubset(facts.columns) or facts["isin"].duplicated().any() or facts["ticker"].duplicated().any():
        raise ValueError("unique primary-exchange identities required")
    raw = pd.read_csv(source, low_memory=False)
    raw["event_date_normalized"] = pd.to_datetime(raw["event_date_parsed"], errors="coerce").dt.normalize()
    cutoff = pd.Timestamp(as_of_date).normalize()
    raw = raw.loc[raw.event_date_normalized.notna() & raw.event_date_normalized.le(cutoff)].copy()

    nse = facts.loc[facts.primary_exchange.eq("NSE"), ["isin", "ticker"]].rename(columns={"isin": "canonical_isin"})
    bse = facts.loc[facts.primary_exchange.eq("BSE"), ["isin", "ticker"]].copy()
    bse["ticker_or_code"] = bse.ticker.str.replace("BSE-", "", regex=False)
    bse = bse.rename(columns={"isin": "canonical_isin"})[["canonical_isin", "ticker", "ticker_or_code"]]
    raw["ticker_or_code"] = raw.ticker_or_code.astype(str).str.replace(r"\.0$", "", regex=True)
    nse_rows = raw.loc[raw.exchange.eq("NSE")].merge(
        nse, left_on="ticker_or_code", right_on="ticker", how="inner", validate="many_to_one"
    )
    bse_rows = raw.loc[raw.exchange.eq("BSE")].merge(
        bse, on="ticker_or_code", how="inner", validate="many_to_one"
    )
    mapped = pd.concat([nse_rows, bse_rows], ignore_index=True)

    records = []
    for row in mapped.itertuples(index=False):
        for item in _expanded_mechanics(row):
            record = {
                "isin": row.canonical_isin,
                "ticker": row.ticker,
                "exchange": row.exchange,
                "event_date": row.event_date_normalized.date().isoformat(),
                "source_text": row.source_text,
                "source_event_type": row.event_type,
                "event_type": item["event_type"],
                "mapping_basis": "EXACT_PRIMARY_EXCHANGE_SYMBOL" if row.exchange == "NSE" else "EXACT_PRIMARY_EXCHANGE_CODE",
                "mechanics_status": "BLOCKING" if "block_reason" in item else "AUTO_MULTIPLIER",
                "block_reason": item.get("block_reason"),
                "multiplier_numerator": item.get("multiplier_numerator"),
                "multiplier_denominator": item.get("multiplier_denominator"),
            }
            if record["mechanics_status"] == "AUTO_MULTIPLIER":
                record["total_share_multiplier"] = record["multiplier_numerator"] / record["multiplier_denominator"]
            else:
                record["total_share_multiplier"] = np.nan
            records.append(record)
    ledger = pd.DataFrame(records)
    if ledger.empty:
        raise ValueError("official action ledger mapped no identities")
    key = ["isin", "event_date", "event_type", "mechanics_status",
           "multiplier_numerator", "multiplier_denominator"]
    ledger = ledger.sort_values(["isin", "event_date", "event_type", "exchange"], kind="stable").drop_duplicates(key)
    conflicts = []
    automatic = ledger.loc[ledger.mechanics_status.eq("AUTO_MULTIPLIER")]
    for group_key, group in automatic.groupby(["isin", "event_date", "event_type"], sort=False):
        if group[["multiplier_numerator", "multiplier_denominator"]].drop_duplicates().shape[0] > 1:
            conflicts.append(group_key)
    if conflicts:
        conflict_keys = set(conflicts)
        keep = ~ledger.apply(lambda row: (row["isin"], row["event_date"], row["event_type"]) in conflict_keys, axis=1)
        extra = pd.DataFrame([
            {"isin": identity, "ticker": facts.set_index("isin").loc[identity, "ticker"],
             "exchange": facts.set_index("isin").loc[identity, "primary_exchange"], "event_date": day,
             "source_text": "conflicting official multipliers", "source_event_type": event_type,
             "event_type": event_type, "mapping_basis": "OFFICIAL_CONFLICT",
             "mechanics_status": "BLOCKING", "block_reason": "CONFLICTING_OFFICIAL_MULTIPLIER",
             "multiplier_numerator": np.nan, "multiplier_denominator": np.nan,
             "total_share_multiplier": np.nan}
            for identity, day, event_type in conflicts
        ])
        ledger = pd.concat([ledger.loc[keep], extra], ignore_index=True)
    ledger = ledger.sort_values(["isin", "event_date", "mechanics_status", "event_type"], kind="stable").reset_index(drop=True)
    audit = {
        "raw_rows_through_as_of": len(raw),
        "mapped_source_rows": len(mapped),
        "normalized_rows": len(ledger),
        "mapped_identities": int(ledger["isin"].nunique()),
        "automatic_rows": int(ledger.mechanics_status.eq("AUTO_MULTIPLIER").sum()),
        "blocking_rows": int(ledger.mechanics_status.eq("BLOCKING").sum()),
        "identity_continuity_rows": int(nse_rows["isin"].ne(nse_rows["canonical_isin"]).sum()),
        "conflicting_multiplier_groups": len(conflicts),
    }
    return ledger, audit


class OfficialActionHistoryBook(ExecutableHistoryBook):
    """Whole-share history with official actions and profile-window blockers."""

    def __init__(self, identities: pd.DataFrame, history_root: str | Path,
                 split_root: str | Path, official_actions: pd.DataFrame, *, as_of_date: str,
                 terminal_repairs: pd.DataFrame | None = None,
                 terminal_raw_prices: pd.DataFrame | None = None):
        if identities["isin"].duplicated().any() or identities["ticker"].duplicated().any():
            raise ValueError("executable identities must be unique")
        history_root, split_root = Path(history_root), Path(split_root)
        provider = pd.read_csv(split_root / "split_ledger.csv")
        provider["event_date"] = pd.to_datetime(provider.get("event_date"), errors="coerce").dt.normalize()
        provider_groups = {identity: frame for identity, frame in provider.groupby("isin")}
        actions = official_actions.copy()
        actions["event_date"] = pd.to_datetime(actions.event_date, errors="raise").dt.normalize()
        self.actions = {identity: frame for identity, frame in actions.groupby("isin")}
        cutoff_ts = pd.Timestamp(as_of_date).normalize()
        cutoff = np.datetime64(cutoff_ts.date(), "D")
        repairs, raw_terminals = {}, {}
        if terminal_repairs is not None:
            required = {"isin", "ticker", "appended_date", "appended_price"}
            if not required.issubset(terminal_repairs.columns) or terminal_repairs["isin"].duplicated().any():
                raise ValueError("unique frozen terminal repairs required")
            if terminal_raw_prices is None or not {"isin", "trade_date", "latest_price"}.issubset(terminal_raw_prices.columns):
                raise ValueError("terminal raw prices required for frozen repairs")
            repairs = terminal_repairs.set_index("isin").to_dict("index")
            raw_terminals = terminal_raw_prices.set_index("isin").to_dict("index")
        self.arrays, self.errors, self.cache = {}, {}, {}
        for row in identities[["isin", "ticker"]].sort_values("isin").itertuples(index=False):
            try:
                relative = Path(f"{row.ticker}.csv")
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("unsafe history path")
                frame = pd.read_csv(history_root / relative)
                repair = repairs.get(row.isin)
                if repair is not None and pd.Timestamp(repair["appended_date"]).normalize() <= cutoff_ts:
                    terminal_raw = raw_terminals.get(row.isin)
                    if repair["ticker"] != row.ticker or terminal_raw is None:
                        raise ValueError("terminal repair identity mismatch")
                    repair_date = pd.Timestamp(repair["appended_date"]).normalize()
                    if pd.Timestamp(terminal_raw["trade_date"]).normalize() != repair_date:
                        raise ValueError("terminal repair date mismatch")
                    if repair_date > pd.to_datetime(frame["date"]).max():
                        frame = pd.concat([frame, pd.DataFrame({
                            "date": [repair_date], "raw_close": [terminal_raw["latest_price"]],
                            "adjusted_close": [repair["appended_price"]],
                        })], ignore_index=True)
                dates = pd.to_datetime(frame["date"], errors="raise").to_numpy(dtype="datetime64[D]")
                raw = pd.to_numeric(frame["raw_close"], errors="raise").to_numpy(float)
                provider_adjusted = pd.to_numeric(frame["adjusted_close"], errors="raise").to_numpy(float)
                keep = dates <= cutoff
                dates, raw, provider_adjusted = dates[keep], raw[keep], provider_adjusted[keep]
                if len(dates) < 2 or np.isnat(dates).any() or (np.diff(dates).astype(int) <= 0).any():
                    raise ValueError("invalid execution dates")
                if (not np.isfinite(raw).all() or not np.isfinite(provider_adjusted).all()
                        or (raw <= 0).any() or (provider_adjusted <= 0).any()):
                    raise ValueError("invalid price history")

                provider_events = provider_groups.get(row.isin, pd.DataFrame(columns=provider.columns)).copy()
                provider_events = provider_events.loc[provider_events.event_date.le(cutoff_ts)].sort_values("event_date")
                provider_ratios = pd.to_numeric(provider_events.get("split_ratio"), errors="coerce").to_numpy(float)
                provider_dates = provider_events.event_date.to_numpy(dtype="datetime64[D]")
                if len(provider_ratios) and (not np.isfinite(provider_ratios).all() or (provider_ratios <= 0).any()):
                    raise ValueError("invalid provider split ratio")
                provider_suffix = np.ones(len(provider_ratios) + 1)
                if len(provider_ratios):
                    provider_suffix[:-1] = np.cumprod(provider_ratios[::-1])[::-1]
                provider_factor = provider_suffix[np.searchsorted(provider_dates, dates, side="right")]
                # Yahoo ``raw_close`` is the contemporaneous exchange price.  A
                # split changes shares held, not the cash paid at that old close.
                nominal = raw.copy()

                identity_actions = self.actions.get(row.isin, pd.DataFrame(columns=actions.columns))
                automatic = identity_actions.loc[
                    identity_actions.mechanics_status.eq("AUTO_MULTIPLIER")
                    & identity_actions.event_date.le(cutoff_ts)
                ].sort_values(["event_date", "event_type"])
                official_ratios = pd.to_numeric(automatic.total_share_multiplier, errors="coerce").to_numpy(float)
                official_dates = automatic.event_date.to_numpy(dtype="datetime64[D]")
                if len(official_ratios) and (not np.isfinite(official_ratios).all() or (official_ratios <= 0).any()):
                    raise ValueError("invalid official multiplier")
                official_suffix = np.ones(len(official_ratios) + 1)
                if len(official_ratios):
                    official_suffix[:-1] = np.cumprod(official_ratios[::-1])[::-1]
                official_factor = official_suffix[np.searchsorted(official_dates, dates, side="right")]
                # Yahoo Adj Close combines distributions and Yahoo's own split
                # ledger.  Remove the provider split component, then apply only
                # the official exchange multiplier to the economic return basis.
                dividend_factor = provider_adjusted / raw * provider_factor
                economic_adjusted = nominal / official_factor * dividend_factor
                for array in (dates, raw, economic_adjusted, nominal, official_factor):
                    array.setflags(write=False)
                self.arrays[row.isin] = (dates, raw, economic_adjusted, nominal, official_factor)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.errors[row.isin] = str(exc)

    def simulate(self, profile, end, *, months: int | None = None,
                 mode: str = "enhanced_carry", include_journal: bool = True) -> pd.DataFrame:
        result = super().simulate(profile, end, months=months, mode=mode, include_journal=include_journal)
        if "reason" not in result:
            result["reason"] = None
        else:
            result["reason"] = result["reason"].astype(object)
        end_ts = pd.Timestamp(end).normalize()
        start = end_ts - pd.DateOffset(months=months or profile.lookback_months)
        blocker_ids, action_counts = {}, {}
        for identity, actions in self.actions.items():
            window = actions.loc[actions.event_date.between(start, end_ts)]
            action_counts[identity] = len(window)
            blocking = window.loc[window.mechanics_status.eq("BLOCKING")]
            if not blocking.empty:
                blocker_ids[identity] = "|".join(sorted(set(blocking.block_reason.astype(str))))
        result["official_action_events_in_window"] = result["isin"].map(action_counts).fillna(0).astype(int)
        result["corporate_action_evidence"] = "OFFICIAL_PRIMARY_EXCHANGE_PROFILE_WINDOW"
        metric_columns = [
            "shares_bought", "average_purchase_cost", "amount_invested", "current_holding_value",
            "total_wealth", "profit_loss", "profit_loss_pct", "xirr", "target_attainment",
            "target_shortfall", "cash_utilization", "execution_count", "terminal_price",
            "price_drawdown", "cagr_3y", "cagr_5y",
        ]
        blocked = result["isin"].isin(blocker_ids)
        result.loc[blocked, "status"] = "UNRESOLVED_CORPORATE_ACTION"
        result.loc[blocked, "reason"] = result.loc[blocked, "isin"].map(blocker_ids)
        result.loc[blocked, metric_columns] = np.nan
        available = result.status.eq("AVAILABLE")
        fractional = available & result.shares_bought.notna() & ~np.isclose(
            result.shares_bought, np.round(result.shares_bought), atol=1e-8
        )
        result.loc[fractional, "status"] = "UNRESOLVED_FRACTIONAL_ENTITLEMENT"
        result.loc[fractional, "reason"] = "OFFICIAL_MULTIPLIER_PRODUCED_FRACTIONAL_SHARES"
        result.loc[fractional, metric_columns] = np.nan
        result["evidence_grade"] = "OFFICIAL_ACTIONS_WITH_YAHOO_PRICE_BASIS_RESEARCH_ONLY"
        return result
