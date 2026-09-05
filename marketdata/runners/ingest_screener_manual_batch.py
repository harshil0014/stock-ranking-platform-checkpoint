"""Ingest one hash-pinned manual Screener workbook ZIP without network access."""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.screener_historical_fundamentals import (  # noqa: E402
    SCREENER_HISTORICAL_CONTRACT_VERSION,
    build_screener_pit_cohorts,
    official_clock_from_availability,
    sha256_file,
)
from stock_ranker.screener_manual_batch import (  # noqa: E402
    BATCH_SCHEMA_VERSION,
    ingest_screener_manual_batch,
)


RANKING_DATES = [
    date(2022, 8, 5), date(2023, 8, 7), date(2024, 8, 7),
    date(2025, 8, 7), date(2026, 8, 21),
]


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(
        path, index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g"
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )


def _fingerprint(frame: pd.DataFrame, columns: list[str]) -> str:
    stable = frame.loc[:, columns].copy()
    for column in stable.columns:
        if pd.api.types.is_datetime64_any_dtype(stable[column]):
            stable[column] = stable[column].map(lambda value: value.isoformat())
    payload = stable.to_csv(index=False, lineterminator="\n", float_format="%.17g")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cohort_map(frame: pd.DataFrame) -> dict[str, int]:
    return {
        str(row["ranking_date"]): int(row["pit_fundamental_count"])
        for row in frame.to_dict("records")
    }


