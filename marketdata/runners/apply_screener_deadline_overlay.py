from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from stock_ranker.screener_data_bundle import (
    SCREENER_BUNDLE_VERSION,
    accept_screener_data_bundle,
    build_coverage_audit,
    merge_screener_market_exports,
)
from stock_ranker.screener_historical_fundamentals import sha256_file


ROOT = Path(__file__).resolve().parents[2]

SCREENER_ROOT = (
    ROOT / "data" / "company_facts" / "providers" / "screener_bundle"
)

SCREENER_STATE = SCREENER_ROOT / "accepted_state.json"
FACT_ROOT = ROOT / "data" / "company_facts"
FACT_STATE = FACT_ROOT / "accepted_state.json"


IDENTITY_COLUMNS = {
    "Name",
    "BSE Code",
    "NSE Code",
    "ISIN Code",
    "Industry Group",
    "Industry",
}


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def present(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    return series.notna() & text.ne("") & text.str.lower().ne("nan")


def bool_series(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .isin({"true", "1", "yes"})
    )


def normalize_identity(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    text = str(value).strip()

    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]

    return text.upper()


def load_export(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(
        path,
        dtype={
            "ISIN Code": str,
            "BSE Code": str,
            "NSE Code": str,
        },
        low_memory=False,
    )

    missing = sorted(IDENTITY_COLUMNS - set(frame.columns))

    if missing:
        raise ValueError(
            f"{path.name}: required columns missing: {missing}"
        )

    frame["ISIN Code"] = (
        frame["ISIN Code"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    bad = (
        frame["ISIN Code"].eq("")
        | frame["ISIN Code"].eq("NAN")
    )

    if bad.any():
        raise ValueError(
            f"{path.name}: missing ISIN rows = {int(bad.sum())}"
        )

    dup = frame["ISIN Code"].duplicated(keep=False)

    if dup.any():
        raise ValueError(
            f"{path.name}: duplicate ISINs found"
        )

    return frame


def merge_fresh_exports(paths: list[Path]) -> pd.DataFrame:
    frames = [load_export(path) for path in paths]

    expected_isins = set(frames[0]["ISIN Code"])

    for path, frame in zip(paths[1:], frames[1:]):
        if set(frame["ISIN Code"]) != expected_isins:
            raise ValueError(
                f"{path.name}: Screener export universe differs"
            )

    master = frames[0].set_index("ISIN Code")

    for path, incoming_frame in zip(paths[1:], frames[1:]):
        incoming = incoming_frame.set_index("ISIN Code")

        for column in (
            "Name",
            "BSE Code",
            "NSE Code",
            "Industry Group",
            "Industry",
        ):
            left = master[column]
            right = incoming[column]

            both = present(left) & present(right)

            if both.any():
                mismatch = (
                    left[both].map(normalize_identity)
                    != right[both].map(normalize_identity)
                )

                if mismatch.any():
                    raise ValueError(
                        f"{path.name}: identity conflict in {column}"
                    )

        for column in incoming.columns:
            if column not in master.columns:
                master[column] = incoming[column]
                continue

            mask = present(incoming[column])

            master.loc[mask, column] = incoming.loc[
                mask, column
            ]

    return (
        master
        .reset_index()
        .sort_values("ISIN Code", kind="stable")
        .reset_index(drop=True)
    )


def merge_sector_exports(paths: list[Path]) -> pd.DataFrame:
    """Combine disjoint Screener sector exports with fail-closed identity checks."""

    frames: list[pd.DataFrame] = []
    for path in sorted(paths):
        frame = load_export(path)
        groups = sorted(frame["Industry Group"].dropna().astype(str).str.strip().unique())
        if len(groups) != 1:
            raise ValueError(f"{path.name}: expected exactly one Screener industry group, found {groups}")
        frame = frame.copy()
        frame["Sector Export File"] = path.name
        frame["Sector Export Group"] = groups[0]
        frames.append(frame)

    master = pd.concat(frames, ignore_index=True, sort=False)
    duplicate = master["ISIN Code"].duplicated(keep=False)
    if duplicate.any():
        values = sorted(master.loc[duplicate, "ISIN Code"].unique())
        raise ValueError(f"Sector exports contain duplicate ISINs: {values[:20]}")
    return master.sort_values("ISIN Code", kind="stable").reset_index(drop=True)


def merge_sector_export_directories(directories: list[Path]) -> pd.DataFrame:
    passes = [merge_sector_exports(sorted(directory.glob("*.csv"))) for directory in directories]
    expected = set(passes[0]["ISIN Code"])
    for directory, frame in zip(directories[1:], passes[1:]):
        if set(frame["ISIN Code"]) != expected:
            raise ValueError(f"{directory}: sector-pass ISIN universe differs")
    master = passes[0].set_index("ISIN Code")
    for directory, incoming_frame in zip(directories[1:], passes[1:]):
        incoming = incoming_frame.set_index("ISIN Code")
        for column in IDENTITY_COLUMNS - {"ISIN Code"}:
            left, right = master[column], incoming[column]
            both = present(left) & present(right)
            if both.any() and (left[both].map(normalize_identity) != right[both].map(normalize_identity)).any():
                raise ValueError(f"{directory}: identity conflict in {column}")
        for column in incoming.columns:
            if column not in master.columns:
                master[column] = incoming[column]
            else:
                mask = present(incoming[column])
                master[column] = master[column].astype(object)
                master.loc[mask, column] = incoming.loc[mask, column]
    return master.reset_index().sort_values("ISIN Code", kind="stable").reset_index(drop=True)


def load_full_company_universe() -> pd.DataFrame:
    state = json.loads(
        FACT_STATE.read_text(encoding="utf-8")
    )

    snapshot = FACT_ROOT / str(state["snapshot_path"])

    facts = pd.read_csv(
        snapshot / "company_facts.csv",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    required = [
        "ticker",
        "company",
        "isin",
        "primary_exchange",
        "exchange_security_id",
    ]

    missing = [c for c in required if c not in facts.columns]

    if missing:
        raise ValueError(
            f"company facts missing universe columns: {missing}"
        )

    optional = [
        c for c in ("series", "listing_date")
        if c in facts.columns
    ]

    universe = facts[required + optional].copy()

    universe["isin"] = (
        universe["isin"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    if universe["isin"].duplicated().any():
        raise ValueError("company-fact universe has duplicate ISINs")

    return universe


def rebuild_inventory(bundle: Path) -> None:
    rows = []

    for path in sorted(bundle.rglob("*")):
        if not path.is_file():
            continue

        if path.name == "artifact_inventory.json":
            continue

        rows.append(
            {
                "path": path.relative_to(bundle).as_posix(),
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
        )

    (bundle / "artifact_inventory.json").write_bytes(
        canonical_json(rows)
    )


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument("--input", action="append")
    parser.add_argument("--sector-directory", action="append")

    parser.add_argument(
        "--batch-id",
        default="screener-deadline-additive-20260912",
    )

    args = parser.parse_args()

    if bool(args.input) == bool(args.sector_directory):
        raise SystemExit("Supply either --input or --sector-directory, but not both.")
    sector_mode = bool(args.sector_directory)
    sector_directories = [Path(value).resolve() for value in (args.sector_directory or [])]
    paths = (
        [path for directory in sector_directories for path in sorted(directory.glob("*.csv"))]
        if sector_mode else [Path(p).resolve() for p in args.input]
    )

    for path in paths:
        if not path.is_file():
            raise SystemExit(f"Missing input: {path}")

    print("Loading fresh Screener exports...")

    fresh = (
        merge_sector_export_directories(sector_directories)
        if sector_mode else merge_fresh_exports(paths)
    )

    print(f"Fresh Screener rows: {len(fresh)}")
    print(f"Fresh columns: {len(fresh.columns)}")
    print(
        f"Fresh unique ISINs: "
        f"{fresh['ISIN Code'].nunique()}"
    )

    universe = load_full_company_universe()

    print(f"Full company universe: {len(universe)}")

    fresh_market, fresh_conflicts = (
        merge_screener_market_exports(
            universe,
            fresh,
            fresh,
        )
    )

    fresh_matches = int(
        fresh_market[
            "operational_exact_isin_match"
        ].sum()
    )

    print(f"Fresh exact ISIN matches: {fresh_matches}")
    print(
        f"Fresh unresolved: "
        f"{len(universe) - fresh_matches}"
    )

    if fresh_matches < int(len(universe) * 0.99):
        raise ValueError(
            "Fresh Screener exact-ISIN coverage fell below 99%"
        )

    screener_state = json.loads(
        SCREENER_STATE.read_text(encoding="utf-8")
    )

    old_bundle = Path(
        str(screener_state["accepted_bundle_path"])
    ).resolve()

    old_market = pd.read_csv(
        old_bundle / "market_master.csv",
        low_memory=False,
    )

    old_market["isin"] = (
        old_market["isin"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    print(f"Previous Screener universe: {len(old_market)}")

    # The current accepted company-fact universe is the base.
    combined = fresh_market.set_index("isin")

    old = old_market.set_index("isin")

    # Preserve every old field. Fresh non-empty values win.
    for column in old.columns:
        old_values = old[column].reindex(combined.index)

        if column not in combined.columns:
            combined[column] = old_values
            continue

        if column in {
            "operational_exact_isin_match",
            "snapshot_exact_isin_match",
            "market_merge_status",
        }:
            continue

        # Sector exports contain a wider mix of numeric and text columns than
        # the older market-wide files.  Object dtype preserves accepted prior
        # values without coercing or truncating either representation.
        combined[column] = combined[column].astype(object)
        missing_fresh = ~present(combined[column])
        usable_old = present(old_values)

        mask = missing_fresh & usable_old

        combined.loc[mask, column] = old_values[mask]

    # Exact match flags = fresh OR prior accepted exact match.
    for flag in (
        "operational_exact_isin_match",
        "snapshot_exact_isin_match",
    ):
        current = bool_series(combined[flag])

        if flag in old.columns:
            previous = bool_series(
                old[flag].reindex(combined.index)
            )
        else:
            previous = pd.Series(
                False,
                index=combined.index,
            )

        combined[flag] = current | previous

    # Preserve old accepted status for the single company that
    # has no fresh export row. Fresh matches are accepted.
    old_status = (
        old["market_merge_status"]
        .reindex(combined.index)
        if "market_merge_status" in old.columns
        else pd.Series("", index=combined.index)
    )

    fresh_status = combined[
        "market_merge_status"
    ].astype(str)

    fresh_exact = (
        bool_series(
            combined["operational_exact_isin_match"]
        )
        | bool_series(
            combined["snapshot_exact_isin_match"]
        )
    )

    combined["market_merge_status"] = "ACCEPTED"

    quarantine = fresh_status.eq(
        "CONFLICT_QUARANTINED"
    )

    combined.loc[
        quarantine,
        "market_merge_status",
    ] = "CONFLICT_QUARANTINED"

    no_current_match = ~fresh_exact

    combined.loc[
        no_current_match,
        "market_merge_status",
    ] = "NO_CURRENT_REFERENCE"

    combined = (
        combined
        .reset_index()
        .sort_values(
            ["primary_exchange", "ticker", "isin"],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    output = (
        SCREENER_ROOT
        / "batches"
        / args.batch_id
    )

    if output.exists():
        raise SystemExit(
            f"Output already exists: {output}\n"
            "Use another --batch-id."
        )

    print(f"Creating additive bundle: {output}")

    shutil.copytree(old_bundle, output)

    merged_export_name = (
        "sector_merged_screener_export.csv" if sector_mode
        else "deadline_merged_screener_export.csv"
    )
    fresh.to_csv(
        output / merged_export_name,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        float_format="%.17g",
    )

    combined.to_csv(
        output / "market_master.csv",
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        float_format="%.17g",
    )

    # Preserve previous conflicts and append fresh audit conflicts.
    old_conflict_path = old_bundle / "market_conflicts.csv"

    old_conflicts = (
        pd.read_csv(old_conflict_path, low_memory=False)
        if old_conflict_path.is_file()
        else pd.DataFrame()
    )

    if len(old_conflicts):
        old_conflicts = old_conflicts.copy()
        old_conflicts["overlay_generation"] = "PRIOR"

    if len(fresh_conflicts):
        fresh_conflicts = fresh_conflicts.copy()
        fresh_conflicts["overlay_generation"] = (
            "SCREENER_SECTORS_20260915" if sector_mode else "FRESH_20260912"
        )

    conflict_parts = [
        frame
        for frame in (old_conflicts, fresh_conflicts)
        if len(frame)
    ]

    conflicts = (
        pd.concat(
            conflict_parts,
            ignore_index=True,
            sort=False,
        )
        if conflict_parts
        else pd.DataFrame()
    )

    conflicts.to_csv(
        output / "market_conflicts.csv",
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    workbook_audit = pd.read_csv(
        output / "workbook_audit.csv",
        low_memory=False,
    )

    normalized_history = pd.read_csv(
        output / "normalized_history.csv",
        low_memory=False,
    )

    pit_summary = pd.read_csv(
        output / "pit_summary.csv",
        low_memory=False,
    )

    coverage = build_coverage_audit(
        combined,
        workbook_audit,
        normalized_history,
        pit_summary,
    )

    coverage.to_csv(
        output / "coverage_audit.csv",
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        float_format="%.17g",
    )

    summary_path = output / "bundle_summary.json"

    summary = json.loads(
        summary_path.read_text(encoding="utf-8")
    )

    observed = datetime.now(
        timezone.utc
    ).isoformat()

    summary["source_observed_at"] = observed
    summary["clean_universe_count"] = len(combined)

    summary["operational_exact_isin_matches"] = int(
        bool_series(
            combined["operational_exact_isin_match"]
        ).sum()
    )

    summary["snapshot_exact_isin_matches"] = int(
        bool_series(
            combined["snapshot_exact_isin_match"]
        ).sum()
    )

    summary["market_conflict_rows"] = len(conflicts)

    summary["market_conflict_counts"] = (
        conflicts["conflict_type"]
        .value_counts()
        .sort_index()
        .astype(int)
        .to_dict()
        if len(conflicts)
        and "conflict_type" in conflicts.columns
        else {}
    )

    unresolved = combined.loc[
        ~(
            bool_series(
                combined["operational_exact_isin_match"]
            )
            | bool_series(
                combined["snapshot_exact_isin_match"]
            )
        ),
        ["isin", "ticker", "company"],
    ]

    overlay_key = "sector_current_overlay" if sector_mode else "deadline_current_overlay"
    summary[overlay_key] = {
        "policy": (
            "Fresh Screener sector current/reference evidence " if sector_mode else
            "Fresh Screener current/reference evidence "
        ) + (
            "overlaid additively on prior accepted Screener evidence. "
            "Fresh non-empty values win; prior fields fill gaps. "
            "Historical PIT evidence unchanged."
        ),
        "full_company_universe": len(combined),
        "fresh_export_rows": len(fresh),
        "fresh_exact_isin_matches": fresh_matches,
        "combined_exact_isin_matches": (
            len(combined) - len(unresolved)
        ),
        "combined_unresolved": len(unresolved),
        "unresolved_isins": unresolved[
            "isin"
        ].tolist(),
        "source_observed_at": observed,
    }

    source_hashes = dict(
        summary.get("source_hashes", {})
    )

    input_hash_key = "sector_inputs_20260915" if sector_mode else "deadline_inputs_20260912"
    source_hashes[input_hash_key] = {
        (f"{path.parent.name}/{path.name}" if sector_mode else path.name): sha256_file(path)
        for path in paths
    }

    merged_hash_key = (
        "sector_merged_export_20260915" if sector_mode
        else "deadline_merged_export_20260912"
    )
    source_hashes[merged_hash_key] = sha256_file(output / merged_export_name)

    summary["source_hashes"] = source_hashes

    artifact_hashes = {}

    for name in sorted(
        summary.get("artifact_hashes", {})
    ):
        artifact = output / name

        if artifact.is_file():
            artifact_hashes[name] = sha256_file(
                artifact
            )

    summary["artifact_hashes"] = artifact_hashes

    summary["frozen_science_changed"] = False

    summary["bundle_fingerprint"] = hashlib.sha256(
        canonical_json(
            {
                "schema_version": SCREENER_BUNDLE_VERSION,
                "source_hashes": source_hashes,
                "artifact_hashes": artifact_hashes,
            }
        )
    ).hexdigest()

    summary_path.write_bytes(
        canonical_json(summary)
    )

    rebuild_inventory(output)

    accepted = accept_screener_data_bundle(
        output,
        SCREENER_STATE,
        allow_quarantined_workbooks=True,
    )

    print()
    print("PASS")
    print(f"Combined universe: {len(combined)}")
    print(
        "Combined exact Screener matches: "
        f"{len(combined) - len(unresolved)}"
    )
    print(f"Unresolved: {len(unresolved)}")

    if len(unresolved):
        print(
            unresolved.to_string(index=False)
        )

    print(
        f"Fingerprint: "
        f"{accepted['bundle_fingerprint']}"
    )

    print(
        "Historical/PIT evidence preserved."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
