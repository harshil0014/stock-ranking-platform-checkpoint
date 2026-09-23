"""Research-only whole-share simulator and executable tournament helpers."""
from __future__ import annotations

from dataclasses import fields
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from stock_ranker.personalized import InvestorProfile, xirr


FEATURES = [
    "enhanced_carry_xirr_score", "enhanced_goal_score", "price_drawdown",
    "cagr_3y", "cagr_5y", "cash_utilization", "unaffordable_rate",
]
BASE_CANDIDATES = [
    "professor_whole_share_score", "enhanced_no_carry_xirr_score",
    "enhanced_carry_xirr_score", "enhanced_goal_score",
    "historical_target_frequency_score", "global_existing_score",
    "enhanced_plus_existing_score", "ridge_executable_score",
    "ridge_without_amount_features_score", "ridge_without_goal_score",
    "cluster_rank_aggregation_score", "hist_gradient_boosting_score",
    "lightgbm_lambdarank_score",
]


def load_protocol(path: str | Path) -> tuple[dict, dict[str, InvestorProfile]]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("scope") != "GLOBAL_ONLY_FROZEN_COHORTS_WHOLE_SHARES":
        raise ValueError("executable global-only protocol required")
    allowed = {item.name for item in fields(InvestorProfile)}
    profiles = {
        name: InvestorProfile(whole_shares=True, **{key: raw[key] for key in raw if key in allowed})
        for name, raw in value["profiles"].items()
    }
    if {p.lookback_months for p in profiles.values()} - {12, 36, 60}:
        raise ValueError("profile has no frozen lookback cohort")
    if set(value["validation_decision_dates"]) & set(value["supplementary_exposed_test_dates"]):
        raise ValueError("validation and supplementary dates overlap")
    return value, profiles


