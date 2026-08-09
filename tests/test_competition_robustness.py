from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from marketdata.runners.evaluate_walk_forward import run as run_evaluation
from stock_ranker import walk_forward_evaluation as evaluation
from stock_ranker.v2_config import ResearchV2Weights


ROOT = Path(__file__).resolve().parents[1]
BLIND_ROOT = ROOT / "data/walk_forward/blind_predictions_v1_run_01"
EVALUATION_ROOT = ROOT / "data/walk_forward/evaluation_v1_run_01"
EVALUATION_FINGERPRINT = "04e29e8a0f641f900e2ef5ca6d6fe5252b75eff9b23a69fba3b6480f373606c1"


def _manifest(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "blind_prediction_fingerprint": evaluation.BLIND_FINGERPRINT,
        "protocol_sha256": evaluation.PROTOCOL_SHA256,
        "future_outcome_data_present": False,
    }
    value.update(updates)
    return value


def _prices() -> pd.DataFrame:
    return pd.DataFrame({
        "ranking_date": ["2025-08-07"] * 5,
        "ticker": ["AAA"] * 5,
        "provider_symbol": ["AAA.NS"] * 5,
        "date": ["2025-08-07", "2025-11-06", "2025-11-10", "2026-02-06", "2026-08-07"],
        "adj_close": [100.0, 110.0, 999.0, 120.0, 130.0],
    })


def test_outcome_row_order_is_irrelevant_and_each_endpoint_is_independent() -> None:
    ordered = evaluation.calculate_future_returns(_prices())
    shuffled = evaluation.calculate_future_returns(
        _prices().sample(frac=1, random_state=42).reset_index(drop=True)
    )
    assert_frame_equal(ordered, shuffled)
    assert ordered["actual_endpoint_date"].tolist() == [
        "2025-11-06", "2026-02-06", "2026-08-07",
    ]
    assert ordered["future_adjusted_return"].tolist() == pytest.approx([0.1, 0.2, 0.3])


@pytest.mark.parametrize("mutation,error", [
    ("duplicate", "duplicate company-date"),
    ("mixed_provider", "mixed provider identities"),
    ("nan", "invalid adjusted price"),
    ("infinite", "invalid adjusted price"),
])
def test_corrupt_outcome_prices_fail_closed(mutation: str, error: str) -> None:
    prices = _prices()
    if mutation == "duplicate":
        prices = pd.concat([prices, prices.iloc[[0]]], ignore_index=True)
    elif mutation == "mixed_provider":
        prices.loc[1, "provider_symbol"] = "SUCCESSOR.NS"
    elif mutation == "nan":
        prices.loc[1, "adj_close"] = np.nan
    else:
        prices.loc[1, "adj_close"] = np.inf
    with pytest.raises(ValueError, match=error):
        evaluation.calculate_future_returns(prices)


def _frozen() -> pd.DataFrame:
    rows = []
    for sector, tickers in {"Singleton": ["S"], "Pair": ["P1", "P2"], "Triple": ["T1", "T2", "T3"]}.items():
        for rank, ticker in enumerate(tickers, start=1):
            rows.append({
                "ranking_date": "2025-08-07", "ticker": ticker,
                "historical_sector": sector, "research_v2_score": 100 - rank,
                "research_v2_sector_rank": rank,
                "matched_baseline_sector_rank": len(tickers) - rank + 1,
                "original_baseline_sector_rank": rank,
                "eligible_peer_count": len(tickers),
            })
    return pd.DataFrame(rows)


def _returns() -> pd.DataFrame:
    rows = []
    for index, ticker in enumerate(["S", "P1", "P2", "T1", "T2", "T3"]):
        for months in evaluation.HORIZONS:
            rows.append({
                "ranking_date": "2025-08-07", "ticker": ticker,
                "horizon_months": months, "future_adjusted_return": 0.1 - index / 100,
            })
    return pd.DataFrame(rows)


def _evaluate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, returns: pd.DataFrame | None = None):
    (tmp_path / "manifest.json").write_text(json.dumps(_manifest()), encoding="utf-8")
    monkeypatch.setattr(evaluation, "_frozen_groups", lambda _: _frozen())
    return evaluation.evaluate_walk_forward(tmp_path, _returns() if returns is None else returns)


