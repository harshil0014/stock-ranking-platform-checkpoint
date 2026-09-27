"""Sector projection tests use independently specified final champion ranks."""
from __future__ import annotations

from collections import OrderedDict
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock

import pandas as pd
import pytest

from stock_ranker.personalized_product import (
    CHAMPION_COMMIT, PACK_AUDIT, PersonalizationError, PersonalizedRankingService,
    load_runtime_book,
)


CANONICAL_PACK_SHA256 = "515eac8ffc555a571406a4a41f9d931a016cb6280871a3d89f59846d2692ed0c"


def test_runtime_contract_rejects_alternate_pack_even_if_listed_compatible(tmp_path: Path) -> None:
    audit = json.loads(PACK_AUDIT.read_text(encoding="utf-8"))
    assert audit["challenger_commit"] == CHAMPION_COMMIT
    assert audit["pack_sha256"] == CANONICAL_PACK_SHA256
    assert audit["pack_bytes"] == 98_546_546
    assert "compatible_pack_sha256" not in audit
    alternate = tmp_path / "alternate.npz"
    alternate.write_bytes(b"alternate runtime evidence")
    audit["compatible_pack_sha256"] = [sha256(alternate.read_bytes()).hexdigest()]
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    with pytest.raises(PersonalizationError, match="integrity validation"):
        load_runtime_book(alternate, audit_path)


PROFILE = {"amount": 7500, "lookback_months": 36, "interval_days": 30,
           "target_cagr_percent": 20, "horizon_months": 12}


def _service(product: pd.DataFrame) -> PersonalizedRankingService:
    service = PersonalizedRankingService.__new__(PersonalizedRankingService)
    service.config = {"profiles": {}, "prediction_as_of": "2026-09-18"}
    service.product_loader = lambda: product
    service.cache_size = 12
    service.cache = OrderedDict()
    service.lock = RLock()
    service._calculate = lambda profile: (pd.DataFrame([
        {"isin": "I1", "status": "AVAILABLE", "personalized_score": .8, "personalized_rank": 1},
        {"isin": "I3", "status": "AVAILABLE", "personalized_score": .7, "personalized_rank": 2},
        {"isin": "I2", "status": "AVAILABLE", "personalized_score": .6, "personalized_rank": 3},
    ]), 0.0)
    return service


def _product() -> pd.DataFrame:
    return pd.DataFrame([
        {"isin": "I1", "ticker": "ONE", "company": "One", "product_sector": "A", "product_baseline_sector_rank": 3},
        {"isin": "I2", "ticker": "TWO", "company": "Two", "product_sector": "A", "product_baseline_sector_rank": 2},
        {"isin": "I3", "ticker": "THREE", "company": "Three", "product_sector": "B", "product_baseline_sector_rank": 1},
        {"isin": "I4", "ticker": "FOUR", "company": "Four", "product_sector": "A", "product_baseline_sector_rank": 1,
         "product_baseline_score": .91},
    ])


def test_sector_rank_projects_global_order_and_excludes_fallbacks() -> None:
    result = _service(_product()).rank(PROFILE)
    rows = {row["ticker"]: row for row in result["rows"]}
    assert (result["row_count"], result["personalized_count"], result["fallback_count"], result["sector_count"]) == (4, 3, 1, 2)
    assert [(rows[t]["personalized_rank"], rows[t]["personalized_sector_rank"]) for t in ("ONE", "THREE", "TWO")] == [(1, 1), (2, 1), (3, 2)]
    assert (rows["ONE"]["personalized_sector_peer_count"], rows["ONE"]["sector_security_count"]) == (2, 3)
    assert rows["FOUR"]["personalized_sector_rank"] is None
    assert rows["FOUR"]["personalized_sector_peer_count"] == 2
    assert rows["FOUR"]["personalized_score"] is None
    assert rows["FOUR"]["baseline_sector_rank"] == 1
    assert rows["FOUR"]["baseline_score"] == .91
    assert rows["ONE"]["baseline_sector_rank"] == 3
    assert result["rows"] == _service(_product()).rank(PROFILE)["rows"]


def test_score_tie_keeps_existing_overall_tiebreak_within_sector() -> None:
    service = _service(_product())
    service._calculate = lambda profile: (pd.DataFrame([
        {"isin": "I1", "status": "AVAILABLE", "personalized_score": .8, "personalized_rank": 1},
        {"isin": "I2", "status": "AVAILABLE", "personalized_score": .8, "personalized_rank": 2},
        {"isin": "I3", "status": "AVAILABLE", "personalized_score": .7, "personalized_rank": 3},
    ]), 0.0)
    rows = {row["ticker"]: row for row in service.rank(PROFILE)["rows"]}
    assert (rows["ONE"]["personalized_sector_rank"], rows["TWO"]["personalized_sector_rank"]) == (1, 2)
    assert rows["ONE"]["personalized_score"] == rows["TWO"]["personalized_score"]


def test_in_cohort_missing_score_is_an_explicit_fallback() -> None:
    service = _service(_product())
    service._calculate = lambda profile: (pd.DataFrame([
        {"isin": "I1", "status": "AVAILABLE", "personalized_score": .8, "personalized_rank": 1},
        {"isin": "I2", "status": "AVAILABLE", "personalized_score": float("nan"), "personalized_rank": None},
        {"isin": "I3", "status": "AVAILABLE", "personalized_score": .7, "personalized_rank": 2},
    ]), 0.0)
    rows = {row["ticker"]: row for row in service.rank(PROFILE)["rows"]}
    assert rows["TWO"]["status"] == "PERSONALIZED_SCORE_UNAVAILABLE"
    assert rows["TWO"]["execution_status"] == "AVAILABLE"
    assert rows["TWO"]["personalized_sector_rank"] is None
    assert rows["TWO"]["personalized_score"] is None
    assert rows["TWO"]["personalized_sector_peer_count"] == 1


def test_duplicate_champion_overall_rank_fails_closed() -> None:
    service = _service(_product())
    service._calculate = lambda profile: (pd.DataFrame([
        {"isin": "I1", "personalized_score": .8, "personalized_rank": 1},
        {"isin": "I2", "personalized_score": .7, "personalized_rank": 1},
    ]), 0.0)
    with pytest.raises(PersonalizationError, match="overall ranks"):
        service.rank(PROFILE)


@pytest.mark.parametrize("mutation", [
    lambda frame: frame.assign(product_sector=["A", "", "B", "A"]),
    lambda frame: frame.assign(isin=["I1", "I1", "I3", "I4"]),
    lambda frame: frame.assign(ticker=["ONE", "ONE", "THREE", "FOUR"]),
])
def test_ambiguous_classification_or_identity_fails_closed(mutation) -> None:
    with pytest.raises(PersonalizationError, match="incomplete or ambiguous"):
        _service(mutation(_product())).rank(PROFILE)
