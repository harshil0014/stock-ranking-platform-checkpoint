"""Official-action authority for research-only executable simulations."""
from __future__ import annotations

from pathlib import Path
from hashlib import sha256
import json
import math
import re

import numpy as np
import pandas as pd

from stock_research.personalized_executable_tournament import ExecutableHistoryBook


AUTO_TYPES = {"BONUS", "SPLIT", "CONSOLIDATION"}
BLOCKING_TYPES = {"RIGHTS", "DEMERGER", "SCHEME_OR_MERGER"}


def affordable_rights_allotment(held_shares: int, available_cash: float,
                                offered: int, per_held: int, issue_price: float) -> tuple[int, float]:
    """Cash-constrained exercise; no new contribution is introduced."""
    if held_shares < 0 or available_cash < 0 or offered <= 0 or per_held <= 0 or issue_price <= 0:
        raise ValueError("invalid rights exercise inputs")
    entitled = held_shares * offered // per_held
    shares = min(entitled, int(available_cash // issue_price))
    return shares, available_cash - shares * issue_price


def validate_recovery_pack(pack: str | Path, round2_root: str | Path) -> dict:
    """Reconcile the 445 event identities and verify each declared local source."""
    pack, round2_root = Path(pack), Path(round2_root)
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        path = pack / name
        if path.stat().st_size != expected["size"] or sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
            raise ValueError(f"recovery manifest mismatch: {name}")
    for item in json.loads((pack / "source_inventory.json").read_text(encoding="utf-8")):
        if not item.get("local_path"):
            continue
        path = pack / item["local_path"].replace("\\", "/")
        if path.stat().st_size != item["bytes"] or sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"recovery source mismatch: {path}")
    batches = [pd.read_csv(round2_root / f"batch_{number:02d}" / "parsed_event_terms.csv")
               for number in range(1, 5)]
    events = pd.concat(batches, ignore_index=True)
    if len(events) != 445 or events.event_id.nunique() != 445:
        raise ValueError("round-two event population differs from frozen 445")
    auto_rows = pd.read_csv(pack / "auto_action_ledger_reconciliation.csv")
    auto = set(auto_rows.loc[auto_rows.mechanics_status.eq("AUTO_MULTIPLIER"), "event_id"])
    complex_terms = pd.read_csv(pack / "critical_event_terms_recovered.csv")
    consolidation = pd.read_csv(pack / "consolidation_terms_recovered.csv")
    event_key = lambda frame, date: set(zip(frame["isin"], frame[date], frame["event_type"]))
    lookup = events.set_index(["isin", "event_date", "event_type"]).event_id
    critical_ids = {lookup.loc[key] for key in event_key(complex_terms, "ledger_event_date")}
    consolidation_ids = {lookup.loc[key] for key in event_key(consolidation.rename(columns={"record_date": "event_date"}), "event_date")}
    residual = set(auto_rows.event_id) | critical_ids | consolidation_ids
    old = set(events.event_id) - residual
    web = pd.concat([pd.read_csv(round2_root / f"batch_{number:02d}" / "supplemental_web_terms.csv")
                     for number in range(1, 5)], ignore_index=True)
    evidence_keys = event_key(events.loc[events.evidence_grade.ne("NO_ATTACHMENT_TEXT")], "event_date") | event_key(web, "event_date")
    old_keys = set(events.loc[events.event_id.isin(old), ["isin", "event_date", "event_type"]].itertuples(index=False, name=None))
    if not old_keys.issubset(evidence_keys):
        raise ValueError("previously covered event lacks round-two evidence")
    if len(old) != 311 or len(auto) != 112 or len(critical_ids) != 16 or len(consolidation_ids) != 6:
        raise ValueError("recovery component count mismatch")
    covered = old | auto | critical_ids | consolidation_ids
    if covered != set(events.event_id):
        raise ValueError(f"uncovered round-two events: {len(set(events.event_id) - covered)}")
    return {"round2_events": len(events), "previously_covered": len(old),
            "official_auto_matches": len(auto), "complex_recovered": len(critical_ids),
            "consolidations_recovered": len(consolidation_ids), "covered_union": len(covered),
            "core_mechanics_unknown": 0, "verified_pack_files": len(manifest["files"])}


def apply_recovered_terms(ledger: pd.DataFrame, residual_pack: str | Path,
                          *, as_of_date: str) -> tuple[pd.DataFrame, dict]:
    """Apply dated recovered mechanics without importing post-cutoff events."""
    pack = Path(residual_pack)
    cutoff = pd.Timestamp(as_of_date)
    result = ledger.copy()
    result["economic_policy"] = "OFFICIAL_MULTIPLIER_OR_EXISTING_BLOCK"
    result["evidence_url"] = None
    result["entitlement_terms"] = None
    result["issue_price_inr"] = np.nan
    complex_terms = pd.read_csv(pack / "critical_event_terms_recovered.csv")
    consolidations = pd.read_csv(pack / "consolidation_terms_recovered.csv")
    applied = []
    for row in complex_terms.itertuples(index=False):
        day = pd.Timestamp(row.ledger_event_date)
        if day > cutoff:
            continue
        mask = result["isin"].eq(row.isin) & result.event_date.eq(day.date().isoformat()) & result.event_type.eq(row.event_type)
        if not mask.any():
            raise ValueError(f"recovered event missing from normalized ledger: {row.isin} {day.date()} {row.event_type}")
        if row.event_type == "RIGHTS":
            policy = "WITHDRAWN_NO_ALLOTMENT" if row.outcome == "WITHDRAWN_NO_ALLOTMENT" else "PASSIVE_NO_SUBSCRIPTION_ZERO_ENTITLEMENT_VALUE"
            result.loc[mask, "mechanics_status"] = "PASSIVE_RIGHTS"
            result.loc[mask, "block_reason"] = None
        elif row.event_type == "DEMERGER":
            policy = "RESULTING_SECURITY_VALUATION_UNAVAILABLE"
            result.loc[mask, "block_reason"] = policy
        else:
            policy = "PREFERENCE_SHARE_VALUATION_UNAVAILABLE"
            result.loc[mask, "block_reason"] = policy
        result.loc[mask, "economic_policy"] = policy
        result.loc[mask, "evidence_url"] = row.source_url
        result.loc[mask, "entitlement_terms"] = row.economic_ratio
        result.loc[mask, "issue_price_inr"] = row.issue_price_inr
        applied.append((row.isin, row.event_type, policy))
    for row in consolidations.itertuples(index=False):
        day = pd.Timestamp(row.record_date)
        if day > cutoff:
            continue
        mask = result["isin"].eq(row.isin) & result.event_date.eq(day.date().isoformat()) & result.event_type.eq("CONSOLIDATION")
        if not mask.any():
            raise ValueError(f"recovered consolidation missing from normalized ledger: {row.isin} {day.date()}")
        result.loc[mask, "mechanics_status"] = "AUTO_MULTIPLIER"
        result.loc[mask, "block_reason"] = None
        result.loc[mask, "multiplier_numerator"] = float(row.new_shares)
        result.loc[mask, "multiplier_denominator"] = float(row.old_shares)
        result.loc[mask, "total_share_multiplier"] = float(row.new_shares) / float(row.old_shares)
        result.loc[mask, "economic_policy"] = "FRACTION_REQUIRES_SETTLEMENT_VALUE"
        result.loc[mask, "evidence_url"] = row.source_url
        result.loc[mask, "entitlement_terms"] = f"{int(row.old_shares)}_OLD_TO_{int(row.new_shares)}_NEW"
        applied.append((row.isin, "CONSOLIDATION", "FRACTION_REQUIRES_SETTLEMENT_VALUE"))
    supplemental_count = 0
    for path in sorted((pack.parent / "event_terms_round2").glob("batch_*/supplemental_web_terms.csv")):
        supplemental = pd.read_csv(path)
        for term in supplemental.loc[supplemental.event_type.eq("RIGHTS")].itertuples(index=False):
            mask = result["isin"].eq(term.isin) & result.event_date.eq(term.event_date) & result.event_type.eq("RIGHTS")
            mask &= result.economic_policy.ne("WITHDRAWN_NO_ALLOTMENT")
            if not mask.any() or pd.Timestamp(term.event_date) > cutoff:
                continue
            result.loc[mask, "entitlement_terms"] = str(term.ratio)
            result.loc[mask, "issue_price_inr"] = pd.to_numeric(term.issue_price, errors="coerce")
            result.loc[mask, "evidence_url"] = term.source_url
            supplemental_count += 1
    # A deliberate lapse strategy needs no issue-price assumption. This is a
    # portfolio policy, not an observed zero market price for a tradable RE.
    passive = result.event_type.eq("RIGHTS") & result.mechanics_status.eq("BLOCKING")
    result.loc[passive, "mechanics_status"] = "PASSIVE_RIGHTS"
    result.loc[passive, "block_reason"] = None
    result.loc[passive, "economic_policy"] = "POLICY_NO_SUBSCRIPTION_NO_RENUNCIATION"
    result.loc[passive & result.evidence_url.isna(), "evidence_url"] = "https://www.nseindia.com/static/trade/members-faqs-rights-entitlement-trading"
    result["policy_assumption"] = result.event_type.eq("RIGHTS")
    result = result.sort_values(["isin", "event_date", "mechanics_status", "event_type"], kind="stable").reset_index(drop=True)
    return result, {"applied_pre_cutoff": len(applied), "additional_passive_rights_events": int(passive.sum()), "supplemental_rights_terms": supplemental_count, "applied_by_type": {
        kind: sum(item[1] == kind for item in applied) for kind in sorted({item[1] for item in applied})},
        "post_cutoff_excluded": int((pd.to_datetime(complex_terms.ledger_event_date) > cutoff).sum()
                               + (pd.to_datetime(consolidations.record_date) > cutoff).sum())}


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
                 terminal_raw_prices: pd.DataFrame | None = None,
                 resulting_terms: pd.DataFrame | None = None,
                 history_overlay: str | Path | None = None,
                 nominal_tickers: set[str] | None = None,
                 adjustment_dates: dict[str, str] | None = None,
                 enforce_provider_alignment: bool = True):
        if identities["isin"].duplicated().any() or identities["ticker"].duplicated().any():
            raise ValueError("executable identities must be unique")
        history_root, split_root = Path(history_root), Path(split_root)
        provider = pd.read_csv(split_root / "split_ledger.csv")
        provider["event_date"] = pd.to_datetime(provider.get("event_date"), errors="coerce").dt.normalize()
        provider_groups = {identity: frame for identity, frame in provider.groupby("isin")}
        self.resulting_terms = resulting_terms if resulting_terms is not None else pd.DataFrame()
        actions = official_actions.copy()
        if not self.resulting_terms.empty:
            for term in self.resulting_terms.itertuples(index=False):
                match = actions["isin"].eq(term.parent_isin) & actions.event_date.eq(term.event_date) & actions.event_type.eq("DEMERGER")
                actions.loc[match, "mechanics_status"] = "RESULTING_EQUITY"
                actions.loc[match, "block_reason"] = None
        actions["event_date"] = pd.to_datetime(actions.event_date, errors="raise").dt.normalize()
        actions = actions.loc[actions.event_date.le(pd.Timestamp(as_of_date))]
        self.actions = {identity: frame for identity, frame in actions.groupby("isin")}
        self.provider_alignment_blocks = {}
        self._window_cache = {}
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
                overlay_path = Path(history_overlay) / relative if history_overlay else None
                frame = pd.read_csv(overlay_path if overlay_path and overlay_path.exists() else history_root / relative)
                original_last = pd.Timestamp((adjustment_dates or {}).get(row.ticker, pd.to_datetime(frame["date"]).max()))
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
                provider_events = provider_events.loc[provider_events.event_date.le(min(cutoff_ts, original_last))].sort_values("event_date")
                provider_ratios = pd.to_numeric(provider_events.get("split_ratio"), errors="coerce").to_numpy(float)
                provider_dates = provider_events.event_date.to_numpy(dtype="datetime64[D]")
                if len(provider_ratios) and (not np.isfinite(provider_ratios).all() or (provider_ratios <= 0).any()):
                    raise ValueError("invalid provider split ratio")
                provider_suffix = np.ones(len(provider_ratios) + 1)
                if len(provider_ratios):
                    provider_suffix[:-1] = np.cumprod(provider_ratios[::-1])[::-1]
                provider_factor = provider_suffix[np.searchsorted(provider_dates, dates, side="right")]
                # Yahoo Close is already split-adjusted (despite our raw_close
                # column name). Undo the provider factor to recover nominal cash.
                nominal = raw.copy() if row.ticker in (nominal_tickers or set()) else raw * provider_factor

                identity_actions = self.actions.get(row.isin, pd.DataFrame(columns=actions.columns))
                automatic = identity_actions.loc[
                    identity_actions.mechanics_status.eq("AUTO_MULTIPLIER")
                    & identity_actions.event_date.le(cutoff_ts)
                ].sort_values(["event_date", "event_type"])
                official_ratios = pd.to_numeric(automatic.total_share_multiplier, errors="coerce").to_numpy(float)
                official_dates = automatic.event_date.to_numpy(dtype="datetime64[D]")
                if len(official_ratios) and (not np.isfinite(official_ratios).all() or (official_ratios <= 0).any()):
                    raise ValueError("invalid official multiplier")
                # Unadjusting provider prices without the corresponding holdings
                # adjustment can manufacture enormous returns. Withhold windows
                # crossing unresolved events; never assume the provider is right.
                # The opt-out is only for explicit forensic replay of old labels.
                if enforce_provider_alignment and row.ticker not in (nominal_tickers or set()):
                    unresolved = []
                    for event in provider_events.itertuples(index=False):
                        nearby = automatic.loc[automatic.event_date.between(
                            event.event_date - pd.Timedelta(days=7),
                            event.event_date + pd.Timedelta(days=7))]
                        if nearby.empty or not np.isclose(
                                nearby.total_share_multiplier.prod(), event.split_ratio,
                                rtol=.002, atol=1e-9):
                            unresolved.append(event.event_date)
                    if unresolved:
                        self.provider_alignment_blocks[row.isin] = unresolved
                official_suffix = np.ones(len(official_ratios) + 1)
                if len(official_ratios):
                    official_suffix[:-1] = np.cumprod(official_ratios[::-1])[::-1]
                official_factor = official_suffix[np.searchsorted(official_dates, dates, side="right")]
                # Yahoo Adj Close combines distributions and Yahoo's own split
                # ledger.  Remove the provider split component, then apply only
                # the official exchange multiplier to the economic return basis.
                dividend_factor = provider_adjusted / raw
                economic_adjusted = nominal / official_factor
                for array in (dates, raw, economic_adjusted, nominal, official_factor):
                    array.setflags(write=False)
                self.arrays[row.isin] = (dates, raw, economic_adjusted, nominal, official_factor)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.errors[row.isin] = str(exc)

    def simulate(self, profile, end, *, months: int | None = None,
                 mode: str = "enhanced_carry", include_journal: bool = True) -> pd.DataFrame:
        # Frozen runtime packages construct this class without __init__. Recover
        # the provider-factor transitions from their immutable arrays so they
        # receive the alignment guard too, instead of crashing or bypassing it.
        if not hasattr(self, "provider_alignment_blocks"):
            self.provider_alignment_blocks = {}
            for identity, arrays in self.arrays.items():
                dates, raw, _, nominal, _ = arrays
                basis = nominal / raw
                ratios = basis[:-1] / basis[1:]
                changes = np.flatnonzero(~np.isclose(ratios, 1., rtol=1e-7, atol=1e-9))
                actions = self.actions.get(identity)
                for index in changes:
                    day = pd.Timestamp(dates[index + 1])
                    nearby = actions.loc[
                        actions.mechanics_status.eq("AUTO_MULTIPLIER")
                        & actions.event_date.between(day-pd.Timedelta(days=7), day+pd.Timedelta(days=7))
                    ] if actions is not None else pd.DataFrame()
                    if nearby.empty or not np.isclose(nearby.total_share_multiplier.prod(), ratios[index], rtol=.002, atol=1e-9):
                        self.provider_alignment_blocks.setdefault(identity, []).append(day)
        result = super().simulate(profile, end, months=months, mode=mode, include_journal=include_journal)
        if "reason" not in result:
            result["reason"] = None
        else:
            result["reason"] = result["reason"].astype(object)
        end_ts = pd.Timestamp(end).normalize()
        start = end_ts - pd.DateOffset(months=months or profile.lookback_months)
        window_key = (start, end_ts)
        if window_key not in self._window_cache:
            blocker_ids, action_counts, fractional_events = {}, {}, {}
            for identity, actions in self.actions.items():
                window = actions.loc[actions.event_date.between(start, end_ts)]
                action_counts[identity] = len(window)
                blocking = window.loc[window.mechanics_status.eq("BLOCKING")]
                if not blocking.empty:
                    blocker_ids[identity] = "|".join(sorted(set(blocking.block_reason.astype(str))))
                automatic = window.loc[window.mechanics_status.eq("AUTO_MULTIPLIER")]
                ratios = automatic.total_share_multiplier.to_numpy(float)
                if len(ratios) and not np.isclose(ratios, np.round(ratios), rtol=0, atol=1e-10).all():
                    fractional_events[identity] = automatic.sort_values(["event_date", "event_type"])
            for identity, dates in self.provider_alignment_blocks.items():
                unresolved = [d.date().isoformat() for d in dates if start < d <= end_ts]
                if unresolved:
                    reason = 'PROVIDER_OFFICIAL_MULTIPLIER_MISMATCH:' + ','.join(unresolved)
                    blocker_ids[identity] = '|'.join(filter(None, [blocker_ids.get(identity), reason]))
            self._window_cache[window_key] = blocker_ids, action_counts, fractional_events
        blocker_ids, action_counts, fractional_events = self._window_cache[window_key]
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
            result.shares_bought, np.round(result.shares_bought), rtol=0, atol=1e-8
        )
        result.loc[fractional, "status"] = "UNRESOLVED_FRACTIONAL_ENTITLEMENT"
        result.loc[fractional, "reason"] = "OFFICIAL_MULTIPLIER_PRODUCED_FRACTIONAL_SHARES"
        result.loc[fractional, metric_columns] = np.nan
        # A later split can make a fractional consolidation entitlement look
        # integral at the terminal date. Inspect the holding at each event.
        for index in result.index[result.status.eq("AVAILABLE") & result["isin"].isin(fractional_events)]:
            identity = result.at[index, "isin"]
            events = fractional_events[identity]
            reason = self._fractional_consolidation_reason(identity, profile, end_ts,
                                                            months or profile.lookback_months,
                                                            mode, events)
            if reason:
                result.at[index, "status"] = "UNRESOLVED_FRACTIONAL_ENTITLEMENT"
                result.at[index, "reason"] = reason
                result.loc[index, metric_columns] = np.nan
        if not self.resulting_terms.empty:
            result = self._add_resulting_equity(result, profile, start, end_ts, mode, metric_columns)
        result["evidence_grade"] = "OFFICIAL_ACTIONS_WITH_YAHOO_PRICE_BASIS_RESEARCH_ONLY"
        return result

    def _fractional_consolidation_reason(self, identity, profile, end, months, mode, events):
        start = end - pd.DateOffset(months=months)
        schedule = pd.date_range(start, end - pd.Timedelta(days=1), freq=f"{profile.interval_days}D")
        dates, _, _, nominal, _ = self.arrays[identity]
        scheduled = schedule.to_numpy(dtype="datetime64[D]")
        buy = np.searchsorted(dates, scheduled)
        last = np.searchsorted(dates, np.datetime64(end.date(), "D"), side="right") - 1
        actions = list(events.itertuples(index=False))
        position = 0
        shares = cash = 0.0

        def apply_through(day):
            nonlocal position, shares
            while position < len(actions) and np.datetime64(actions[position].event_date.date(), "D") <= day:
                action = actions[position]
                shares *= float(action.total_share_multiplier)
                if not np.isclose(shares, round(shares), rtol=0, atol=1e-8):
                    return f"FRACTIONAL_{action.event_type}_ENTITLEMENT:{action.event_date.date().isoformat()}"
                position += 1
            return None

        for day, price_index in zip(scheduled, buy):
            if mode == "enhanced_carry":
                cash += profile.amount
            if price_index > last:
                continue
            executed = dates[price_index]
            reason = apply_through(executed)
            if reason:
                return reason
            available = cash if mode == "enhanced_carry" else profile.amount
            quantity = math.floor(available / float(nominal[price_index]))
            shares += quantity
            if mode == "enhanced_carry":
                cash = available - quantity * float(nominal[price_index])
        return apply_through(np.datetime64(end.date(), "D"))

    def _add_resulting_equity(self, result, profile, start, end, mode, metric_columns):
        from stock_ranker.personalized import xirr
        terms = self.resulting_terms.loc[self.resulting_terms.event_date.between(start.date().isoformat(), end.date().isoformat())]
        result["resulting_security_value"] = 0.0
        result["resulting_valuation_policy"] = "BUY_AND_HOLD_PRICE_ONLY_NO_DIVIDEND_CASH"
        schedule = pd.date_range(start, end - pd.Timedelta(days=1), freq=f"{profile.interval_days}D")
        for identity, group in terms.groupby("parent_isin"):
            matches = result.index[result["isin"].eq(identity) & result.status.eq("AVAILABLE")]
            if not len(matches):
                continue
            index = matches[0]
            dates, _, _, nominal, factors = self.arrays[identity]
            buy = np.searchsorted(dates, schedule.to_numpy(dtype="datetime64[D]"))
            last = np.searchsorted(dates, np.datetime64(end.date(), "D"), side="right") - 1
            quantities, cash = [], 0.0
            for position in buy:
                cash += profile.amount
                if position > last:
                    quantities.append(0); continue
                available = cash if mode == "enhanced_carry" else profile.amount
                q = math.floor(available / nominal[position])
                quantities.append(q)
                cash = available - q * nominal[position]
            extra, reason = 0.0, None
            for term in group.itertuples(index=False):
                event = np.datetime64(term.event_date, "D")
                # Holdings immediately before ex-date; purchases on ex-date have no entitlement.
                before = np.searchsorted(dates, event, side="left") - 1
                held = sum(q * factors[pos] / factors[before] for q, pos in zip(quantities, buy)
                           if pos <= last and dates[pos] < event) if before >= 0 else 0
                entitlement = held * term.numerator / term.denominator
                if not np.isclose(entitlement, round(entitlement), atol=1e-8, rtol=0):
                    reason = "RESULTING_FRACTION_SETTLEMENT_UNAVAILABLE:" + term.child_ticker; break
                if entitlement == 0:
                    continue
                if term.child_isin not in self.arrays:
                    reason = "RESULTING_HISTORY_UNAVAILABLE:" + term.child_ticker; break
                child_dates, _, _, child_nominal, child_factors = self.arrays[term.child_isin]
                terminal = np.searchsorted(child_dates, np.datetime64(end.date(), "D"), side="right") - 1
                if terminal < 0 or (np.datetime64(end.date(), "D") - child_dates[terminal]).astype(int) > profile.max_price_gap_days:
                    reason = "RESULTING_TERMINAL_UNAVAILABLE:" + term.child_ticker; break
                child_actions = self.actions.get(term.child_isin)
                multiplier = 1.0
                if child_actions is not None:
                    window = child_actions.loc[child_actions.event_date.gt(pd.Timestamp(term.event_date)) & child_actions.event_date.le(end)]
                    if window.mechanics_status.isin(["BLOCKING", "RESULTING_EQUITY"]).any():
                        reason = "RESULTING_NESTED_ACTION_UNRESOLVED:" + term.child_ticker; break
                    for action in window.loc[window.mechanics_status.eq("AUTO_MULTIPLIER")].itertuples():
                        multiplier *= action.total_share_multiplier
                        if not np.isclose(entitlement * multiplier, round(entitlement * multiplier), atol=1e-8, rtol=0):
                            reason = "RESULTING_FRACTION_SETTLEMENT_UNAVAILABLE:" + term.child_ticker; break
                if reason:
                    break
                extra += entitlement * multiplier * child_nominal[terminal]
            if reason:
                result.at[index, "status"] = "UNRESOLVED_CORPORATE_ACTION"
                result.at[index, "reason"] = reason
                result.loc[index, metric_columns] = np.nan
                continue
            result.at[index, "resulting_security_value"] = extra
            for column in ("current_holding_value", "total_wealth", "profit_loss"):
                result.at[index, column] += extra
            denominator = result.at[index, "amount_invested"] if mode == "professor" else result.at[index, "amount_contributed"]
            result.at[index, "profit_loss_pct"] = result.at[index, "total_wealth"] / denominator - 1 if denominator else np.nan
            if mode != "professor":
                wealth = result.at[index, "total_wealth"]
                result.at[index, "xirr"] = xirr([*schedule, end], [-profile.amount] * len(schedule) + [wealth])
                result.at[index, "target_attainment"] = wealth / result.at[index, "target_wealth"]
                result.at[index, "target_shortfall"] = max(0, 1 - result.at[index, "target_attainment"])
        return result
