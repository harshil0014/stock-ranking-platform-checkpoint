"""Prepare deterministic blind prediction bundles from one frozen source cache."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.walk_forward_blind import (  # noqa: E402
    PROTOCOL_SHA256,
    apply_historical_sector_mapping,
    build_blind_snapshot,
    canonical_json_bytes,
    protocol_fingerprint,
    validate_blind_snapshot_directory,
    write_blind_snapshot,
)


RANKING_DATES = ("2022-08-05", "2023-08-07", "2024-08-07", "2025-08-07")


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def prepare(
    source_cache: Path,
    output: Path,
    protocol: Path,
    annual_mapping_path: Path,
    sector_mapping_path: Path,
    availability_rescue_path: Path | None = None,
) -> dict[str, object]:
    if output.exists():
        raise ValueError(f"blind prediction bundle already exists: {output}")
    if protocol_fingerprint(protocol) != PROTOCOL_SHA256:
        raise ValueError("frozen walk-forward protocol hash mismatch")
    acquisition = json.loads(
        (source_cache / "acquisition_summary.json").read_text(encoding="utf-8")
    )
    if acquisition.get("outcome_data_acquired") is not False:
        raise ValueError("source cache does not prove outcome-blind acquisition")
    annual_mapping = json.loads(annual_mapping_path.read_text(encoding="utf-8"))
    if annual_mapping.get("contract_identifier") != "nse_audited_standalone_fundamentals_v1":
        raise ValueError("unexpected historical accounting contract")
    sector_mapping = json.loads(sector_mapping_path.read_text(encoding="utf-8"))
    if availability_rescue_path is None:
        availability_rescue_path = ROOT / "marketdata/specifications/walk_forward_nse_availability_rescue.json"
    availability_rescue = json.loads(availability_rescue_path.read_text(encoding="utf-8"))
    if availability_rescue.get("outcome_data_acquired") is not False:
        raise ValueError("availability rescue does not prove outcome-blind acquisition")
    rescue_by_date = {
        item["ranking_date"]: item for item in availability_rescue["snapshots"]
    }
    output.mkdir(parents=True)
    date_manifests = []
    summaries = []
    for ranking_date in RANKING_DATES:
        raw = source_cache / ranking_date
        universe = pd.read_csv(raw / "historical_universe.csv")
        universe = apply_historical_sector_mapping(universe, sector_mapping, ranking_date)
        identity = pd.read_csv(raw / "identity_resolution_requested.csv")
        taxonomy_columns = [
            "historical_sector", "official_sector_code", "classification_document_id",
        ]
        identity = identity.drop(columns=taxonomy_columns, errors="ignore").merge(
            universe[["historical_symbol", *taxonomy_columns]],
            on="historical_symbol", how="left", validate="one_to_one",
        )
        true_status = pd.read_csv(raw / "price_status_repair_true.csv")
        status_by_ticker = true_status.set_index("ticker")
        for index, row in identity.iterrows():
            ticker = row["historical_symbol"]
            if ticker in status_by_ticker.index:
                identity.loc[index, "identity_resolution_status"] = status_by_ticker.loc[ticker, "status"]
                identity.loc[index, "identity_evidence"] = status_by_ticker.loc[ticker, "reason"]
        repaired = pd.read_csv(raw / "prices_repair_true.csv")
        unrepaired = pd.read_csv(raw / "prices_repair_false.csv")
        annual_summary = json.loads(
            (raw / "annual_reports" / "acquisition_summary.json").read_text(encoding="utf-8")
        )
        audit_summary = json.loads(
            (raw / "annual_report_audit" / "audit_summary.json").read_text(encoding="utf-8")
        )
        source_provenance = {
            "source_cache_relative_path": ranking_date,
            "historical_universe_sha256": _sha(raw / "historical_universe.csv"),
            "predictor_prices_repair_true_sha256": _sha(raw / "prices_repair_true.csv"),
            "predictor_prices_repair_false_sha256": _sha(raw / "prices_repair_false.csv"),
            "price_request_sha256": _sha(raw / "price_request.json"),
            "annual_report_acquisition_summary": annual_summary,
            "annual_report_audit_summary": audit_summary,
            "required_fiscal_year": annual_summary["required_fiscal_year"],
            "sector_mapping_sha256": _sha(sector_mapping_path),
            "classification_document": next(
                item for item in sector_mapping["classification_documents"]
                if ranking_date in item["applicable_ranking_dates"]
            ),
            "outcome_data_acquired": False,
        }
        if ranking_date in rescue_by_date:
            attempts = rescue_by_date[ranking_date]["attempts"]
            source_provenance["nse_availability_rescue"] = {
                "specification_sha256": _sha(availability_rescue_path),
                "attempted_count": len(attempts),
                "status_counts": {
                    status: sum(
                        row["availability_rescue"]["evidence_status"] == status
                        for row in attempts
                    )
                    for status in sorted({
                        row["availability_rescue"]["evidence_status"] for row in attempts
                    })
                },
                "outcome_data_acquired": False,
            }
        snapshot = build_blind_snapshot(
            universe, identity, repaired, unrepaired, annual_mapping,
            ranking_date, source_provenance,
        )
        date_root = output / ranking_date
        fingerprint = write_blind_snapshot(snapshot, date_root)
        validate_blind_snapshot_directory(date_root, ranking_date)
        manifest_path = date_root / "manifest.json"
        date_manifests.append({
            "ranking_date": ranking_date,
            "blind_prediction_fingerprint": fingerprint,
            "manifest_sha256": _sha(manifest_path),
        })
        baseline_exclusions = snapshot.exclusions.loc[
            snapshot.exclusions["model"].eq("BASELINE_V1")
        ]
        v2_exclusions = snapshot.exclusions.loc[
            snapshot.exclusions["model"].eq("RESEARCH_V2")
        ]
        peer_distribution = (
            snapshot.matched_baseline["eligible_peer_count"].value_counts().sort_index().to_dict()
            if not snapshot.matched_baseline.empty else {}
        )
        summaries.append({
            "ranking_date": ranking_date,
            "official_source_rows": len(snapshot.universe),
            "investable_rows": int(snapshot.universe["investable"].sum()),
            "provider_resolved_rows": int(identity["identity_resolution_status"].eq("RESOLVED").sum()),
            "baseline_eligible_count": len(snapshot.baseline_full),
            "baseline_excluded_count": len(baseline_exclusions),
            "fundamental_contract_accepted_count": len(snapshot.fundamentals),
            "research_v2_eligible_count": len(snapshot.research_v2),
            "research_v2_excluded_count": len(v2_exclusions),
            "research_v2_sector_count": int(snapshot.research_v2["sector"].nunique()) if not snapshot.research_v2.empty else 0,
            "matched_peer_size_distribution": {str(key): int(value) for key, value in peer_distribution.items()},
            "repair_affected_count": int(snapshot.repair_sensitivity["repair_status"].eq("REPAIR_AFFECTED").sum()),
            "material_repair_rank_impact_count": int(snapshot.repair_sensitivity["material_baseline_rank_impact"].sum()),
        })
    overall_fingerprint = sha256(canonical_json_bytes(date_manifests)).hexdigest()
    manifest = {
        "schema_version": 1,
        "protocol_sha256": PROTOCOL_SHA256,
        "blind_prediction_fingerprint": overall_fingerprint,
        "future_outcome_data_present": False,
        "date_manifests": date_manifests,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    (output / "summary.json").write_text(
        json.dumps({"snapshots": summaries}, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    return {"blind_prediction_fingerprint": overall_fingerprint, "snapshots": summaries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare frozen outcome-blind predictions.")
    parser.add_argument("--source-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=ROOT / "experiments/walk_forward/protocol_v1.json")
    parser.add_argument("--annual-mapping", type=Path, default=ROOT / "marketdata/specifications/walk_forward_annual_report_mapping.json")
    parser.add_argument("--sector-mapping", type=Path, default=ROOT / "marketdata/specifications/walk_forward_nse_sector_mapping.json")
    parser.add_argument("--availability-rescue", type=Path, default=ROOT / "marketdata/specifications/walk_forward_nse_availability_rescue.json")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(prepare(
            args.source_cache, args.output, args.protocol, args.annual_mapping,
            args.sector_mapping,
            args.availability_rescue,
        ), sort_keys=True, indent=2))
        return 0
    except Exception as exc:
        print(f"blind prediction preparation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
