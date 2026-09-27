"""Independent Personalized sector audit and descriptive Sir benchmark."""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from stock_ranker.personalized_product import PersonalizedRankingService, parse_profile, resolve_security
from stock_ranker.professor_strategy import extract_ok_strategy_workbook


BASE = {"amount": 7500, "lookback_months": 36, "interval_days": 30,
        "target_cagr_percent": 20, "horizon_months": 12}


def sir_order() -> list[str]:
    """Read the previously recorded external order without guessed aliases."""
    tree = ast.parse((ROOT / "compare_sir_14_current_reference.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "targets" for target in node.targets
        ):
            return [entry[1] for entry in ast.literal_eval(node.value)]
    raise AssertionError("recorded Sir ordering is missing")


def agreement(reference: list[str], candidate: list[str]) -> dict:
    common = set(reference) & set(candidate)
    a = [identity for identity in reference if identity in common]
    b = [identity for identity in candidate if identity in common]
    ar, br = {identity: i for i, identity in enumerate(a)}, {identity: i for i, identity in enumerate(b)}
    pair_count = len(a) * (len(a) - 1) // 2
    agreeing = sum((ar[x] < ar[y]) == (br[x] < br[y])
                   for i, x in enumerate(a) for y in a[i + 1:])
    return {
        "comparable_count": len(a), "pair_count": pair_count,
        "agreeing_pairs": agreeing,
        "pairwise_agreement": agreeing / pair_count if pair_count else None,
        "spearman": float(pd.Series(range(len(a)), index=a).corr(
            pd.Series(range(len(b)), index=b), method="spearman")) if len(a) > 1 else None,
        "top_5_overlap": len(set(a[:5]) & set(b[:5])) / 5 if len(a) > 5 else None,
        "exact_cohort_positions": sum(ar[identity] == br[identity] for identity in a),
    }


def audit_profile(service: PersonalizedRankingService, payload: dict) -> tuple[dict, dict]:
    profile = parse_profile(payload)
    raw, _ = service._calculate(profile)
    product = service.product_loader()
    response = service.rank(payload)
    rows = response["rows"]
    assert len(product) == len(rows) == 4436
    assert product["isin"].is_unique and raw["isin"].is_unique
    by_product = product.set_index("isin")
    by_raw = raw.set_index("isin")
    scored = raw.loc[raw["personalized_score"].notna()].sort_values(
        ["personalized_score", "isin"], ascending=[False, True], kind="stable")
    oracle_overall = {identity: position for position, identity in
                      enumerate(scored["isin"], start=1)}
    by_sector: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for identity, item in by_raw.iterrows():
        if pd.notna(item.get("personalized_score")):
            by_sector[str(by_product.loc[identity, "complete_sector"])].append(
                (oracle_overall[identity], identity))
    oracle = {identity: (position, len(members))
              for members in by_sector.values()
              for position, (_, identity) in enumerate(sorted(members), start=1)}
    sector_totals = Counter(product["complete_sector"])
    errors = []
    overall_ranks = []
    for row in rows:
        identity = row["isin"]
        sector = by_product.loc[identity, "complete_sector"]
        expected = oracle.get(identity)
        if row["sector"] != sector or row["sector_security_count"] != sector_totals[sector]:
            errors.append((identity, "membership_or_total"))
        if row["personalized_sector_peer_count"] != len(by_sector.get(sector, [])):
            errors.append((identity, "peer_count"))
        if row["personalized_sector_rank"] != (expected[0] if expected else None):
            errors.append((identity, "sector_rank"))
        if row["personalized_available"] != (expected is not None):
            errors.append((identity, "availability"))
        if expected:
            raw_row = by_raw.loc[identity]
            overall_ranks.append(row["personalized_rank"])
            if (row["personalized_rank"] != oracle_overall[identity]
                    or int(raw_row["personalized_rank"]) != oracle_overall[identity]
                    or abs(row["personalized_score"] - float(raw_row["personalized_score"])) > 1e-14):
                errors.append((identity, "champion_output"))
        elif row["personalized_rank"] is not None or row["personalized_score"] is not None:
            errors.append((identity, "fallback_leak"))
        if row["baseline_sector_rank"] != int(by_product.loc[identity, "product_baseline_sector_rank"]):
            errors.append((identity, "baseline_rank"))
        if (row["baseline_score"] is None or abs(
            row["baseline_score"] - float(by_product.loc[identity, "product_baseline_score"])
        ) > 1e-14):
            errors.append((identity, "baseline_score"))
    if sorted(overall_ranks) != list(range(1, len(overall_ranks) + 1)):
        errors.append(("ALL", "overall_rank_continuity"))
    assert not errors, errors[:20]
    assert response["sector_count"] == len(sector_totals)
    report = {
        "profile": payload, "profile_fingerprint": profile.fingerprint,
        "product_count": len(product), "sector_count": len(sector_totals),
        "genuine_count": len(oracle), "fallback_count": len(rows) - len(oracle),
        "memberships_checked": len(rows), "sector_positions_checked": len(oracle),
        "fallbacks_checked": len(rows) - len(oracle), "errors": errors,
        "score_tie_groups": int((scored["personalized_score"].value_counts() > 1).sum()),
        "rows_sha256": sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
    }
    return report, response


def run(workbook: Path, output: Path) -> dict:
    service = PersonalizedRankingService()
    product = service.product_loader()
    profiles = [
        BASE, {**BASE, "amount": 1000}, {**BASE, "amount": 50000},
        {**BASE, "lookback_months": 12}, {**BASE, "lookback_months": 60},
        {**BASE, "interval_days": 7}, {**BASE, "interval_days": 90},
        {**BASE, "target_cagr_percent": 10}, {**BASE, "target_cagr_percent": 30},
    ]
    audits = []
    for payload in profiles:
        result, response = audit_profile(service, payload)
        audits.append(result)
        if payload == BASE:
            default = response
    assert default["rows"] == service.rank(BASE)["rows"]
    by_ticker = {row["ticker"]: row for row in default["rows"]}
    codes = sir_order()
    sir_rows = []
    for position, code in enumerate(codes, 1):
        ticker = resolve_security(code, product)
        row = by_ticker[ticker]
        sir_rows.append({
            "sir_rank": position, "sir_code": code,
            **{key: row[key] for key in (
                "ticker", "isin", "sector", "personalized_available",
                "personalized_rank", "personalized_sector_rank",
                "personalized_sector_peer_count", "personalized_score",
                "baseline_sector_rank", "result_type")},
        })
    genuine = [row for row in sir_rows if row["personalized_available"]]
    global_agreement = agreement(
        [row["isin"] for row in genuine],
        [row["isin"] for row in sorted(genuine, key=lambda item: item["personalized_rank"])])
    sector_agreement = {}
    for sector in sorted({row["sector"] for row in genuine}):
        cohort = [row for row in genuine if row["sector"] == sector]
        if len(cohort) >= 2:
            sector_agreement[sector] = agreement(
                [row["isin"] for row in cohort],
                [row["isin"] for row in sorted(cohort, key=lambda item: item["personalized_sector_rank"])])
    sip, cagr, workbook_meta = extract_ok_strategy_workbook(workbook)
    assert set(sip["requested_code"]) == {
        code if ":" in code else "NSE:" + code for code in codes
    }
    workbook_result = {
        "cached_sip_rank_count": int(sip["workbook_sip_rank"].notna().sum()),
        "cached_profit_loss_count": int(sip["workbook_sip_profit_loss"].notna().sum()),
        "workbook_sha256": workbook_meta["workbook_sha256"],
        "workbook_as_of_date": workbook_meta["workbook_as_of_date"],
    }
    normalized_code = {row["sir_code"] if ":" in row["sir_code"] else "NSE:" + row["sir_code"]: row
                       for row in genuine}
    workbook_result["cached_cagr_vs_personalized"] = {}
    for years in (3, 5, 10):
        field = f"workbook_sip_cagr_{years}y"
        comparable = [(normalized_code[item.requested_code], getattr(item, field))
                      for item in sip.itertuples(index=False)
                      if item.requested_code in normalized_code and pd.notna(getattr(item, field))]
        if len(comparable) >= 2:
            workbook_result["cached_cagr_vs_personalized"][field] = agreement(
                [item["isin"] for item, _ in sorted(comparable, key=lambda pair: pair[1], reverse=True)],
                [item["isin"] for item, _ in sorted(comparable, key=lambda pair: pair[0]["personalized_rank"])])
    for years in (1, 3, 5, 10):
        field = f"workbook_cagr_{years}y"
        comparable = [(normalized_code[item.requested_code], getattr(item, field))
                      for item in cagr.itertuples(index=False)
                      if item.requested_code in normalized_code and pd.notna(getattr(item, field))]
        if len(comparable) >= 2:
            workbook_result["cached_cagr_vs_personalized"][field] = agreement(
                [item["isin"] for item, _ in sorted(comparable, key=lambda pair: pair[1], reverse=True)],
                [item["isin"] for item, _ in sorted(comparable, key=lambda pair: pair[0]["personalized_rank"])])
    reproduction = [service.reproduce_frozen_profile(name) for name in service.config["profiles"]]
    assert all(item["passed"] for item in reproduction)
    report = {
        "status": "PASS", "champion_commit": service.config["challenger_commit"],
        "profile_audits": audits, "deterministic_repeat": True,
        "frozen_profile_reproduction": reproduction,
        "classification_sources": product["product_classification_source"].fillna("MISSING").value_counts().to_dict(),
        "classification_confidence": product["complete_sector_confidence"].value_counts().to_dict(),
        "sir": {
            "recorded_order_source": "compare_sir_14_current_reference.py targets",
            "cohort": sir_rows, "global_order_on_genuine_overlap": global_agreement,
            "within_sector_on_genuine_overlap": sector_agreement,
            "workbook": workbook_result,
            "boundary": "Descriptive order comparison only. The copied workbook has no cached SIP ranks; its 2026-08-21 evidence and the 2026-09-18 product snapshot have different dates. Fallbacks are excluded from Personalized agreement.",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.workbook, args.output)
    print(json.dumps({"status": result["status"], "profiles": len(result["profile_audits"]),
                      "sir": result["sir"]["global_order_on_genuine_overlap"]}, indent=2))
