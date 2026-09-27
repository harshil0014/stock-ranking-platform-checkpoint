"""Website adapter for the immutable d499580 personalized challenger.

The adapter validates user inputs, runs the existing whole-share and corporate-
action engine, scores its seven frozen features with the sealed LightGBM model,
and applies the registered 67/33 percentile blend.  It contains no alternative
ranking rule and performs no fitting.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
from threading import RLock
from time import perf_counter
from typing import Any, Callable

import numpy as np
import pandas as pd

from stock_ranker.personalized import InvestorProfile
from stock_ranker.runtime import PROJECT_ROOT
from stock_research.personalized_executable_tournament import FEATURES
from stock_research.personalized_official_actions import OfficialActionHistoryBook
from stock_research.personalized_shadow import verify as verify_freeze


CHAMPION_COMMIT = "d4995807163bef1ec4b297179e6c54a59c71f390"
FREEZE_ROOT = PROJECT_ROOT / "research/freezes/personalized-d499580"
DEFAULT_PACK = PROJECT_ROOT / "research/runtime/personalized-ui-d499580.npz"
PACK_AUDIT = PROJECT_ROOT / "research/specifications/personalized_ui_runtime_pack_20260926.json"
SAFE_SECURITY = re.compile(r"^[A-Z0-9&.:-]{1,40}$")
REFERENCE_PROFILE = {12: "lookback12", 36: "base7500", 60: "lookback60"}
DOMAINS = {
    "amount": {"minimum": 1000.0, "maximum": 50000.0, "decimals": True, "unit": "INR"},
    "lookback_months": {"choices": [12, 36, 60], "unit": "months"},
    "interval_days": {"minimum": 7, "maximum": 90, "integer": True, "unit": "days"},
    "target_cagr_percent": {"minimum": 10.0, "maximum": 30.0, "decimals": True, "unit": "percent"},
    "horizon_months": {"choices": [12], "unit": "months"},
}


class PersonalizationError(ValueError):
    """A safe, user-facing personalization error."""


def _sha(path: str | Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def _number(payload: dict, key: str) -> float:
    value = payload.get(key)
    if value is None or value == "" or isinstance(value, bool):
        raise PersonalizationError(f"{key} is required")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PersonalizationError(f"{key} must be numeric") from exc
    if not math.isfinite(result):
        raise PersonalizationError(f"{key} must be finite")
    return result


def parse_profile(payload: dict[str, Any]) -> InvestorProfile:
    """Validate the public input contract without clamping or substitution."""
    if not isinstance(payload, dict):
        raise PersonalizationError("profile must be a JSON object")
    amount = _number(payload, "amount")
    interval_raw = _number(payload, "interval_days")
    lookback_raw = _number(payload, "lookback_months")
    target_percent = _number(payload, "target_cagr_percent")
    horizon_raw = _number(payload, "horizon_months")
    for key, value in (("interval_days", interval_raw), ("lookback_months", lookback_raw),
                       ("horizon_months", horizon_raw)):
        if not value.is_integer():
            raise PersonalizationError(f"{key} must be a whole number")
    interval, lookback, horizon = int(interval_raw), int(lookback_raw), int(horizon_raw)
    if not DOMAINS["amount"]["minimum"] <= amount <= DOMAINS["amount"]["maximum"]:
        raise PersonalizationError("amount must be between ₹1,000 and ₹50,000")
    if lookback not in DOMAINS["lookback_months"]["choices"]:
        raise PersonalizationError("lookback_months must be 12, 36, or 60")
    if not DOMAINS["interval_days"]["minimum"] <= interval <= DOMAINS["interval_days"]["maximum"]:
        raise PersonalizationError("interval_days must be a whole number from 7 through 90")
    if not DOMAINS["target_cagr_percent"]["minimum"] <= target_percent <= DOMAINS["target_cagr_percent"]["maximum"]:
        raise PersonalizationError("target_cagr_percent must be between 10 and 30")
    if horizon not in DOMAINS["horizon_months"]["choices"]:
        raise PersonalizationError("the frozen champion supports only a 12-month horizon")
    return InvestorProfile(amount=amount, interval_days=interval, lookback_months=lookback,
                           horizon_months=horizon, target_cagr=target_percent / 100,
                           whole_shares=True)


def _json_value(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def load_runtime_book(pack_path: str | Path, audit_path: str | Path = PACK_AUDIT) -> OfficialActionHistoryBook:
    """Load the safe NumPy pack produced from the accepted immutable histories."""
    pack, audit_path = Path(pack_path), Path(audit_path)
    if not pack.is_file():
        raise FileNotFoundError(
            "Personalized runtime evidence is not prepared. Run build_personalized_runtime_pack.py."
        )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("challenger_commit") != CHAMPION_COMMIT or _sha(pack) != audit.get("pack_sha256"):
        raise PersonalizationError("personalized runtime pack failed integrity validation")
    data = np.load(pack, allow_pickle=False)
    identities = data["identities"].astype(str)
    offsets = data["offsets"].astype(np.int64)
    dates = data["dates"].astype("datetime64[D]")
    raw, adjusted, nominal, factor = (data[name].astype(float) for name in
                                       ("raw", "adjusted", "nominal", "factor"))
    book = OfficialActionHistoryBook.__new__(OfficialActionHistoryBook)
    book.arrays = {}
    for position, identity in enumerate(identities):
        start, stop = int(offsets[position]), int(offsets[position + 1])
        values = tuple(array[start:stop] for array in (dates, raw, adjusted, nominal, factor))
        for array in values:
            array.setflags(write=False)
        book.arrays[identity] = values
    book.errors = json.loads(bytes(data["errors_json"].tolist()).decode("utf-8"))
    book.cache, book._window_cache = {}, {}
    ledger = pd.read_csv(PROJECT_ROOT / audit["official_action_ledger"], low_memory=False)
    ledger["event_date"] = pd.to_datetime(ledger.event_date, errors="raise").dt.normalize()
    book.actions = {identity: frame for identity, frame in ledger.groupby("isin")}
    terms = pd.read_csv(PROJECT_ROOT / audit["resulting_terms"])
    book.resulting_terms = terms
    return book


def _product_metadata() -> pd.DataFrame:
    from stock_ranker.live_website import _company_facts, _product_view
    product = _product_view().copy()
    facts = _company_facts().facts
    optional = [column for column in ("screener_nse_code", "screener_bse_code") if column in facts]
    if optional:
        product = product.merge(facts[["isin", *optional]], on="isin", how="left", validate="one_to_one")
    return product


def _code(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip().upper()
    return text[:-2] if text.endswith(".0") and text[:-2].isdigit() else text


def resolve_security(requested: str, product: pd.DataFrame) -> str:
    """Resolve an exact NSE/BSE identifier to a canonical product ticker."""
    value = str(requested).strip().upper()
    if not value or not SAFE_SECURITY.fullmatch(value):
        raise PersonalizationError("security identifier is invalid")
    ticker = product.ticker.astype(str).str.upper()
    direct = product.loc[ticker.eq(value)]
    if len(direct) == 1:
        return str(direct.iloc[0].ticker)
    prefix, code = (value.split(":", 1) if ":" in value else ("", value))
    if prefix == "NSE":
        direct = product.loc[ticker.eq(code)]
        if len(direct) == 1:
            return str(direct.iloc[0].ticker)
        if "screener_nse_code" in product:
            direct = product.loc[product.screener_nse_code.map(_code).eq(code)]
    elif prefix in {"BOM", "BSE"} or code.isdigit():
        if not code.isdigit():
            raise PersonalizationError("BSE security code must be numeric")
        primary = product.get("exchange_security_id", pd.Series("", index=product.index)).map(_code)
        bse = product.get("screener_bse_code", pd.Series("", index=product.index)).map(_code)
        direct = product.loc[(product.primary_exchange.astype(str).str.upper().eq("BSE") & primary.eq(code)) | bse.eq(code)]
    else:
        direct = product.iloc[0:0]
    choices = sorted(set(direct.ticker.astype(str)))
    if len(choices) != 1:
        raise PersonalizationError("security is not uniquely present in the accepted product universe")
    return choices[0]


class PersonalizedRankingService:
    """Thread-safe, stateless-by-request product facade over the frozen model."""

    def __init__(self, *, freeze_root: str | Path = FREEZE_ROOT,
                 pack_path: str | Path | None = None,
                 audit_path: str | Path = PACK_AUDIT,
                 product_loader: Callable[[], pd.DataFrame] = _product_metadata,
                 book: OfficialActionHistoryBook | None = None,
                 model: Any | None = None, cache_size: int = 12):
        self.freeze_root = Path(freeze_root)
        verify_freeze(self.freeze_root)
        self.config = json.loads((self.freeze_root / "config.json").read_text(encoding="utf-8"))
        if self.config.get("challenger_commit") != CHAMPION_COMMIT or self.config.get("weights") != [.67, .33]:
            raise PersonalizationError("frozen champion identity changed")
        self.features = pd.read_csv(self.freeze_root / "features.csv.gz", low_memory=False)
        self.frozen_rankings = pd.read_csv(self.freeze_root / "rankings.csv.gz", low_memory=False)
        self.book = book or load_runtime_book(
            pack_path or os.environ.get("STOCK_RANKER_PERSONALIZED_RUNTIME_PACK", DEFAULT_PACK), audit_path
        )
        if model is None:
            from lightgbm import Booster
            model = Booster(model_file=str(self.freeze_root / "lambdarank.txt"))
        self.model = model
        self.product_loader = product_loader
        self.cache_size = cache_size
        self.cache: OrderedDict[str, dict] = OrderedDict()
        self.lock = RLock()

    def metadata(self) -> dict[str, Any]:
        return {
            "available": True, "status": "FROZEN PERSONALIZED CHAMPION",
            "champion_commit": CHAMPION_COMMIT, "blend": {"goal": .67, "lightgbm_lambdarank": .33},
            "as_of_date": self.config["prediction_as_of"], "domains": DOMAINS,
            "defaults": {"amount": 7500, "lookback_months": 36, "interval_days": 30,
                         "target_cagr_percent": 20, "horizon_months": 12},
            "scientific_boundary": (
                "Inputs are limited to the domain represented in the frozen research. "
                "Lookback cohorts are 12, 36 and 60 months; the frozen champion supports a 12-month horizon."
            ),
        }

    def _cohort(self, lookback: int) -> tuple[pd.DataFrame, pd.DataFrame]:
        name = REFERENCE_PROFILE[lookback]
        features = self.features.loc[self.features.profile_name.eq(name)].copy()
        frozen = self.frozen_rankings.loc[self.frozen_rankings.profile_name.eq(name)].copy()
        if features["isin"].duplicated().any() or frozen["isin"].duplicated().any():
            raise PersonalizationError("frozen cohort contains duplicate identities")
        return features, frozen

    def _frozen_profile_name(self, profile: InvestorProfile) -> str | None:
        for name, raw in self.config["profiles"].items():
            if (float(raw["amount"]) == profile.amount
                    and int(raw["interval_days"]) == profile.interval_days
                    and int(raw["lookback_months"]) == profile.lookback_months
                    and int(raw["horizon_months"]) == profile.horizon_months
                    and float(raw["target_cagr"]) == profile.target_cagr):
                return name
        return None

    def _calculate(self, profile: InvestorProfile, *, use_stored_frozen_profile: bool = True) -> tuple[pd.DataFrame, float]:
        started = perf_counter()
        frozen_name = self._frozen_profile_name(profile) if use_stored_frozen_profile else None
        if frozen_name is not None:
            current = self.frozen_rankings.loc[self.frozen_rankings.profile_name.eq(frozen_name)].copy()
            components = current[["enhanced_goal_score", "lightgbm_lambdarank_score"]].rank(pct=True)
            current["goal_percentile"] = components.iloc[:, 0]
            current["lambdarank_percentile"] = components.iloc[:, 1]
            current["personalized_score"] = current["selected_ensemble_score"]
            ranked = current.loc[current.personalized_score.notna()].sort_values(
                ["personalized_score", "isin"], ascending=[False, True], kind="stable"
            )
            current["personalized_rank"] = pd.Series(
                np.arange(1, len(ranked) + 1, dtype=int), index=ranked.index, dtype="Int64"
            )
            return current, perf_counter() - started
        cohort, _ = self._cohort(profile.lookback_months)
        allowed = set(cohort["isin"])
        current = self.book.simulate(profile, self.config["prediction_as_of"],
                                     mode="enhanced_carry", include_journal=False)
        current = current.loc[current["isin"].isin(allowed)].copy()
        if set(current["isin"]) != allowed:
            raise PersonalizationError("runtime evidence does not cover the frozen lookback cohort")
        if profile.horizon_months > profile.lookback_months:
            scenarios: list[pd.Series] = []
        else:
            offsets = sorted(set(np.linspace(0, profile.lookback_months - profile.horizon_months, 4).astype(int)))
            scenarios = [self.book.simulate(
                profile, pd.Timestamp(self.config["prediction_as_of"]) - pd.DateOffset(months=int(offset)),
                months=profile.horizon_months, mode="enhanced_carry", include_journal=False,
            ).set_index("isin")["target_shortfall"].rename(int(offset)).reindex(current["isin"])
                         for offset in offsets]
        shortfalls = pd.concat(scenarios, axis=1) if scenarios else pd.DataFrame(index=current["isin"])
        current["goal_windows"] = shortfalls.notna().sum(axis=1).to_numpy()
        current["enhanced_goal_score"] = (
            -shortfalls.pow(2).mean(axis=1).where(shortfalls.notna().all(axis=1)).to_numpy()
            if len(shortfalls.columns) else np.nan
        )
        current["enhanced_carry_xirr_score"] = current["xirr"]
        valid = current["enhanced_carry_xirr_score"].notna()
        current["lightgbm_lambdarank_score"] = np.nan
        current.loc[valid, "lightgbm_lambdarank_score"] = self.model.predict(current.loc[valid, FEATURES])
        components = current[["enhanced_goal_score", "lightgbm_lambdarank_score"]].rank(pct=True)
        current["goal_percentile"] = components.iloc[:, 0]
        current["lambdarank_percentile"] = components.iloc[:, 1]
        current["personalized_score"] = components.iloc[:, 0] * .67 + components.iloc[:, 1] * .33
        ranked = current.loc[current.personalized_score.notna()].sort_values(
            ["personalized_score", "isin"], ascending=[False, True], kind="stable"
        )
        current["personalized_rank"] = pd.Series(
            np.arange(1, len(ranked) + 1, dtype=int), index=ranked.index, dtype="Int64"
        )
        return current, perf_counter() - started

    def rank(self, payload: dict[str, Any], *, securities: list[str] | None = None) -> dict[str, Any]:
        profile = parse_profile(payload)
        key = profile.fingerprint
        security_scope = tuple(str(value).strip().upper() for value in (securities or []))
        cache_key = key + ":" + sha256(json.dumps(security_scope).encode()).hexdigest()
        with self.lock:
            if cache_key in self.cache:
                self.cache.move_to_end(cache_key)
                cached = json.loads(json.dumps(self.cache[cache_key]))
                cached["cache_hit"] = True
                return cached
            calculated, seconds = self._calculate(profile)
            product = self.product_loader().copy()
            facts = product.drop_duplicates("isin").set_index("isin")
            requested: dict[str, str] = {}
            for raw in securities or []:
                canonical = resolve_security(raw, product)
                isin_rows = product.loc[product.ticker.eq(canonical), "isin"]
                requested[str(isin_rows.iloc[0])] = str(raw)
            rows = []
            by_isin = calculated.set_index("isin")
            identities = list(calculated["isin"])
            identity_set = set(identities)
            # Preserve the complete accepted product universe after the frozen
            # personalized cohort.  These rows are explicitly labelled as
            # fallbacks and never receive an invented personalized score.
            for identity in product["isin"].dropna().astype(str):
                if identity not in identity_set:
                    identities.append(identity)
                    identity_set.add(identity)
            for identity in requested:
                if identity not in identity_set:
                    identities.append(identity)
                    identity_set.add(identity)
            for identity in identities:
                execution = by_isin.loc[identity] if identity in by_isin.index else None
                product_row = facts.loc[identity] if identity in facts.index else pd.Series(dtype=object)
                score = None if execution is None else _json_value(execution.get("personalized_score"))
                status = "OUTSIDE_FROZEN_LOOKBACK_COHORT" if execution is None else str(execution.get("status"))
                reason = ("Security remains available in the product view but is outside this frozen personalized cohort."
                          if execution is None else _json_value(execution.get("reason")))
                aliases = {str(product_row.get("ticker") or ""), identity}
                nse_code, bse_code = _code(product_row.get("screener_nse_code")), _code(product_row.get("screener_bse_code"))
                exchange_code = _code(product_row.get("exchange_security_id"))
                if nse_code:
                    aliases.update({nse_code, "NSE:" + nse_code})
                if bse_code:
                    aliases.update({bse_code, "BOM:" + bse_code, "BSE:" + bse_code})
                if str(product_row.get("primary_exchange") or "").upper() == "BSE" and exchange_code:
                    aliases.update({exchange_code, "BOM:" + exchange_code, "BSE:" + exchange_code})
                rows.append({
                    "requested_code": requested.get(identity), "isin": identity,
                    "ticker": _json_value(product_row.get("ticker")), "company": _json_value(product_row.get("company")),
                    "search_aliases": " ".join(sorted(value for value in aliases if value)),
                    "personalized_available": score is not None,
                    "result_type": "PERSONALIZED_CHAMPION" if score is not None else "PRODUCT_FALLBACK",
                    "status": status, "blocker": reason,
                    "personalized_rank": None if execution is None else _json_value(execution.get("personalized_rank")),
                    "personalized_score": score,
                    "goal_component_percentile": None if execution is None else _json_value(execution.get("goal_percentile")),
                    "lambdarank_component_percentile": None if execution is None else _json_value(execution.get("lambdarank_percentile")),
                    "target_attainment": None if execution is None else _json_value(execution.get("target_attainment")),
                    "target_shortfall": None if execution is None else _json_value(execution.get("target_shortfall")),
                    "xirr": None if execution is None else _json_value(execution.get("enhanced_carry_xirr_score")),
                    "amount_contributed": None if execution is None else _json_value(execution.get("amount_contributed")),
                    "amount_invested": None if execution is None else _json_value(execution.get("amount_invested")),
                    "residual_cash": None if execution is None else _json_value(execution.get("residual_cash")),
                    "cash_utilization": None if execution is None else _json_value(execution.get("cash_utilization")),
                    "unaffordable_rate": None if execution is None else _json_value(execution.get("unaffordable_rate")),
                    "execution_count": None if execution is None else _json_value(execution.get("execution_count")),
                    "shares_bought": None if execution is None else _json_value(execution.get("shares_bought")),
                    "terminal_price": None if execution is None else _json_value(execution.get("terminal_price")),
                    "corporate_action_evidence": None if execution is None else _json_value(execution.get("corporate_action_evidence")),
                    "baseline_rank": _json_value(product_row.get("product_baseline_sector_rank")),
                    "research_v2_rank": _json_value(product_row.get("product_research_v2_sector_rank")),
                    "fallback_available": bool(pd.notna(product_row.get("ticker"))),
                })
            rows.sort(key=lambda row: (row["personalized_rank"] is None,
                                       row["personalized_rank"] or 10**9, row["ticker"] or row["isin"]))
            response = {
                **self.metadata(), "profile": asdict(profile), "profile_fingerprint": key,
                "evaluation_mode": ("SEALED_EXACT_PROFILE_ARTIFACT" if self._frozen_profile_name(profile)
                                    else "FROZEN_MODEL_RECOMPUTATION"),
                "cache_hit": False, "latency_seconds": seconds,
                "row_count": len(rows), "personalized_count": sum(row["personalized_available"] for row in rows),
                "fallback_count": sum(row["result_type"] == "PRODUCT_FALLBACK" for row in rows),
                "rows": rows,
            }
            json.dumps(response, allow_nan=False)
            self.cache[cache_key] = json.loads(json.dumps(response))
            self.cache.move_to_end(cache_key)
            if len(self.cache) > self.cache_size:
                self.cache.popitem(last=False)
            return response

    def reproduce_frozen_profile(self, name: str) -> dict[str, Any]:
        if name not in self.config["profiles"]:
            raise PersonalizationError("unknown frozen profile")
        raw = dict(self.config["profiles"][name])
        payload = {"amount": raw["amount"], "interval_days": raw["interval_days"],
                   "lookback_months": raw["lookback_months"],
                   "target_cagr_percent": raw["target_cagr"] * 100,
                   "horizon_months": raw["horizon_months"]}
        profile = parse_profile(payload)
        current, seconds = self._calculate(profile, use_stored_frozen_profile=False)
        expected = self.frozen_rankings.loc[self.frozen_rankings.profile_name.eq(name)]
        paired = expected[["isin", *FEATURES, "lightgbm_lambdarank_score", "selected_ensemble_score"]].merge(
            current[["isin", *FEATURES, "lightgbm_lambdarank_score", "personalized_score"]],
            on="isin", suffixes=("_expected", "_actual"), validate="one_to_one",
        )
        errors = {}
        for column in [*FEATURES, "lightgbm_lambdarank_score"]:
            errors[column] = float(np.nanmax(np.abs(
                paired[column + "_expected"] - paired[column + "_actual"]
            )))
        errors["selected_ensemble_score"] = float(np.nanmax(np.abs(
            paired.selected_ensemble_score - paired.personalized_score
        )))
        return {"profile": name, "rows": len(paired), "max_abs_errors": errors,
                "passed": all(value <= 2e-12 for value in errors.values()),
                "latency_seconds": seconds}


_SERVICE: PersonalizedRankingService | None = None
_SERVICE_LOCK = RLock()


def personalized_service() -> PersonalizedRankingService:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = PersonalizedRankingService()
        return _SERVICE


def personalized_metadata() -> dict[str, Any]:
    try:
        return personalized_service().metadata()
    except (FileNotFoundError, OSError, PersonalizationError) as exc:
        return {"available": False, "status": "PERSONALIZED RUNTIME NOT PREPARED", "error": str(exc),
                "domains": DOMAINS}


def personalized_rank(payload: dict[str, Any]) -> dict[str, Any]:
    securities = payload.get("securities") if isinstance(payload, dict) else None
    if securities is not None and (not isinstance(securities, list) or len(securities) > 100):
        raise PersonalizationError("securities must be a list of at most 100 identifiers")
    profile = payload.get("profile", payload) if isinstance(payload, dict) else payload
    return personalized_service().rank(profile, securities=securities)
