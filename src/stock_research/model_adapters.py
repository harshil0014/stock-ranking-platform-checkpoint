"""Dependency-free adapters from model implementations to canonical signals."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Mapping

import numpy as np

import pandas as pd

from stock_research.contracts import validate_signals
from stock_research.errors import Diagnostic, ResearchValidationError
from stock_research.platform import ModelDataset, ModelSpecification


class ModelAdapter(ABC):
    """Small boundary implemented by native, subprocess, or precomputed models."""

    specification: ModelSpecification

    @abstractmethod
    def produce_signals(self, dataset: ModelDataset, *, run_id: str) -> pd.DataFrame:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class FunctionalModelAdapter(ModelAdapter):
    specification: ModelSpecification
    score: Callable[[pd.DataFrame], pd.Series]

    def produce_signals(self, dataset: ModelDataset, *, run_id: str) -> pd.DataFrame:
        if dataset.model_id != self.specification.model_id:
            raise ResearchValidationError(Diagnostic("adapter_model_mismatch", "dataset and adapter model IDs differ"))
        values = self.score(dataset.features.copy(deep=True))
        if not isinstance(values, pd.Series) or len(values) != len(dataset.features):
            raise ResearchValidationError(Diagnostic("adapter_output", "score function must return one pandas Series value per row"))
        output = dataset.features[["as_of_date", "ticker", "sector"]].copy()
        output["score"] = values.to_numpy()
        output["model_id"] = self.specification.model_id
        output["run_id"] = run_id
        output = output[["as_of_date", "ticker", "score", "model_id", "run_id", "sector"]]
        return validate_signals(output, {self.specification.model_id})


@dataclass(frozen=True, slots=True)
class PrecomputedSignalAdapter(ModelAdapter):
    specification: ModelSpecification
    signals: pd.DataFrame

    def produce_signals(self, dataset: ModelDataset, *, run_id: str) -> pd.DataFrame:
        signals = self.signals.copy(deep=True)
        signals["run_id"] = run_id
        canonical = validate_signals(signals, {self.specification.model_id})
        expected = set(map(tuple, dataset.features[["as_of_date", "ticker"]].to_numpy()))
        actual = set(map(tuple, canonical[["as_of_date", "ticker"]].to_numpy()))
        if not actual <= expected:
            raise ResearchValidationError(Diagnostic("signal_dataset_mismatch", "signals contain keys outside the validated model dataset"))
        return canonical


@dataclass(frozen=True, slots=True)
class OpenSourceAPMom12mAdapter(ModelAdapter):
    """Mom12m on complete calendar months t-11 through t-1.

    The upstream implementation replaces missing monthly returns with zero.
    This adapter instead emits no signal for an incomplete window so absence is
    never converted into an economic return. On complete input, the formula is
    identical to the upstream OpenSourceAP implementation.
    """

    specification: ModelSpecification

    def produce_signals(self, dataset: ModelDataset, *, run_id: str) -> pd.DataFrame:
        if dataset.model_id != self.specification.model_id:
            raise ResearchValidationError(Diagnostic("adapter_model_mismatch", "dataset and adapter model IDs differ"))
        if "monthly_total_return" not in dataset.features:
            raise ResearchValidationError(Diagnostic("mom12m_feature", "monthly_total_return is required"))
        frame = dataset.features.copy(deep=True)
        frame["period"] = pd.to_datetime(frame["as_of_date"], format="%Y-%m-%d").dt.to_period("M")
        if frame.duplicated(["ticker", "period"]).any():
            raise ResearchValidationError(Diagnostic("mom12m_duplicate_month", "one observation per ticker/calendar month is required"))
        rows = []
        for ticker, group in frame.groupby("ticker", sort=True):
            lookup = {row.period: row for row in group.itertuples(index=False)}
            for current in sorted(lookup):
                required = [current - lag for lag in range(1, 12)]
                if any(period not in lookup for period in required):
                    continue
                values = np.asarray([lookup[period].monthly_total_return for period in required], dtype=float)
                score = float(np.prod(1.0 + values) - 1.0)
                current_row = lookup[current]
                rows.append({
                    "as_of_date": current_row.as_of_date, "ticker": ticker,
                    "score": score, "model_id": self.specification.model_id,
                    "run_id": run_id, "sector": current_row.sector,
                    "method_version": "opensourceap_mom12m_tminus1_to_tminus11_strict_complete_history_v1",
                })
        if not rows:
            raise ResearchValidationError(Diagnostic("mom12m_insufficient_history", "no complete eleven-month lag window"))
        return validate_signals(pd.DataFrame(rows), {self.specification.model_id})


class AdapterCatalog:
    """In-memory adapter registry; registration never imports model runtimes."""

    def __init__(self, adapters: Mapping[str, ModelAdapter] | None = None):
        self._adapters: dict[str, ModelAdapter] = {}
        for model_id, adapter in (adapters or {}).items():
            self.register(model_id, adapter)

    def register(self, model_id: str, adapter: ModelAdapter) -> None:
        if model_id in self._adapters:
            raise ResearchValidationError(Diagnostic("duplicate_model_adapter", f"adapter already registered: {model_id}"))
        if adapter.specification.model_id != model_id:
            raise ResearchValidationError(Diagnostic("adapter_model_mismatch", "catalog key and adapter specification differ"))
        self._adapters[model_id] = adapter

    def produce_signals(self, model_id: str, dataset: ModelDataset, *, run_id: str) -> pd.DataFrame:
        if model_id not in self._adapters:
            raise ResearchValidationError(Diagnostic("missing_model_adapter", f"no adapter registered: {model_id}"))
        return self._adapters[model_id].produce_signals(dataset, run_id=run_id)

    @property
    def model_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))
