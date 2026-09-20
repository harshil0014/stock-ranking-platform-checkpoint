"""Outcome-blind signal agreement and descriptive rank consensus."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Mapping

import pandas as pd

from stock_research.contracts import validate_signals
from stock_research.errors import Diagnostic, ResearchValidationError


@dataclass(frozen=True, slots=True)
class ConsensusResult:
    report: dict
    pairwise_agreement: pd.DataFrame
    consensus_signals: pd.DataFrame


def verify_consensus(
    signals_by_model: Mapping[str, pd.DataFrame], *,
    model_configuration_fingerprints: Mapping[str, str],
    evaluation_protocol_fingerprint: str,
    run_id: str = "descriptive-consensus",
) -> ConsensusResult:
    """Require one common cohort, then calculate label-free rank agreement."""

    if len(signals_by_model) < 2:
        raise ResearchValidationError(Diagnostic("consensus_model_count", "at least two models are required"))
    if set(signals_by_model) != set(model_configuration_fingerprints):
        raise ResearchValidationError(Diagnostic("consensus_fingerprints", "every model needs one configuration fingerprint"))
    canonical = {name: validate_signals(frame, {name}) for name, frame in signals_by_model.items()}
    keys = {
        name: tuple(map(tuple, frame[["as_of_date", "ticker"]].to_numpy()))
        for name, frame in canonical.items()
    }
    reference = next(iter(keys.values()))
    if any(value != reference for value in keys.values()):
        raise ResearchValidationError(Diagnostic("consensus_cohort_mismatch", "models must have identical ordered date/ticker keys"))
    wide = None
    for name in sorted(canonical):
        part = canonical[name][["as_of_date", "ticker", "score"]].rename(columns={"score": name})
        wide = part if wide is None else wide.merge(part, on=["as_of_date", "ticker"], validate="one_to_one")
    assert wide is not None
    normalized = wide[["as_of_date", "ticker"]].copy()
    for name in sorted(canonical):
        normalized[name] = wide.groupby("as_of_date")[name].rank(method="average", pct=True)
    pairs = []
    for first, second in combinations(sorted(canonical), 2):
        for date, group in normalized.groupby("as_of_date", sort=True):
            value = group[first].corr(group[second], method="pearson") if len(group) >= 2 else None
            pairs.append({"as_of_date": date, "model_a": first, "model_b": second,
                          "rank_correlation": value, "observations": len(group)})
    consensus = normalized[["as_of_date", "ticker"]].copy()
    consensus["score"] = normalized[sorted(canonical)].mean(axis=1)
    consensus["model_id"] = "verified_rank_consensus"
    consensus["run_id"] = run_id
    consensus = validate_signals(consensus)
    report = {
        "schema_version": "model_consensus_verification_v1",
        "status": "verified", "purpose": "descriptive_outcome_blind_rank_agreement",
        "model_ids": sorted(canonical),
        "model_configuration_fingerprints": dict(sorted(model_configuration_fingerprints.items())),
        "evaluation_protocol_fingerprint": evaluation_protocol_fingerprint,
        "common_observations": len(reference),
        "date_count": len({key[0] for key in reference}),
        "winner_selected": False, "labels_accessed": False,
    }
    return ConsensusResult(report, pd.DataFrame(pairs), consensus)