class ExecutableHistoryBook:
    """Immutable raw/adjusted arrays with split-reconstructed nominal prices."""

    def __init__(self, identities: pd.DataFrame, history_root: str | Path,
                 split_root: str | Path, *, as_of_date: str):
        if identities["isin"].duplicated().any() or identities["ticker"].duplicated().any():
            raise ValueError("executable identities must be unique")
        history_root, split_root = Path(history_root), Path(split_root)
        audit = pd.read_csv(split_root / "acquisition_audit.csv").set_index("isin")
        ledger = pd.read_csv(split_root / "split_ledger.csv")
        ledger["event_date"] = pd.to_datetime(ledger.get("event_date"), errors="coerce")
        grouped = {identity: frame for identity, frame in ledger.groupby("isin")}
        cutoff = np.datetime64(pd.Timestamp(as_of_date).date(), "D")
        self.arrays, self.errors, self.cache = {}, {}, {}
        for row in identities[["isin", "ticker"]].sort_values("isin").itertuples(index=False):
            try:
                if row.isin not in audit.index or audit.loc[row.isin, "status"] != "SUCCESS":
                    raise ValueError("split acquisition unavailable")
                relative = Path(f"{row.ticker}.csv")
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("unsafe history path")
                frame = pd.read_csv(history_root / relative)
                dates = pd.to_datetime(frame["date"], errors="raise").to_numpy(dtype="datetime64[D]")
                raw = pd.to_numeric(frame["raw_close"], errors="raise").to_numpy(float)
                adjusted = pd.to_numeric(frame["adjusted_close"], errors="raise").to_numpy(float)
                keep = dates <= cutoff
                dates, raw, adjusted = dates[keep], raw[keep], adjusted[keep]
                if len(dates) < 2 or np.isnat(dates).any() or (np.diff(dates).astype(int) <= 0).any():
                    raise ValueError("invalid execution dates")
                if not np.isfinite(raw).all() or not np.isfinite(adjusted).all() or (raw <= 0).any() or (adjusted <= 0).any():
                    raise ValueError("invalid price history")
                events = grouped.get(row.isin, pd.DataFrame(columns=ledger.columns)).sort_values("event_date")
                ratios = pd.to_numeric(events.get("split_ratio"), errors="coerce").to_numpy(float)
                event_dates = pd.to_datetime(events.get("event_date"), errors="coerce").to_numpy(dtype="datetime64[D]")
                if len(ratios) and (not np.isfinite(ratios).all() or (ratios <= 0).any()):
                    raise ValueError("invalid split ratio")
                if len(ratios) and (np.abs(ratios - np.round(ratios)) > 1e-10).any():
                    raise ValueError("complex split ratio")
                if len(ratios) and (ratios < 1).any():
                    raise ValueError("reverse split ratio")
                suffix = np.ones(len(ratios) + 1)
                if len(ratios):
                    suffix[:-1] = np.cumprod(ratios[::-1])[::-1]
                factor = suffix[np.searchsorted(event_dates, dates, side="right")]
                nominal = raw * factor
                for array in (dates, raw, adjusted, nominal, factor):
                    array.setflags(write=False)
                self.arrays[row.isin] = (dates, raw, adjusted, nominal, factor)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.errors[row.isin] = str(exc)

    def simulate(self, profile: InvestorProfile, end, *, months: int | None = None,
                 mode: str = "enhanced_carry", include_journal: bool = True) -> pd.DataFrame:
        if mode not in {"professor", "enhanced_no_carry", "enhanced_carry"}:
            raise ValueError("unknown executable cash policy")
        end = pd.Timestamp(end).normalize()
        start = end - pd.DateOffset(months=months or profile.lookback_months)
        schedule = pd.date_range(start, end - pd.Timedelta(days=1), freq=f"{profile.interval_days}D")
        scheduled = schedule.to_numpy(dtype="datetime64[D]")
        terminal = np.datetime64(end.date(), "D")
        years = (end - schedule).days.to_numpy() / 365
        target = float(profile.amount * np.power(1 + profile.target_cagr, years).sum())
        cache_key = (profile.amount, profile.interval_days, profile.max_price_gap_days,
                     profile.fixed_fee, profile.fee_bps, end.date().isoformat(),
                     months or profile.lookback_months, mode)
        if not include_journal and cache_key in self.cache:
            result = self.cache[cache_key].copy(deep=True)
            result["target_wealth"] = target
            if mode != "professor":
                result["target_attainment"] = result.total_wealth / target
                result["target_shortfall"] = (1 - result.target_attainment).clip(lower=0)
            return result
        records = []
        for identity in sorted(set(self.arrays) | set(self.errors)):
            base = {"isin": identity, "status": "INVALID_HISTORY", "mode": mode,
                    "as_of_date": end.date().isoformat(), "target_wealth": target,
                    "amount_per_contribution": profile.amount,
                    "contribution_count": len(schedule), "evidence_grade": "PROVIDER_SPLIT_LEDGER_RESEARCH_ONLY"}
            if identity not in self.arrays:
                base["reason"] = self.errors[identity]
                records.append(base)
                continue
            dates, raw, adjusted, nominal, factor = self.arrays[identity]
            buy = np.searchsorted(dates, scheduled)
            last = np.searchsorted(dates, terminal, side="right") - 1
            if last < 0 or dates[0] > scheduled[0]:
                base["status"] = "INSUFFICIENT_HISTORY"
                records.append(base); continue
            if int((terminal - dates[last]).astype(int)) > profile.max_price_gap_days:
                base["status"] = "STALE_TERMINAL"
                records.append(base); continue
            executable = buy <= last
            if executable.any() and ((dates[buy[executable]] - scheduled[executable]).astype(int) > profile.max_price_gap_days).any():
                base["status"] = "MISSING_EXECUTION_PRICE"
                records.append(base); continue
            cash = invested = excluded_cash = terminal_shares = 0.0
            execution_count = unaffordable = 0
            journal = []
            terminal_factor = factor[last]
            for scheduled_day, index, can_execute in zip(schedule, buy, executable):
                if mode == "enhanced_carry":
                    cash += profile.amount
                if not can_execute:
                    if mode == "enhanced_no_carry":
                        cash += profile.amount
                    elif mode == "professor":
                        excluded_cash += profile.amount
                    unaffordable += 1
                    continue
                price = float(nominal[index])
                available = cash if mode == "enhanced_carry" else profile.amount
                quantity = math.floor(available / price)
                cost = quantity * price
                if quantity <= 0:
                    unaffordable += 1
                else:
                    execution_count += 1
                    invested += cost
                    terminal_shares += quantity * factor[index] / terminal_factor
                residual = available - cost
                if mode == "enhanced_carry":
                    cash = residual
                elif mode == "enhanced_no_carry":
                    cash += residual
                else:
                    excluded_cash += residual
                if include_journal:
                    journal.append({"scheduled_date": scheduled_day.date().isoformat(),
                                    "execution_date": pd.Timestamp(dates[index]).date().isoformat(),
                                    "execution_price": price, "shares_purchased": quantity,
                                    "residual_cash": residual})
            holding_value = terminal_shares * float(nominal[last])
            contributed = profile.amount * len(schedule)
            residual_cash = cash if mode != "professor" else 0.0
            wealth = holding_value + residual_cash
            denominator = invested if mode == "professor" else contributed
            profit_pct = wealth / denominator - 1 if denominator > 0 else np.nan
            window_start = min(int(buy[0]), last) if len(buy) else 0
            window = adjusted[window_start:last + 1]
            base.update({
                "status": "AVAILABLE", "shares_bought": terminal_shares,
                "average_purchase_cost": invested / terminal_shares if terminal_shares else np.nan,
                "amount_contributed": contributed, "amount_invested": invested,
                "current_holding_value": holding_value, "residual_cash": residual_cash,
                "unused_cash_excluded_by_professor": excluded_cash if mode == "professor" else 0.0,
                "total_wealth": wealth, "profit_loss": wealth - denominator,
                "profit_loss_pct": profit_pct, "xirr": np.nan,
                "target_attainment": wealth / target if mode != "professor" else np.nan,
                "target_shortfall": max(0.0, 1 - wealth / target) if mode != "professor" else np.nan,
                "cash_utilization": invested / contributed if contributed else np.nan,
                "unaffordable_contributions": unaffordable,
                "unaffordable_rate": unaffordable / len(schedule) if len(schedule) else np.nan,
                "execution_count": execution_count, "terminal_price": float(nominal[last]),
                "terminal_price_date": pd.Timestamp(dates[last]).date().isoformat(),
                "price_drawdown": float(np.min(window / np.maximum.accumulate(window) - 1)),
                "journal": journal if include_journal else None,
            })
            for years_back in (3, 5):
                anchor = np.datetime64((end - pd.DateOffset(years=years_back)).date(), "D")
                index = np.searchsorted(dates, anchor, side="right") - 1
                base[f"cagr_{years_back}y"] = (
                    (adjusted[last] / adjusted[index]) ** (365 / int((dates[last] - dates[index]).astype(int))) - 1
                    if index >= 0 and 0 <= int((anchor - dates[index]).astype(int)) <= profile.max_price_gap_days and last > index
                    else np.nan
                )
            records.append(base)
        result = pd.DataFrame(records)
        valid = result.status.eq("AVAILABLE") & result.total_wealth.notna() if "total_wealth" in result else pd.Series(False, index=result.index)
        if mode != "professor" and valid.any():
            wealth = result.loc[valid, "total_wealth"].to_numpy(float)
            lo = np.full(len(wealth), -700 / years.max())
            hi = np.full(len(wealth), 700 / years.max())
            for _ in range(64):
                mid = (lo + hi) / 2
                future = profile.amount * np.exp(years[:, None] * mid).sum(axis=0)
                higher = future > wealth
                hi = np.where(higher, mid, hi)
                lo = np.where(higher, lo, mid)
            result.loc[valid, "xirr"] = np.expm1((lo + hi) / 2)
        if not include_journal:
            self.cache[cache_key] = result.copy(deep=True)
        return result


