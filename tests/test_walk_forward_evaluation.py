from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest

from marketdata.runners import acquire_walk_forward_outcomes as acquisition
from stock_ranker import walk_forward_evaluation as evaluation
from stock_ranker.walk_forward_blind import protocol_fingerprint


ROOT = Path(__file__).resolve().parents[1]
BLIND_ROOT = ROOT / "data/walk_forward/blind_predictions_v1_run_01"


def test_frozen_research_identifiers_are_unchanged() -> None:
    assert evaluation.PROTOCOL_SHA256 == "a81278b799e1a61c3684f3b319fb14e2f6f0db6a2bdad1cd79b2ce13fd6f8576"
    assert evaluation.AMENDMENT_SHA256 == "7f8c5d40de88077f3b6afcd471d0db4377fab567d2839e719a71ee6b11ae7163"
    assert evaluation.BLIND_FINGERPRINT == "c438c31967e1f2685bbe77d85db6ca44617e024c699dba3749ee3523af6e401d"
    manifest = json.loads((BLIND_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["blind_prediction_fingerprint"] == evaluation.BLIND_FINGERPRINT


@pytest.mark.parametrize("months,target", [(3, "2023-11-07"), (6, "2024-02-07"), (12, "2024-08-07")])
def test_calendar_targets(months: int, target: str) -> None:
    assert evaluation.calendar_target("2023-08-07", months) == target


def test_endpoint_is_last_observation_on_or_before_target() -> None:
    prices = pd.DataFrame({"date": ["2024-02-06", "2024-02-07", "2024-02-08"], "adj_close": [1, 2, 3]})
    row = evaluation.select_price_on_or_before(prices, "2024-02-07")
    assert row["date"] == pd.Timestamp("2024-02-07")
    assert row["adj_close"] == 2


def test_adjusted_return_formula_and_endpoint_dates() -> None:
    prices = pd.DataFrame({
        "ranking_date": ["2023-08-07"] * 4,
        "ticker": ["AAA"] * 4,
        "provider_symbol": ["AAA.NS"] * 4,
        "date": ["2023-08-07", "2023-11-07", "2024-02-06", "2024-08-07"],
        "adj_close": [100.0, 110.0, 120.0, 130.0],
    })
    result = evaluation.calculate_future_returns(prices)
    assert result["actual_endpoint_date"].tolist() == ["2023-11-07", "2024-02-06", "2024-08-07"]
    assert result["future_adjusted_return"].tolist() == pytest.approx([0.1, 0.2, 0.3])
    assert set(result["label_semantics"]) == {"ADJUSTED-PRICE FUTURE RETURN"}


def test_missing_ranking_observation_is_not_substituted() -> None:
    prices = pd.DataFrame({
        "ranking_date": ["2023-08-07"] * 2, "ticker": ["AAA"] * 2,
        "provider_symbol": ["AAA.NS"] * 2,
        "date": ["2023-08-04", "2024-08-07"], "adj_close": [100.0, 120.0],
    })
    with pytest.raises(ValueError, match="ranking-date observation absent"):
        evaluation.calculate_future_returns(prices)


def test_acquisition_uses_exact_frozen_provider_and_bounded_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blind = tmp_path / "blind"
    date_dir = blind / "2025-08-07"
    date_dir.mkdir(parents=True)
    (blind / "manifest.json").write_text(json.dumps({"blind_prediction_fingerprint": evaluation.BLIND_FINGERPRINT}))
    pd.DataFrame({"ticker": ["AAA"]}).to_csv(date_dir / "research_v2.csv", index=False)
    pd.DataFrame({
        "historical_symbol": ["AAA"], "provider_symbol": ["ORIGINAL.NS"],
        "identity_resolution_status": ["RESOLVED"],
    }).to_csv(date_dir / "identity_resolution.csv", index=False)
    monkeypatch.setattr(acquisition, "RANKING_DATES", ("2025-08-07",))
    calls: list[tuple[str, str, str]] = []

    def loader(provider: str, start: str, end: str) -> pd.DataFrame:
        calls.append((provider, start, end))
        index = pd.to_datetime(["2025-08-07", "2026-08-07"])
        return pd.DataFrame({"Close": [100.0, 110.0], "Adj Close": [100.0, 110.0]}, index=index)

    output = tmp_path / "cache"
    result = acquisition.acquire(blind, output, loader)
    assert calls == [("ORIGINAL.NS", "2025-08-07", "2026-08-08")]
    assert result["company_date_count"] == 1
    provenance = json.loads((output / "request_provenance.json").read_text())
    assert provenance["requests"][0]["provider_symbol"] == "ORIGINAL.NS"
    assert provenance["requests"][0]["auto_adjust"] is False
    assert provenance["requests"][0]["repair"] is True


def test_average_rank_spearman_and_pairwise_tie_policy() -> None:
    assert evaluation._spearman(pd.Series([3.0, 2.0, 1.0]), pd.Series([30.0, 20.0, 10.0])) == pytest.approx(1.0)
    group = pd.DataFrame({
        "ticker": ["A", "B", "C"], "rank": [1, 1, 3],
        "future_adjusted_return": [0.3, 0.2, 0.2],
    })
    credit, pairs, model_ties, outcome_ties = evaluation._pairwise(group, "rank")
    assert (credit, pairs, model_ties, outcome_ties) == (1.5, 2, 1, 1)


def _frozen_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "ranking_date": ["2025-08-07"] * 3,
        "ticker": ["A", "B", "C"], "historical_sector": ["Sector"] * 3,
        "research_v2_score": [30.0, 20.0, 10.0],
        "research_v2_sector_rank": [1, 2, 3],
        "matched_baseline_sector_rank": [3, 2, 1],
        "original_baseline_sector_rank": [3, 2, 1], "eligible_peer_count": [3] * 3,
    })


