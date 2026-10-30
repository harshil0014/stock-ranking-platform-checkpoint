"""Selection stability and sector sensitivity for the preselected successor."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.runners import personalized_successor_20261002 as s


def run():
    _, panels, _, _, _ = s.prepare()
    summary = json.loads((s.OUT / "summary.json").read_text())
    choice = summary["winner"]
    recipe, label, pname = choice["candidate"].split("|")
    selections, sectors = [], []
    for part in ("validation_predictions", "supplementary_predictions"):
        frame = s.predict_dates(panels, part, s.RECIPES[recipe], label, s.PARAMS[pname])
        frame["champion_score"] = s.hist.blend(frame, "lightgbm_lambdarank_score", .67)
        if pd.isna(choice["alpha"]):
            frame["candidate_score"] = s.hist.blend(frame, "model_score", choice["goal_weight"])
        else:
            goal = frame.groupby(["decision_date", "profile_name"]).enhanced_goal_score.rank(pct=True)
            rank = frame.groupby(["decision_date", "profile_name"]).model_score.rank(pct=True)
            age = (1-frame.history_months.fillna(0).div(60).clip(0,1))*frame.cagr_5y_observed.ne(1)
            frame["candidate_score"] = ((1-choice["alpha"])*frame.champion_score+
                choice["alpha"]*(.67*goal+.33*rank)-choice["age_penalty"]*age)
        partition = "development_2023" if part.startswith("validation") else "exposed_2025"
        for (date, profile), block in frame.groupby(["decision_date", "profile_name"]):
            for kind, score in (("champion", "champion_score"), ("challenger", "candidate_score")):
                top = block.dropna(subset=[score, "future_xirr"]).sort_values(
                    [score, "isin"], ascending=[False, True]).head(20)
                selections.append({"partition": partition, "date": date, "profile": profile,
                                   "kind": kind, "top20": top["isin"].tolist()})
        base = frame.loc[frame.profile_name.eq("base7500")]
        for (date, sector), block in base.groupby(["decision_date", "sector"]):
            eligible = block.dropna(subset=["champion_score", "candidate_score", "future_xirr"])
            if len(eligible) < 20:
                continue
            row = {"partition": partition, "date": date, "sector": sector, "eligible": len(eligible)}
            for kind, score in (("champion", "champion_score"), ("challenger", "candidate_score")):
                top = eligible.sort_values([score, "isin"], ascending=[False, True]).head(5)
                row[kind + "_shortfall"] = top.future_shortfall.mean()
                row[kind + "_achievement"] = top.future_shortfall.eq(0).mean()
                row[kind + "_median_xirr"] = top.future_xirr.median()
            sectors.append(row)
    selection = pd.DataFrame(selections)
    turnover = []
    for (partition, profile, kind), block in selection.groupby(["partition", "profile", "kind"]):
        block = block.sort_values("date")
        if len(block) != 2:
            continue
        a, b = map(set, block.top20)
        turnover.append({"partition": partition, "profile": profile, "kind": kind,
                         "date_a": block.date.iloc[0], "date_b": block.date.iloc[1],
                         "replacement_fraction": 1 - len(a & b) / 20})
    pd.DataFrame(turnover).to_csv(s.OUT / "winner_turnover.csv", index=False)
    sector_frame = pd.DataFrame(sectors)
    sector_frame["shortfall_delta"] = sector_frame.challenger_shortfall-sector_frame.champion_shortfall
    sector_frame["achievement_delta"] = sector_frame.challenger_achievement-sector_frame.champion_achievement
    sector_frame.to_csv(s.OUT / "winner_sector_sensitivity.csv", index=False)
    print(pd.DataFrame(turnover).groupby(["partition", "kind"]).replacement_fraction.mean())
    print(sector_frame.groupby("partition")[["shortfall_delta", "achievement_delta"]].mean())
    print(sector_frame.groupby("partition")[["shortfall_delta", "achievement_delta"]].agg(["max", "min"]))


if __name__ == "__main__":
    run()