def rank_executable(book: ExecutableHistoryBook, profile: InvestorProfile, end,
                    evidence: pd.DataFrame) -> pd.DataFrame:
    professor = book.simulate(profile, end, mode="professor", include_journal=False)
    no_carry = book.simulate(profile, end, mode="enhanced_no_carry", include_journal=False)
    carry = book.simulate(profile, end, mode="enhanced_carry", include_journal=False)
    result = carry.rename(columns={"xirr": "enhanced_carry_xirr_score"})
    result = result.merge(
        no_carry[["isin", "xirr"]].rename(columns={"xirr": "enhanced_no_carry_xirr_score"}),
        on="isin", validate="one_to_one",
    ).merge(
        professor[["isin", "profit_loss_pct", "unused_cash_excluded_by_professor"]].rename(
            columns={"profit_loss_pct": "professor_whole_share_score"}
        ), on="isin", validate="one_to_one",
    )
    if profile.horizon_months > profile.lookback_months:
        scenarios = []
    else:
        offsets = sorted(set(np.linspace(0, profile.lookback_months - profile.horizon_months, 4).astype(int)))
        scenarios = [
            book.simulate(profile, pd.Timestamp(end) - pd.DateOffset(months=int(offset)),
                          months=profile.horizon_months, mode="enhanced_carry", include_journal=False).set_index("isin")["target_shortfall"].rename(offset)
            for offset in offsets
        ]
    shortfalls = pd.concat(scenarios, axis=1).reindex(result["isin"]) if scenarios else pd.DataFrame(index=result["isin"])
    result["goal_windows"] = shortfalls.notna().sum(axis=1).to_numpy()
    result["enhanced_goal_score"] = (-shortfalls.pow(2).mean(axis=1).where(shortfalls.notna().all(axis=1))).to_numpy()
    result["historical_target_frequency_score"] = (
        shortfalls.eq(0).sum(axis=1).div(shortfalls.notna().sum(axis=1)).where(shortfalls.notna().sum(axis=1) > 0)
    ).to_numpy()
    result = result.merge(evidence, on="isin", how="left", validate="one_to_one")
    ranks = result[["enhanced_goal_score", "global_existing_score"]].rank(pct=True)
    result["enhanced_plus_existing_score"] = ranks.mean(axis=1).where(ranks.notna().all(axis=1))
    return result