def test_sector_thresholds_exclude_singletons_and_do_not_pool_sectors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _evaluate(tmp_path, monkeypatch)
    assert set(result.sector_rank_ic["historical_sector"]) == {"Triple"}
    assert set(result.pairwise_accuracy["historical_sector"]) == {"Pair", "Triple"}
    assert len(result.sector_rank_ic) == 3
    assert len(result.pairwise_accuracy) == 12


@pytest.mark.parametrize("defect,error", [
    ("duplicate_horizon", "duplicate company-date-horizon"),
    ("missing_horizon", "frozen horizon set"),
    ("nonfinite", "non-finite future return"),
])
def test_corrupt_future_return_panel_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str, error: str,
) -> None:
    returns = _returns()
    if defect == "duplicate_horizon":
        returns = pd.concat([returns, returns.iloc[[0]]], ignore_index=True)
    elif defect == "missing_horizon":
        returns = returns.loc[~returns["horizon_months"].eq(6)]
    else:
        returns.loc[0, "future_adjusted_return"] = np.inf
    with pytest.raises(ValueError, match=error):
        _evaluate(tmp_path, monkeypatch, returns)


@pytest.mark.parametrize("updates,error", [
    ({"protocol_sha256": "0" * 64}, "protocol hash mismatch"),
    ({"future_outcome_data_present": True}, "not outcome-blind"),
])
def test_frozen_bundle_protocol_and_blindness_are_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    updates: dict[str, object], error: str,
) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps(_manifest(**updates)), encoding="utf-8")
    monkeypatch.setattr(evaluation, "_frozen_groups", lambda _: _frozen())
    with pytest.raises(ValueError, match=error):
        evaluation.evaluate_walk_forward(tmp_path, _returns())


def test_tampered_outcome_request_provenance_is_rejected_before_evaluation(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    prices = b"ranking_date,ticker,provider_symbol,date,adj_close\n"
    (cache / "outcome_prices.csv").write_bytes(prices)
    (cache / "request_provenance.json").write_text("{}", encoding="utf-8")
    (cache / "cache_manifest.json").write_text(json.dumps({
        "outcome_prices_sha256": sha256(prices).hexdigest(),
        "request_provenance_sha256": "0" * 64,
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="provenance hash mismatch"):
        run_evaluation(tmp_path / "unused-blind", cache, tmp_path / "unused-output")


def test_frozen_artifact_inventory_cohorts_and_structural_counts() -> None:
    blind_manifest = json.loads((BLIND_ROOT / "manifest.json").read_text(encoding="utf-8"))
    evaluation_manifest = json.loads((EVALUATION_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert blind_manifest["blind_prediction_fingerprint"] == evaluation.BLIND_FINGERPRINT
    assert evaluation_manifest["evaluation_fingerprint"] == EVALUATION_FINGERPRINT
    for artifact in evaluation_manifest["artifacts"]:
        path = EVALUATION_ROOT / artifact["path"]
        assert path.stat().st_size == artifact["size"]
        assert sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
    frozen = evaluation._frozen_groups(BLIND_ROOT)
    assert frozen.groupby("ranking_date")["ticker"].nunique().to_dict() == {
        "2022-08-05": 8, "2023-08-07": 4,
        "2024-08-07": 8, "2025-08-07": 16,
    }
    peers = frozen.groupby(["ranking_date", "historical_sector"])["ticker"].nunique()
    assert int(peers.ge(3).sum()) == 3
    assert int(peers.ge(2).sum()) == 7


def test_frozen_scoring_sources_and_weight_vector_are_guarded() -> None:
    assert sha256((ROOT / "src/stock_ranker/baseline.py").read_bytes()).hexdigest() == (
        "c2833321ea2bb37674680ac6b0cb1603e2825ebb21c8c53e8796bda7dd184cb3"
    )
    assert sha256((ROOT / "src/stock_ranker/research_v2.py").read_bytes()).hexdigest() == (
        "ada9efd47d44d21c425b46f61ab383b39ae41b3ad84525584cf4f732a6e38441"
    )
    assert {name: str(value) for name, value in ResearchV2Weights().as_dict().items()} == {
        "return_1y": "10", "cagr_3y": "10", "cagr_5y": "10",
        "days_since_recorded_high": "5", "annualized_volatility_1y": "12.5",
        "max_drawdown_3y": "12.5", "roce": "15", "debt_to_equity": "10",
        "profit_growth_yoy": "15",
    }
