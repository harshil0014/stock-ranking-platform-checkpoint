"""Exploratory restrained blends after the primary history tournament."""
from pathlib import Path
import argparse
import json
import sys

import numpy as np
import pandas as pd
import lightgbm as lgb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.runners import personalized_history_challenger as c

DEFAULT_OUTPUT = c.OUTPUT.parent / "hybrid-run"


def run(audit_ticker, output):
    output.mkdir(parents=True, exist_ok=False)
    original = c.load_panels()
    features = pd.read_csv(c.ROOT / "experiments/personalized-history-challenger/v6/history_features.csv.gz")
    panels = {k: c.attach(v, features) for k, v in original.items()}
    audit = json.loads((c.ROOT / "experiments/personalized-history-challenger/v6/audit.json").read_text())
    columns, params = audit["features"], audit["parameters"]
    results = []
    frames = {}
    for part, name in (("validation", "validation_predictions"), ("supplementary", "supplementary_predictions")):
        frame = panels[name].copy()
        frame["champion_score"] = c.blend(frame, "lightgbm_lambdarank_score", .67)
        frame["new_lambda"] = np.nan
        development = pd.concat([panels["training_panel"], panels["validation_predictions"]], ignore_index=True)
        for day, group in frame.groupby("decision_date"):
            training = panels["training_panel"] if part == "validation" else development
            mature = training.loc[pd.to_datetime(training.endpoint).lt(pd.Timestamp(day))]
            frame.loc[group.index, "new_lambda"], _ = c.fit_predict(mature, group, columns, params)
        frame["new_score"] = c.blend(frame, "new_lambda", .60)
        frames[part] = frame
    current = pd.read_csv(c.ROOT / "experiments/personalized-history-challenger/v6/current_challenger.csv.gz")
    facts = c.load_company_fact_snapshot(c.resolve_company_fact_snapshot(c.ROOT / "data/company_facts")).facts
    audit_isin = facts.loc[facts.ticker.eq(audit_ticker), "isin"].iloc[0]
    current["champion_score"] = current.selected_ensemble_score
    current["new_score"] = current.challenger_score
    frames["current"] = current
    for part, frame in frames.items():
        severity = (1 - frame.history_months.fillna(0).div(60).clip(0, 1)) * (1 - frame.cagr_5y_observed)
        for alpha in (.3, .4, .5, .6, .7):
            for penalty in (.15, .20, .30, .40):
                frame["hybrid_score"] = (1 - alpha) * frame.champion_score + alpha * frame.new_score - penalty * severity
                if part == "current":
                    subset = frame.loc[frame.profile_name.eq("base7500")].dropna(subset=["hybrid_score"])
                    top = subset.sort_values(["hybrid_score", "isin"], ascending=[False, True]).head(20)
                    results.append({"partition": part, "alpha": alpha, "penalty": penalty,
                        "top20_short_history_share": float(top.cagr_5y_observed.ne(1).mean()),
                        "audited_rank": int((subset.hybrid_score > subset.loc[subset["isin"].eq(audit_isin), "hybrid_score"].iloc[0]).sum() + 1)})
                else:
                    summary = c.score_summary(c.evaluate(frame, "hybrid_score"))
                    results.append({"partition": part, "alpha": alpha, "penalty": penalty, **summary})
    pd.DataFrame(results).to_csv(output / "hybrid_tournament.csv", index=False)
    alpha, penalty = .6, .4
    comparisons, slices = [], []
    for part, frame in frames.items():
        severity = (1 - frame.history_months.fillna(0).div(60).clip(0, 1)) * (1 - frame.cagr_5y_observed)
        frame["hybrid_score"] = (1 - alpha) * frame.champion_score + alpha * frame.new_score - penalty * severity
        if part == "current":
            frame.to_csv(output / "current_hybrid.csv.gz", index=False)
            continue
        old, new = c.evaluate(frame, "champion_score"), c.evaluate(frame, "hybrid_score")
        for metric in c.METRICS:
            comparisons.append({"partition": part, "metric": metric, "champion": old[metric].mean(),
                "challenger": new[metric].mean(), "delta": new[metric].mean() - old[metric].mean()})
        merged = old.merge(new, on=["decision_date", "profile"], suffixes=("_champion", "_challenger"))
        merged.insert(0, "partition", part)
        slices.append(merged)
    pd.DataFrame(comparisons).to_csv(output / "champion_vs_challenger.csv", index=False)
    pd.concat(slices).to_csv(output / "profile_slices.csv", index=False)
    frozen = pd.read_csv(c.FREEZE / "rankings.csv.gz")
    current_for_audit = frames["current"].copy()
    current_for_audit["challenger_score"] = current_for_audit.hybrid_score
    booster = lgb.Booster(model_file=str(c.ROOT / "experiments/personalized-history-challenger/v6/current_lambdarank.txt"))
    current_audit = c.current_audit(frozen, current_for_audit, features, facts, booster, columns, audit_ticker)
    (output / "audit.json").write_text(json.dumps({"alpha": alpha, "history_penalty": penalty,
        "effective_goal_weight": (1 - alpha) * .67 + alpha * .60,
        "history_confidence_severity": "(1 - min(history_months / 60, 1)) * (1 - cagr_5y_observed)",
        "new_ranker": audit["winner"], "current": current_audit}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-ticker", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    run(arguments.audit_ticker, arguments.output)