def fit_fixed_models(training: pd.DataFrame, target: pd.DataFrame, protocol: dict) -> tuple[pd.DataFrame, list[dict]]:
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.inspection import permutation_importance
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    config = protocol["candidate_policy"]
    training = training.loc[training.future_xirr.notna() & training.enhanced_carry_xirr_score.notna()].sort_values(
        ["decision_date", "profile_name", "isin"], kind="stable"
    )
    output, audits = target.copy(), []
    groups = {
        "ridge_executable": FEATURES,
        "ridge_without_amount_features": [c for c in FEATURES if c not in config["amount_feature_columns"]],
        "ridge_without_goal": [c for c in FEATURES if c != "enhanced_goal_score"],
    }
    valid = output.enhanced_carry_xirr_score.notna()
    for name, columns in groups.items():
        model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                              Ridge(alpha=float(config["ridge_alpha"])))
        model.fit(training[columns], training.future_xirr.clip(-1, 3))
        output[name + "_score"] = np.nan
        output.loc[valid, name + "_score"] = model.predict(output.loc[valid, columns])
        audits.append({"candidate": name, "features": columns, "train_rows": len(training),
                       "alpha": config["ridge_alpha"]})
    correlation = training[FEATURES].corr(method="spearman").abs()
    clusters, pending = [], set(FEATURES)
    threshold = float(config["correlation_cluster_threshold"])
    while pending:
        component = {min(pending)}
        while True:
            enlarged = component | {c for c in pending if any(correlation.loc[c, k] >= threshold for k in component)}
            if enlarged == component:
                break
            component = enlarged
        clusters.append(sorted(component)); pending -= component
    normalized = output.groupby(["decision_date", "profile_name"])[FEATURES].rank(pct=True)
    votes = pd.concat([normalized[group].mean(axis=1).where(normalized[group].notna().all(axis=1))
                       for group in clusters], axis=1)
    output["cluster_rank_aggregation_score"] = votes.mean(axis=1).where(votes.notna().all(axis=1))
    audits.append({"candidate": "cluster_rank_aggregation", "clusters": clusters, "threshold": threshold})
    imputer = SimpleImputer(strategy="median")
    train_x, test_x = imputer.fit_transform(training[FEATURES]), imputer.transform(output.loc[valid, FEATURES])
    train_y = training.future_xirr.clip(-1, 3)
    hist = HistGradientBoostingRegressor(**config["hist_gradient_boosting"], random_state=int(config["seed"]))
    hist.fit(train_x, train_y)
    output["hist_gradient_boosting_score"] = np.nan
    output.loc[valid, "hist_gradient_boosting_score"] = hist.predict(test_x)
    sample = np.linspace(0, len(training) - 1, min(5000, len(training)), dtype=int)
    importance = permutation_importance(hist, train_x[sample], train_y.iloc[sample], n_repeats=3,
                                        random_state=int(config["seed"]), n_jobs=1)
    audits.append({"candidate": "hist_gradient_boosting", "features": FEATURES, "train_rows": len(training),
                   "parameters": config["hist_gradient_boosting"],
                   "permutation_importance": dict(zip(FEATURES, importance.importances_mean.tolist()))})
    try:
        from lightgbm import LGBMRanker
        ordered = training.sort_values(["decision_date", "profile_name", "isin"], kind="stable")
        labels = ordered.groupby(["decision_date", "profile_name"]).future_xirr.rank(pct=True).mul(4).clip(upper=3).astype(int)
        ranker = LGBMRanker(**config["lightgbm_lambdarank"], random_state=int(config["seed"]), n_jobs=1,
                            verbosity=-1, deterministic=True, force_col_wise=True)
        sizes = ordered.groupby(["decision_date", "profile_name"], sort=False).size().to_list()
        ranker.fit(ordered[FEATURES], labels, group=sizes)
        output["lightgbm_lambdarank_score"] = np.nan
        output.loc[valid, "lightgbm_lambdarank_score"] = ranker.predict(output.loc[valid, FEATURES])
        audits.append({"candidate": "lightgbm_lambdarank", "features": FEATURES,
                       "train_rows": len(ordered), "parameters": config["lightgbm_lambdarank"],
                       "importance": dict(zip(FEATURES, ranker.feature_importances_.tolist()))})
    except ImportError:
        output["lightgbm_lambdarank_score"] = np.nan
        audits.append({"candidate": "lightgbm_lambdarank", "status": "INSUFFICIENT EVIDENCE"})
    return output, audits


def common_metrics(panel: pd.DataFrame) -> pd.DataFrame:
    from stock_research.personalized_validation import ranking_metrics
    rows = []
    required = [*BASE_CANDIDATES, "future_xirr", "future_shortfall", "future_drawdown"]
    for (day, profile), group in panel.groupby(["decision_date", "profile_name"], sort=True):
        common = group.dropna(subset=required)
        for candidate in BASE_CANDIDATES:
            rows.append({"decision_date": day, "profile": profile, "candidate": candidate,
                         "cohort": "common", **ranking_metrics(common, candidate)})
    return pd.DataFrame(rows)
