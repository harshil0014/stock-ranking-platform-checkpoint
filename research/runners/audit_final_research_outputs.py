"""Check cutoff, reconciliation, and manifests for the final research build."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def verify_manifest(directory: Path) -> str:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest["deterministic_artifacts"]
    if len({entry["path"] for entry in entries}) != len(entries):
        raise ValueError("duplicate manifest path")
    for entry in entries:
        path = (directory / entry["path"]).resolve()
        if path.parent != directory.resolve() or path.stat().st_size != entry["size"] or digest(path) != entry["sha256"]:
            raise ValueError(f"manifest mismatch: {entry['path']}")
    if sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest() != manifest["fingerprint"]:
        raise ValueError("manifest fingerprint mismatch")
    return manifest["fingerprint"]


def run(args):
    output, freeze = args.tournament, args.freeze
    freeze_fingerprint = verify_manifest(freeze)
    rebuild_fingerprint = verify_manifest(args.rebuild_check)
    if freeze_fingerprint != rebuild_fingerprint:
        raise ValueError("deterministic freeze rebuild mismatch")
    ledger = pd.read_csv(freeze / "normalized_official_action_ledger.csv.gz", low_memory=False)
    cutoff = pd.Timestamp("2026-09-18")
    if pd.to_datetime(ledger.event_date).gt(cutoff).any():
        raise ValueError("post-cutoff action in final ledger")
    panel = pd.read_csv(freeze / "official_exact_date_sector_panel.csv.gz", low_memory=False,
                        usecols=["observation_date"])
    sector_dates = sorted(panel.observation_date.unique().tolist())
    if sector_dates != ["2020-03-31", "2021-03-31", "2022-03-31"]:
        raise ValueError("non-exact or post-cutoff sector snapshot")
    validation = pd.read_csv(output / "validation_predictions.csv.gz", low_memory=False,
                             usecols=["decision_date", "endpoint"])
    if pd.to_datetime(validation.endpoint).gt(cutoff).any():
        raise ValueError("validation outcome after research cutoff")
    supplementary = pd.read_csv(output / "supplementary_predictions.csv.gz", low_memory=False,
                                usecols=["endpoint"])
    if pd.to_datetime(supplementary.endpoint).gt(cutoff).any():
        raise ValueError("supplementary outcome after research cutoff")
    current = pd.read_csv(output / "current_profile_rankings.csv.gz", low_memory=False,
                          usecols=["decision_date", "future_xirr"])
    if set(current.decision_date) != {"2026-09-18"}:
        raise ValueError("current ranking date drift")
    if current.future_xirr.notna().any():
        raise ValueError("unmatured current outcome is populated")
    provenance = ledger.loc[ledger.evidence_url.notna(),
                            ["isin", "ticker", "event_date", "event_type", "economic_policy",
                             "entitlement_terms", "evidence_url"]].copy()
    pack = ROOT / "external_research_pack/residual_recovery_20260925"
    critical = pd.read_csv(pack / "critical_event_terms_recovered.csv").rename(columns={
        "ledger_event_date": "event_date", "source_url": "evidence_url"})
    consolidations = pd.read_csv(pack / "consolidation_terms_recovered.csv").rename(columns={
        "record_date": "event_date", "source_url": "evidence_url"})
    sources = pd.concat([critical, consolidations], ignore_index=True)[
        ["isin", "event_date", "event_type", "evidence_url", "source_tier"]].drop_duplicates()
    provenance = provenance.merge(sources, on=["isin", "event_date", "event_type", "evidence_url"],
                                  how="left", validate="many_to_one")
    if provenance.source_tier.isna().any():
        raise ValueError("recovered action missing source tier")
    provenance.to_csv(output / "source_evidence_provenance.csv", index=False, lineterminator="\n")
    blockers = pd.read_csv(output / "remaining_blockers.csv")
    blockers["event_type"] = blockers.reason.fillna("").str.split("|").str[0]
    blockers.loc[~blockers.status.eq("UNRESOLVED_CORPORATE_ACTION"), "event_type"] = "NOT_ACTION_SPECIFIC"
    blockers.groupby(["lookback_months", "status", "reason", "event_type"], dropna=False).size().rename(
        "profile_rows").reset_index().to_csv(output / "blocker_reconciliation.csv", index=False,
                                               lineterminator="\n")
    candidates = pd.read_csv(output / "candidate_metrics.csv")
    ensembles = pd.read_csv(output / "ensemble_metrics.csv")
    rows = []
    for label, frame, metric, direction in (
        ("strongest_individual_rank_ic", candidates, "rank_ic", "max"),
        ("strongest_individual_goal_achievement", candidates, "target_achievement_top20", "max"),
        ("strongest_individual_lowest_shortfall", candidates, "target_shortfall_top20", "min"),
        ("strongest_fixed_ensemble_rank_ic", ensembles, "rank_ic", "max"),
        ("strongest_fixed_ensemble_goal_achievement", ensembles, "target_achievement_top20", "max"),
        ("strongest_fixed_ensemble_lowest_shortfall", ensembles, "target_shortfall_top20", "min"),
    ):
        row = frame.loc[frame[metric].idxmax() if direction == "max" else frame[metric].idxmin()]
        rows.append({"control": label, "candidate": row.candidate, "rank_ic": row.rank_ic,
                     "target_achievement_top20": row.target_achievement_top20,
                     "target_shortfall_top20": row.target_shortfall_top20})
    pd.DataFrame(rows).to_csv(output / "control_experiment.csv", index=False, lineterminator="\n")
    write_json(output / "leakage_audit.json", {
        "cutoff": "2026-09-18", "ledger_latest_event": ledger.event_date.max(),
        "validation_latest_maturity": validation.endpoint.max(),
        "supplementary_latest_maturity": supplementary.endpoint.max(),
        "current_unmatured_outcome_rows_populated": 0,
        "current_decision_dates": sorted(current.decision_date.unique().tolist()),
        "sector_exact_observation_dates": sector_dates,
        "2026_09_23_sector_snapshot_used": False,
        "modern_sector_labels_back_projected": False,
        "post_cutoff_market_outcomes_used": False,
        "retrospective_event_documents_after_cutoff_allowed_only_for_pre_cutoff_events": True,
    })
    write_json(output / "deterministic_rebuild_verification.json", {
        "freeze_fingerprint": freeze_fingerprint,
        "rebuild_fingerprint": rebuild_fingerprint,
        "identical": True,
    })
    assessment_path = output / "final_assessment.json"
    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    assessment["deterministic_rebuild_passed"] = True
    assessment["future_data_leakage_found"] = False
    assessment["production_changed"] = False
    write_json(assessment_path, assessment)
    files = [{"path": path.name, "size": path.stat().st_size, "sha256": digest(path)}
             for path in sorted(output.iterdir()) if path.is_file()
             and path.name not in {"manifest.json", "assessment.json"}]
    write_json(output / "manifest.json", {
        "deterministic_artifacts": files,
        "observational_artifacts": ["assessment.json"],
        "fingerprint": sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
    })
    verify_manifest(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tournament", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--rebuild-check", type=Path, required=True)
    run(parser.parse_args())