def _returns() -> pd.DataFrame:
    rows = []
    values = {"A": 0.3, "B": 0.2, "C": 0.1}
    for ticker, value in values.items():
        for months in evaluation.HORIZONS:
            rows.append({"ranking_date": "2025-08-07", "ticker": ticker,
                         "horizon_months": months, "future_adjusted_return": value})
    return pd.DataFrame(rows)


def test_sector_evaluation_primary_delta_top_and_odd_groups(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps({"blind_prediction_fingerprint": evaluation.BLIND_FINGERPRINT}))
    monkeypatch.setattr(evaluation, "_frozen_groups", lambda _: _frozen_frame())
    result = evaluation.evaluate_walk_forward(tmp_path, _returns())
    primary = result.sector_rank_ic.query("horizon_months == 12").iloc[0]
    assert primary["research_v2_rank_ic"] == pytest.approx(1.0)
    assert primary["matched_baseline_rank_ic"] == pytest.approx(-1.0)
    assert primary["delta_rank_ic"] == pytest.approx(2.0)
    assert result.summary["horizons"]["12"]["rank_ic_observation_count"] == 1
    v2_top = result.top_stock_excess_return.query("horizon_months == 12 and model == 'RESEARCH_V2'").iloc[0]
    assert v2_top["top_stock_excess_return"] == pytest.approx(0.1)
    spread = result.top_bottom_spread.query("horizon_months == 12 and model == 'RESEARCH_V2'").iloc[0]
    assert spread["middle_omitted"] == "B"
    assert spread["top_bottom_spread"] == pytest.approx(0.2)


def test_cohort_mismatch_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps({"blind_prediction_fingerprint": evaluation.BLIND_FINGERPRINT}))
    monkeypatch.setattr(evaluation, "_frozen_groups", lambda _: _frozen_frame())
    with pytest.raises(ValueError, match="cohort does not match"):
        evaluation.evaluate_walk_forward(tmp_path, _returns().query("ticker != 'C'"))


def test_export_is_byte_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blind = tmp_path / "blind"
    blind.mkdir()
    (blind / "manifest.json").write_text(json.dumps({"blind_prediction_fingerprint": evaluation.BLIND_FINGERPRINT}))
    monkeypatch.setattr(evaluation, "_frozen_groups", lambda _: _frozen_frame())
    result = evaluation.evaluate_walk_forward(blind, _returns())
    prices = pd.DataFrame({"date": ["2025-08-07"], "adj_close": [1.0]})
    first, second = tmp_path / "first", tmp_path / "second"
    fingerprint_1 = evaluation.export_evaluation(result, prices, {"source": "test"}, first)
    fingerprint_2 = evaluation.export_evaluation(result, prices, {"source": "test"}, second)
    assert fingerprint_1 == fingerprint_2
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {
        p.name: p.read_bytes() for p in second.iterdir()
    }


def test_protocol_files_remain_byte_frozen() -> None:
    assert protocol_fingerprint(
        ROOT / "experiments/walk_forward/protocol_v1.json"
    ) == evaluation.PROTOCOL_SHA256
    amendment = json.loads((ROOT / "experiments/walk_forward/protocol_amendment_001.json").read_text())
    canonical = json.dumps(amendment, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert sha256(canonical).hexdigest() == evaluation.AMENDMENT_SHA256
