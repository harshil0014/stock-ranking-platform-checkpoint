"""Final retrospective diagnostics for distinct championship contenders."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import numpy as np
import pandas as pd

from research.runners import personalized_championship as c
from research.runners import personalized_history_challenger as h


def selected_configurations(championship):
    table = pd.read_csv(championship / "round2_leaderboard.csv")
    by_candidate = table.sort_values("utility_vs_champion", ascending=False).drop_duplicates("candidate")
    primary = table.loc[table.eligible].sort_values("utility_vs_champion", ascending=False).iloc[0]
    extras = by_candidate.loc[~by_candidate.candidate.eq(primary.candidate)].head(2)
    return pd.concat([primary.to_frame().T, extras], ignore_index=True)


def score_dates(raw, augmented, candidate, params, weight, dates, exposed):
    hist = pd.concat([augmented["training_panel"], augmented["validation_predictions"],
        augmented["supplementary_predictions"]], ignore_index=True)
    outputs = []
    for day in dates:
        panel_name = "supplementary_predictions" if exposed else "validation_predictions"
        target = augmented[panel_name].loc[augmented[panel_name].decision_date.eq(day)].copy()
        pred, _ = c.fit_predict(c.mature_before(hist, day), target, c.RECIPES[candidate[1]],
                                candidate[0], candidate[2], params, 20261001)
        target["model_score"] = pred
        target["challenger_score"] = h.blend(target, "model_score", weight)
        old = raw[panel_name].loc[raw[panel_name].decision_date.eq(day)].copy()
        old["champion_score"] = h.blend(old, "lightgbm_lambdarank_score", .67)
        target["champion_score"] = old.champion_score.to_numpy()
        outputs.append(target)
    return pd.concat(outputs, ignore_index=True)


def top_set(group, score, n=20):
    return set(group.dropna(subset=[score]).sort_values([score, "isin"], ascending=[False, True]).head(n)["isin"])


def extra_metrics(frame, score):
    rows = []
    for (day, profile), group in frame.groupby(["decision_date", "profile_name"]):
        eligible = group.dropna(subset=[score, "future_xirr", "future_shortfall", "future_drawdown"])
        top = eligible.sort_values([score, "isin"], ascending=[False, True]).head(20)
        rows.append({"decision_date": day, "profile": profile,
            "winsorized_mean_xirr_top20": top.future_xirr.clip(-1, 3).mean(),
            "top20_xirr_over_300pct_count": int(top.future_xirr.gt(3).sum()),
            "top20_worst_drawdown": top.future_drawdown.min(),
            "top20_short_history_share": top.cagr_5y_observed.ne(1).mean()})
    return pd.DataFrame(rows)


def sector_metrics(frame, score, facts):
    sector = facts.drop_duplicates("isin").set_index("isin")["derived_research_sector"]
    base = frame.loc[frame.profile_name.eq("base7500")].copy()
    base["sector"] = base["isin"].map(sector)
    rows = []
    for (day, sector_name), group in base.groupby(["decision_date", "sector"]):
        comparable = group.dropna(subset=["future_xirr", "future_shortfall", score])
        if len(comparable) < 20:
            continue
        top = comparable.sort_values([score, "isin"], ascending=[False, True]).head(5)
        rows.append({"decision_date": day, "sector": sector_name, "n": len(comparable),
            "top5_shortfall": top.future_shortfall.mean(), "top5_median_xirr": top.future_xirr.median()})
    return pd.DataFrame(rows)


def current_audit(frame, champion, facts, audit_ticker):
    identity = facts.drop_duplicates("isin")[["isin", "ticker", "derived_research_sector"]]
    ticker_isin = identity.loc[identity.ticker.eq(audit_ticker), "isin"].iloc[0]
    sector = identity.loc[identity.ticker.eq(audit_ticker), "derived_research_sector"].iloc[0]
    rows = []
    for name, source, score in (("champion", champion, "selected_ensemble_score"),
                                ("challenger", frame, "challenger_score")):
        one = source.loc[source.profile_name.eq("base7500")].dropna(subset=[score]).merge(
            identity, on="isin", validate="one_to_one")
        one = one.sort_values([score, "isin"], ascending=[False, True]).reset_index(drop=True)
        within = one.loc[one.derived_research_sector.eq(sector)].reset_index(drop=True)
        rank = int(np.flatnonzero(one["isin"].eq(ticker_isin))[0] + 1)
        srank = int(np.flatnonzero(within["isin"].eq(ticker_isin))[0] + 1)
        rows.append({"strategy": name, "universe_n": len(one),
            "universe_short_history_share": float(one.cagr_5y_observed.ne(1).mean()) if "cagr_5y_observed" in one else None,
            "top20_short_history_share": float(one.head(20).cagr_5y_observed.ne(1).mean()) if "cagr_5y_observed" in one else None,
            "top50_short_history_share": float(one.head(50).cagr_5y_observed.ne(1).mean()) if "cagr_5y_observed" in one else None,
            "top100_short_history_share": float(one.head(100).cagr_5y_observed.ne(1).mean()) if "cagr_5y_observed" in one else None,
            "audited_ticker": audit_ticker, "overall_rank": rank, "sector": sector, "sector_rank": srank,
            "sector_top10": json.dumps(within.head(10).ticker.to_list())})
    return rows


def run(championship, output, audit_ticker):
    output.mkdir(parents=True, exist_ok=False)
    configs = selected_configurations(championship)
    configs.to_csv(output / "contenders.csv", index=False)
    raw = h.load_panels()
    features = pd.read_csv(championship / "history_features.csv.gz")
    augmented = {name: h.attach(panel, features) for name, panel in raw.items()}
    facts = h.load_company_fact_snapshot(h.resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    frozen = pd.read_csv(h.FREEZE / "rankings.csv.gz", low_memory=False)
    frozen = h.attach(frozen, features)
    all_metrics, all_extra, all_turnover, all_sector, all_current = [], [], [], [], []
    for record in configs.itertuples(index=False):
        candidate = tuple(record.candidate.split("|"))
        params = json.loads(c.PROTOCOL.read_text())["round2_parameter_sets"][record.params]
        weight = float(record.goal_weight)
        name = f"{record.candidate}@{record.params}@{weight:.2f}"
        for part, dates in (("development", ["2023-06-30", "2023-12-31"]),
                            ("exposed", ["2025-03-31", "2025-06-30"])):
            frame = score_dates(raw, augmented, candidate, params, weight, dates, part == "exposed")
            old = h.evaluate(frame, "champion_score")
            new = h.evaluate(frame, "challenger_score")
            for metric in h.METRICS:
                all_metrics.append({"candidate": name, "partition": part, "metric": metric,
                    "champion": old[metric].mean(), "challenger": new[metric].mean(),
                    "delta": new[metric].mean() - old[metric].mean()})
            for strategy, score in (("champion", "champion_score"), ("challenger", "challenger_score")):
                extra = extra_metrics(frame, score)
                extra["candidate"], extra["partition"], extra["strategy"] = name, part, strategy
                all_extra.append(extra)
                sectors = sector_metrics(frame, score, facts)
                sectors["candidate"], sectors["partition"], sectors["strategy"] = name, part, strategy
                all_sector.append(sectors)
                for profile, group in frame.groupby("profile_name"):
                    sets = [top_set(g, score) for _, g in group.groupby("decision_date", sort=True)]
                    if len(sets) == 2:
                        all_turnover.append({"candidate": name, "partition": part, "profile": profile,
                            "strategy": strategy, "top20_replacement_fraction": 1 - len(sets[0] & sets[1]) / 20})
        history = pd.concat([augmented["training_panel"], augmented["validation_predictions"],
                             augmented["supplementary_predictions"]], ignore_index=True)
        pred, model = c.fit_predict(c.mature_before(history, "2026-09-18"), frozen,
            c.RECIPES[candidate[1]], candidate[0], candidate[2], params, 20261001)
        current = frozen.copy()
        current["model_score"] = pred
        current["challenger_score"] = h.blend(current, "model_score", weight)
        audit = current_audit(current, frozen, facts, audit_ticker)
        for item in audit:
            item["candidate"] = name
        all_current.extend(audit)
        current[["isin", "profile_name", "challenger_score", "cagr_5y", "cagr_5y_source",
                 "cagr_5y_observed", "history_months", "days_since_recorded_high",
                 "distance_from_recorded_high", "full_history_max_drawdown"]].to_csv(
                     output / ("current_" + str(len(all_current)) + ".csv.gz"), index=False)
        if candidate[0] == "lgbm":
            current_ticker = current.loc[current["isin"].eq(
                facts.loc[facts.ticker.eq(audit_ticker), "isin"].iloc[0]) & current.profile_name.eq("base7500")]
            contribution = model.predict(current_ticker[c.RECIPES[candidate[1]]], pred_contrib=True)[0]
            (output / ("contributions_" + str(len(all_current)) + ".json")).write_text(json.dumps(
                {"candidate": name, "ticker": audit_ticker,
                 "feature_contributions": dict(zip([*c.RECIPES[candidate[1]], "bias"], map(float, contribution)))}, indent=2))
        print(name, flush=True)
    pd.DataFrame(all_metrics).to_csv(output / "champion_vs_contenders.csv", index=False)
    pd.concat(all_extra).to_csv(output / "extreme_return_and_history.csv", index=False)
    pd.DataFrame(all_turnover).to_csv(output / "turnover.csv", index=False)
    pd.concat(all_sector).to_csv(output / "sector_slices.csv", index=False)
    pd.DataFrame(all_current).to_csv(output / "current_missing_history_audit.csv", index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--championship", type=Path, default=c.OUTPUT)
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/personalized-championship/audit-v1")
    parser.add_argument("--audit-ticker", required=True)
    args = parser.parse_args()
    run(args.championship, args.output, args.audit_ticker)
