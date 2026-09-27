"""Broad deterministic acceptance run for the d499580 website adapter."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import statistics
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from stock_ranker.personalized_product import PersonalizedRankingService, parse_profile
from run_personalized_ui_browser_acceptance import run as run_browser


CODES = ["NSE:KRISHANA", "NSE:GVT&D", "BOM:524717", "NSE:SHAILY", "NSE:WELCORP",
         "NSE:V2RETAIL", "NSE:TERASOFT", "NSE:APOLLO", "NSE:LUMAXTECH", "BOM:539997",
         "NSE:TDPOWERSYS", "NSE:INDOTECH", "NSE:CEMPRO", "BOM:522195"]


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def fingerprint(value) -> str:
    return sha256(canonical(value)).hexdigest()


def profile(amount, lookback, interval, target):
    return {"amount": amount, "lookback_months": lookback, "interval_days": interval,
            "target_cagr_percent": target, "horizon_months": 12}


def compact(result):
    personalized = [row for row in result["rows"] if row["personalized_available"]]
    execution = [[row["isin"], row["shares_bought"], row["residual_cash"],
                  row["execution_count"], row["unaffordable_rate"]] for row in personalized]
    goals = [[row["isin"], row["goal_component_percentile"], row["target_shortfall"]]
             for row in personalized]
    ranks = [[row["isin"], row["personalized_rank"], row["personalized_score"]]
             for row in personalized]
    return {"profile_fingerprint": result["profile_fingerprint"],
            "personalized_count": result["personalized_count"],
            "fallback_count": result["fallback_count"],
            "execution_sha256": fingerprint(execution), "goal_sha256": fingerprint(goals),
            "ranking_sha256": fingerprint(ranks), "engine_seconds": result["latency_seconds"]}


def run(output: Path):
    output.mkdir(parents=True, exist_ok=False)
    freeze = ROOT / "research/freezes/personalized-d499580"
    protected = {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest()
                 for path in sorted(freeze.rglob("*")) if path.is_file()}
    started = perf_counter()
    service = PersonalizedRankingService()
    load_seconds = perf_counter() - started

    reproduction = [service.reproduce_frozen_profile(name) for name in service.config["profiles"]]
    if not all(row["passed"] for row in reproduction):
        raise RuntimeError("a frozen profile did not reproduce")

    amounts = [1000, 2500, 7500, 15000, 30000, 50000]
    lookbacks, intervals, targets = [12, 36, 60], [7, 30, 90], [10, 20, 30]
    matrix, results = [], {}
    for amount in amounts:
        for lookback in lookbacks:
            for interval in intervals:
                for target in targets:
                    request = profile(amount, lookback, interval, target)
                    wall = perf_counter()
                    result = service.rank(request)
                    summary = compact(result)
                    summary.update({"amount": amount, "lookback_months": lookback,
                                    "interval_days": interval, "target_cagr_percent": target,
                                    "wall_seconds": perf_counter() - wall})
                    matrix.append(summary)
                    results[(amount, lookback, interval, target)] = summary

    amount_slice = [results[(amount, 36, 30, 20)] for amount in amounts]
    lookback_slice = [results[(7500, value, 30, 20)] for value in lookbacks]
    interval_slice = [results[(7500, 36, value, 20)] for value in intervals]
    target_slice = [results[(7500, 36, 30, value)] for value in targets]
    sensitivity = {
        "amount_reached_execution": len({row["execution_sha256"] for row in amount_slice}) > 1,
        "amount_reached_ranking": len({row["ranking_sha256"] for row in amount_slice}) > 1,
        "lookback_changed_cohort_or_execution": len({(row["personalized_count"], row["execution_sha256"]) for row in lookback_slice}) > 1,
        "lookback_reached_ranking": len({row["ranking_sha256"] for row in lookback_slice}) > 1,
        "interval_reached_execution": len({row["execution_sha256"] for row in interval_slice}) > 1,
        "interval_reached_ranking": len({row["ranking_sha256"] for row in interval_slice}) > 1,
        "target_reached_goal": len({row["goal_sha256"] for row in target_slice}) > 1,
        "target_reached_ranking": len({row["ranking_sha256"] for row in target_slice}) > 1,
    }
    if not all(sensitivity.values()):
        raise RuntimeError("a supported input did not reach its scientific dependency")

    base = profile(7500, 36, 30, 20)
    acceptance = service.rank(base, securities=CODES)
    requested = [row for row in acceptance["rows"] if row["requested_code"]]
    acceptance_rows = [{key: row[key] for key in
                        ("requested_code", "ticker", "isin", "result_type", "status", "personalized_rank",
                         "baseline_rank", "research_v2_rank", "fallback_available")} for row in requested]
    if len(acceptance_rows) != len(CODES) or not all(row["fallback_available"] for row in acceptance_rows):
        raise RuntimeError("14-stock acceptance cohort lost a product identity")

    invalid = [
        {**base, "amount": ""}, {**base, "amount": 0}, {**base, "amount": -1},
        {**base, "amount": 999}, {**base, "amount": 50001}, {**base, "lookback_months": 18},
        {**base, "interval_days": 0}, {**base, "interval_days": 30.5}, {**base, "interval_days": 91},
        {**base, "target_cagr_percent": 9}, {**base, "target_cagr_percent": 31},
        {**base, "horizon_months": 6}, {**base, "horizon_months": 24},
    ]
    invalid_results = []
    for value in invalid:
        try:
            parse_profile(value)
        except ValueError as exc:
            invalid_results.append({"input": value, "status": "REJECTED", "message": str(exc)})
        else:
            raise RuntimeError("invalid profile was accepted")

    first = service.rank(profile(2500, 60, 7, 30))
    middle = service.rank(profile(30000, 12, 90, 10))
    repeat_started = perf_counter()
    repeated = service.rank(profile(2500, 60, 7, 30))
    repeat_wall = perf_counter() - repeat_started
    deterministic = fingerprint(first["rows"]) == fingerprint(repeated["rows"])
    isolated = first["profile_fingerprint"] != middle["profile_fingerprint"] and deterministic
    with ThreadPoolExecutor(max_workers=4) as pool:
        concurrent = list(pool.map(service.rank, [base, profile(1000, 12, 7, 10),
                                                   profile(50000, 60, 90, 30), base]))
    concurrent_safe = (fingerprint(concurrent[0]["rows"]) == fingerprint(concurrent[3]["rows"])
                       and len({item["profile_fingerprint"] for item in concurrent}) == 3)
    if not deterministic or not isolated or not concurrent_safe:
        raise RuntimeError("profile state isolation failed")

    wall = [row["wall_seconds"] for row in matrix]
    engine = [row["engine_seconds"] for row in matrix]
    report = {
        "schema_version": "personalized_product_acceptance_v1",
        "status": "PASS", "champion_commit": service.config["challenger_commit"],
        "matrix_profiles": len(matrix), "dimensions": {"amounts": amounts, "lookbacks": lookbacks,
            "intervals": intervals, "targets": targets, "horizons": [12]},
        "frozen_profile_reproduction": reproduction, "sensitivity": sensitivity,
        "acceptance_14": acceptance_rows, "invalid_cases": invalid_results,
        "deterministic_repeat": deterministic, "sequential_isolation": isolated,
        "concurrent_isolation": concurrent_safe,
        "performance": {"runtime_pack_load_seconds": load_seconds,
            "matrix_wall_median_seconds": statistics.median(wall),
            "matrix_wall_p95_seconds": sorted(wall)[int(.95 * (len(wall) - 1))],
            "matrix_wall_max_seconds": max(wall), "engine_max_seconds": max(engine),
            "cached_repeat_wall_seconds": repeat_wall},
        "matrix": matrix,
        "source_hashes": {path: sha256((ROOT / path).read_bytes()).hexdigest() for path in [
            "src/stock_ranker/personalized_product.py", "src/stock_ranker/webapp.py",
            "src/stock_ranker/web_assets.py", "research/runners/build_personalized_runtime_pack.py",
            "research/runners/run_personalized_product_acceptance.py",
            "research/runners/run_personalized_ui_browser_acceptance.py",
            "research/specifications/personalized_ui_runtime_pack_20260926.json",
        ]},
        "protected_freeze_before": protected,
        "protected_freeze_after": {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest()
                                   for path in sorted(freeze.rglob("*")) if path.is_file()},
    }
    if report["protected_freeze_before"] != report["protected_freeze_after"]:
        raise RuntimeError("frozen evidence changed")
    raw = canonical(report)
    (output / "acceptance.json").write_bytes(json.dumps(report, indent=2, sort_keys=True).encode() + b"\n")
    run_browser(output / "browser_acceptance.json")
    artifacts = [{"path": name, "bytes": (output / name).stat().st_size,
                  "sha256": sha256((output / name).read_bytes()).hexdigest()}
                 for name in ("acceptance.json", "browser_acceptance.json")]
    manifest = {"schema_version": "personalized_product_acceptance_manifest_v1",
                "status": "PASS", "artifacts": artifacts,
                "artifact_set_sha256": sha256(canonical(artifacts)).hexdigest()}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "matrix_profiles", "sensitivity", "performance")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