def _union_with_frozen(selected: pd.DataFrame, frozen_root: Path) -> pd.DataFrame:
    rows = []
    for ranking_date in RANKING_DATES:
        frozen_path = frozen_root / ranking_date.isoformat() / "research_v2.csv"
        if not frozen_path.is_file():
            continue
        frozen = set(pd.read_csv(frozen_path)["ticker"].astype(str))
        new = set(selected.loc[
            selected["ranking_date"].astype(str).eq(ranking_date.isoformat()), "ticker"
        ].astype(str))
        rows.append({
            "ranking_date": ranking_date.isoformat(),
            "frozen_cohort_count": len(frozen),
            "screener_cohort_count": len(new),
            "overlap_count": len(frozen & new),
            "prospective_union_count": len(frozen | new),
            "prospective_addition_count": len(new - frozen),
        })
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--checklist", type=Path, required=True)
    parser.add_argument("--identity-master", type=Path, required=True)
    parser.add_argument("--acquisition-queue", type=Path, required=True)
    parser.add_argument("--availability-csv", type=Path, required=True)
    parser.add_argument("--existing-normalized", action="append", type=Path, default=[])
    parser.add_argument("--before-summary", type=Path, required=True)
    parser.add_argument("--frozen-walk-forward-root", type=Path, required=True)
    parser.add_argument("--source-observed-at", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=50)
    parser.add_argument("--priority-start", type=int, default=1)
    parser.add_argument("--allow-identical-overlap", action="store_true")
    parser.add_argument("--quarantine-conflicting-overlap", action="store_true")
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        raise ValueError(f"output directory already exists: {args.output_dir}")
    args.output_dir.mkdir(parents=True)

    availability = pd.read_csv(args.availability_csv)
    clock = official_clock_from_availability(availability)
    batch = ingest_screener_manual_batch(
        archive_path=args.archive,
        checklist=pd.read_csv(args.checklist, dtype=str, keep_default_na=False),
        identity_master=pd.read_csv(args.identity_master, dtype=str),
        acquisition_queue=pd.read_csv(args.acquisition_queue, dtype=str),
        official_clock=clock,
        source_directory=args.output_dir / "source_workbooks",
        source_observed_at=args.source_observed_at,
        ranking_dates=RANKING_DATES,
        expected_count=args.expected_count,
        priority_start=args.priority_start,
    )
    if int(batch.file_audit["file_status"].eq("ACCEPTED").sum()) == 0:
        raise ValueError("no workbooks passed batch validation")

    existing_frames = [pd.read_csv(path) for path in args.existing_normalized]
    pre_batch = pd.concat(existing_frames, ignore_index=True, sort=False)
    if pre_batch.duplicated(["isin", "period_end"]).any():
        raise ValueError("existing normalized histories overlap before batch ingestion")
    pre_batch = pre_batch.sort_values(["isin", "period_end"], kind="stable").reset_index(drop=True)
    pre_batch["period_end"] = pd.to_datetime(
        pre_batch["period_end"], format="mixed", errors="raise", utc=True
    )
    pre_batch_result = build_screener_pit_cohorts(pre_batch, clock, RANKING_DATES)
    batch_for_union = batch.normalized
    overlap_count = 0
    conflict_rows = pd.DataFrame()
    conflicting_isins: set[str] = set()
    overlap_keys = pre_batch[["isin", "period_end"]].merge(
        batch.normalized[["isin", "period_end"]], on=["isin", "period_end"], how="inner"
    ).drop_duplicates()
    if len(overlap_keys):
        if not args.allow_identical_overlap:
            raise ValueError(
                f"manual batch overlaps existing immutable history: {overlap_keys.to_dict('records')}"
            )
        compare = pre_batch.merge(
            batch.normalized, on=["isin", "period_end"], suffixes=("_existing", "_batch"),
            how="inner", validate="one_to_one",
        )
        value_columns = ["roce", "debt_to_equity", "current_pat", "prior_pat"]
        unequal = pd.Series(False, index=compare.index)
        for column in value_columns:
            unequal |= ~pd.to_numeric(compare[f"{column}_existing"]).eq(
                pd.to_numeric(compare[f"{column}_batch"])
            )
        if unequal.any():
            conflict_rows = compare.loc[unequal].copy()
            conflicting_isins = set(conflict_rows["isin"].astype(str))
            if not args.quarantine_conflicting_overlap:
                raise ValueError(
                    "overlapping Screener histories disagree on canonical values: "
                    f"{conflict_rows[['isin', 'period_end']].to_dict('records')}"
                )
        overlap_count = len(compare)
        batch_for_union = batch.normalized.merge(
            overlap_keys.assign(_overlap=True), on=["isin", "period_end"], how="left"
        ).loc[lambda frame: frame["_overlap"].isna()].drop(columns="_overlap")
        if conflicting_isins:
            batch_for_union = batch_for_union.loc[
                ~batch_for_union["isin"].astype(str).isin(conflicting_isins)
            ]
    effective_file_audit = batch.file_audit.copy()
    if conflicting_isins:
        mask = effective_file_audit["isin"].astype(str).isin(conflicting_isins)
        effective_file_audit.loc[mask, "file_status"] = "QUARANTINED"
        effective_file_audit.loc[mask, "reason"] = (
            "canonical values conflict with an existing immutable Screener history; "
            "existing record preserved"
        )
    effective_normalized = batch.normalized.loc[
        ~batch.normalized["isin"].astype(str).isin(conflicting_isins)
    ].copy()
    effective_batch_result = build_screener_pit_cohorts(effective_normalized, clock, RANKING_DATES)
    combined = pd.concat([pre_batch, batch_for_union], ignore_index=True, sort=False)
    combined = combined.sort_values(["isin", "period_end"], kind="stable").reset_index(drop=True)
    combined_result = build_screener_pit_cohorts(combined, clock, RANKING_DATES)
    before_summary = json.loads(args.before_summary.read_text(encoding="utf-8"))
    if "frozen_to_cached_cohort_union" in before_summary:
        reported_before_union = pd.DataFrame(
            before_summary["frozen_to_cached_cohort_union"]
        )[["ranking_date", "prospective_union_count"]]
    elif "prospective_union_before_after" in before_summary:
        reported_before_union = pd.DataFrame(
            before_summary["prospective_union_before_after"]
        )[["ranking_date", "after_batch_count"]].rename(
            columns={"after_batch_count": "prospective_union_count"}
        )
    else:
        raise ValueError("before summary has no recognized prospective cohort records")
    corrected_before_union = _union_with_frozen(
        pre_batch_result.accepted, args.frozen_walk_forward_root
    )
    after_union = _union_with_frozen(combined_result.accepted, args.frozen_walk_forward_root)
    comparison = reported_before_union.rename(
        columns={"prospective_union_count": "reported_before_count"}
    ).merge(
        corrected_before_union[["ranking_date", "prospective_union_count"]].rename(
            columns={"prospective_union_count": "corrected_before_batch_count"}
        ), on="ranking_date", how="outer", validate="one_to_one",
    ).merge(
        after_union[["ranking_date", "prospective_union_count"]].rename(
            columns={"prospective_union_count": "after_batch_count"}
        ), on="ranking_date", how="outer", validate="one_to_one",
    )
    comparison["pre_batch_reconciliation_delta"] = (
        comparison["corrected_before_batch_count"]
        - comparison["reported_before_count"]
    )
    comparison["batch_incremental_gain"] = (
        comparison["after_batch_count"]
        - comparison["corrected_before_batch_count"]
    )
    batch_clock_matches = effective_normalized.assign(
        period_end=lambda frame: frame["period_end"].astype(str).str[:10]
    ).merge(
        clock[["isin", "period_end"]].assign(
            period_end=lambda frame: frame["period_end"].astype(str).str[:10]
        ), on=["isin", "period_end"], how="inner", validate="one_to_one",
    )

    manifest = {
        "schema_version": BATCH_SCHEMA_VERSION,
        "contract_version": SCREENER_HISTORICAL_CONTRACT_VERSION,
        "archive_sha256": sha256_file(args.archive),
        "checklist_sha256": sha256_file(args.checklist),
        "source_observed_at": args.source_observed_at,
        "priority_start": args.priority_start,
        "priority_end": args.priority_start + args.expected_count - 1,
        "records": [row for row in batch.manifest_records if row["isin"] not in conflicting_isins],
    }
    outputs = {
        "file_audit.csv": effective_file_audit,
        "normalized_batch_history.csv": effective_normalized,
        "batch_pit_selected.csv": effective_batch_result.accepted,
        "batch_pit_rejected_periods.csv": effective_batch_result.rejected,
        "batch_pit_cohort_summary.csv": effective_batch_result.cohort_summary,
        "overlap_conflicts.csv": conflict_rows,
        "combined_normalized_history.csv": combined,
        "corrected_pre_batch_pit_selected.csv": pre_batch_result.accepted,
        "combined_pit_selected.csv": combined_result.accepted,
        "combined_pit_rejected_periods.csv": combined_result.rejected,
        "combined_pit_cohort_summary.csv": combined_result.cohort_summary,
        "prospective_union_after_batch.csv": after_union,
        "cohort_before_after.csv": comparison,
    }
    for name, frame in outputs.items():
        _write_csv(args.output_dir / name, frame)
    _write_json(args.output_dir / "batch_manifest.json", manifest)
    summary = {
        "schema_version": "screener_manual_batch_build_v1",
        "contract_version": SCREENER_HISTORICAL_CONTRACT_VERSION,
        "attempted_files": len(effective_file_audit),
        "accepted_files": int(effective_file_audit["file_status"].eq("ACCEPTED").sum()),
        "quarantined_files": int(effective_file_audit["file_status"].eq("QUARANTINED").sum()),
        "normalized_annual_records_gained": len(effective_normalized),
        "identical_existing_annual_records": overlap_count,
        "net_new_annual_records_gained": len(batch_for_union),
        "annual_records_with_official_pit_clock": len(batch_clock_matches),
        "batch_cohorts": _cohort_map(effective_batch_result.cohort_summary),
        "corrected_pre_batch_screener_cohorts": _cohort_map(pre_batch_result.cohort_summary),
        "combined_screener_cohorts": _cohort_map(combined_result.cohort_summary),
        "prospective_union_before_after": comparison.to_dict("records"),
        "batch_normalized_fingerprint": _fingerprint(
            effective_normalized,
            ["isin", "period_end", "roce", "debt_to_equity", "current_pat", "prior_pat", "source_workbook_sha256"],
        ),
        "batch_selected_fingerprint": _fingerprint(
            effective_batch_result.accepted,
            ["ranking_date", "isin", "period_end", "roce", "debt_to_equity", "current_pat", "prior_pat", "official_available_at"],
        ),
        "combined_selected_fingerprint": _fingerprint(
            combined_result.accepted,
            ["ranking_date", "isin", "period_end", "roce", "debt_to_equity", "current_pat", "prior_pat", "official_available_at"],
        ),
        "source_hashes": {
            "archive": sha256_file(args.archive),
            "checklist": sha256_file(args.checklist),
            "identity_master": sha256_file(args.identity_master),
            "acquisition_queue": sha256_file(args.acquisition_queue),
            "availability": sha256_file(args.availability_csv),
            **{f"existing:{path.name}": sha256_file(path) for path in args.existing_normalized},
        },
        "large_historical_evaluation_started": False,
    }
    _write_json(args.output_dir / "batch_summary.json", summary)
    inventory = [
        {"path": path.relative_to(args.output_dir).as_posix(), "sha256": sha256_file(path), "size": path.stat().st_size}
        for path in sorted(args.output_dir.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file() and path.name != "artifact_inventory.json"
    ]
    _write_json(args.output_dir / "artifact_inventory.json", inventory)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
