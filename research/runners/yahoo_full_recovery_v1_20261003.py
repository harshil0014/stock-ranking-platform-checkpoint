"""Current-only Yahoo audit and blanks-only V6 recovery (2026-10-03).

Resumable batch cache. No historical panel or production writes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "experiments/current-data-recovery-20261003"
OUT = BASE / "yahoo-full-recovery-v1"
CACHE = OUT / "history-cache"
SOURCE = BASE / "current_company_facts_recovered_v6_full_screener.csv.gz"
PRIOR = BASE / "current_company_facts_recovered_v8_yahoo_rescued.csv.gz"
FINAL = BASE / "current_company_facts_recovered_v7_full_yahoo.csv.gz"
REPORT = ROOT / "research/reports/yahoo_current_full_recovery_20261003.md"
CUTOFF = pd.Timestamp("2026-10-03")
END = "2026-10-04"
BATCH = 40
OUT.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(exist_ok=True)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def nonblank(s: pd.Series) -> pd.Series:
    return s.notna() & s.astype(str).str.strip().ne("")


def code(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        x = float(s)
        if x.is_integer():
            return str(int(x))
    except ValueError:
        pass
    return s


def candidates(row, old):
    vals = []
    for col, method in [("bulk_classification_provider_symbol", "KNOWN_PROVIDER"),
                        ("yahoo_symbol", "PRIOR_VERIFIED_YAHOO")]:
        v = code(row.get(col)) if col in row else code(old.get(col))
        if v and v.endswith((".NS", ".BO")):
            vals.append((v, method))
    nse, bse, ticker = (code(row.get(c)) for c in
                        ("screener_nse_code", "screener_bse_code", "ticker"))
    if nse:
        vals.append((nse + ".NS", "EXACT_NSE_CODE"))
    if bse:
        vals.append((bse + ".BO", "EXACT_BSE_CODE"))
    if ticker and ticker.startswith("BSE-"):
        vals.append((ticker[4:] + ".BO", "REPO_BSE_CODE"))
    elif ticker:
        vals.append((ticker + ".NS", "REPO_NSE_TICKER"))
    result = []
    seen = set()
    for sym, method in vals:
        if sym not in seen:
            result.append((sym, method))
            seen.add(sym)
    return result


def extract(raw, symbol):
    if raw is None or raw.empty:
        return None
    try:
        if isinstance(raw.columns, pd.MultiIndex):
            if symbol in raw.columns.get_level_values(1):
                f = raw.xs(symbol, axis=1, level=1)
            elif symbol in raw.columns.get_level_values(0):
                f = raw[symbol]
            else:
                return None
        else:
            f = raw
        f = f.copy()
        f.index = pd.to_datetime(f.index, errors="coerce").tz_localize(None)
        f = f.loc[f.index.notna() & (f.index <= CUTOFF)].sort_index()
        f = f.loc[~f.index.duplicated(keep="last")]
        price_cols = [c for c in ("Adj Close", "Close") if c in f]
        if price_cols:
            f = f.loc[f[price_cols].notna().any(axis=1)]
        return f if len(f) else None
    except Exception:
        return None


def download(symbols, prefix="batch"):
    result = {}
    symbols = list(dict.fromkeys(symbols))
    for start in range(0, len(symbols), BATCH):
        batch = symbols[start:start+BATCH]
        path = CACHE / f"{prefix}_{start//BATCH:04d}.pkl"
        if path.exists():
            with path.open("rb") as f:
                got = pickle.load(f)
            if set(got.get("symbols", [])) != set(batch):
                raise RuntimeError(f"cache symbol mismatch: {path}")
            result.update(got["frames"])
            continue
        frames = {}
        for attempt in range(3):
            try:
                raw = yf.download(batch, start="1990-01-01", end=END,
                                  auto_adjust=False, actions=False, progress=False,
                                  threads=True, group_by="column", timeout=30)
                for sym in batch:
                    f = extract(raw, sym)
                    if f is not None:
                        frames[sym] = f
                break
            except Exception as exc:
                print("BATCH_RETRY", start, attempt, type(exc).__name__, flush=True)
                time.sleep(2 ** attempt)
        temp = path.with_suffix(".tmp")
        with temp.open("wb") as f:
            pickle.dump({"symbols": batch, "frames": frames}, f, protocol=4)
        temp.replace(path)
        result.update(frames)
        print("DOWNLOADED", min(start+BATCH, len(symbols)), len(symbols),
              "HISTORY", len(result), flush=True)
        time.sleep(0.3)
    return result


def series(frame, col):
    if frame is None or col not in frame:
        return pd.Series(dtype=float)
    s = pd.to_numeric(frame[col], errors="coerce")
    return s.loc[s.notna() & s.gt(0)].sort_index()


def anchor_return(s, months):
    if len(s) < 2:
        return np.nan, "INSUFFICIENT_DATA_QUALITY"
    anchor = CUTOFF - pd.DateOffset(months=months)
    before = s.loc[s.index <= anchor]
    if before.empty:
        return np.nan, "YAHOO_HISTORY_SHORTER_THAN_HORIZON"
    date = before.index[-1]
    if (anchor-date).days > 7:
        return np.nan, "STRICT_ANCHOR_MISSING_OVER_7D"
    span = (s.index[-1]-date).days
    if span <= 0:
        return np.nan, "INSUFFICIENT_DATA_QUALITY"
    val = float(np.expm1(np.log(float(s.iloc[-1]/before.iloc[-1])) *
                          (365.0/span if months >= 12 else 1.0)))
    return val, "OK"


def metrics(frame):
    adj = series(frame, "Adj Close")
    raw = series(frame, "Close")
    if len(adj) < 2:
        return None, "NO_ADJUSTED_HISTORY" if len(raw) else "NO_HISTORY"
    last = adj.index[-1]
    lag = (CUTOFF-last).days
    if lag > 7:
        status = "STALE_HISTORY"
    else:
        status = "CURRENT_HISTORY"
    p = adj.to_numpy(float)
    dates = adj.index
    peaks = np.maximum.accumulate(p)
    dd = p/peaks-1
    peak_idx = int(np.argmax(p))
    trough_idx = int(np.argmin(dd))
    high_mask = p >= peaks*(1-1e-10)
    last_peak_idx = np.maximum.accumulate(np.where(high_mask, np.arange(len(p)), 0))
    day_dates = dates.to_numpy(dtype="datetime64[D]")
    durations = (day_dates-day_dates[last_peak_idx]).astype(int)
    yr = adj.loc[adj.index >= CUTOFF-pd.Timedelta(days=365)]
    last3 = adj.loc[adj.index >= CUTOFF-pd.DateOffset(years=3)]
    def risk(s):
        r = np.log(s).diff().dropna().to_numpy(float)
        if len(r) < 60:
            return (np.nan, np.nan, np.nan, np.nan, np.nan)
        neg = r[r < 0]
        return (float(np.std(r, ddof=1)*np.sqrt(252)),
                float(np.sqrt(np.mean(np.minimum(r, 0)**2))*np.sqrt(252)),
                float(np.mean(r < 0)), float(np.mean(neg)) if len(neg) else 0.0,
                float(np.mean(np.minimum(r, 0)**2)))
    vol, down, freq, severity, semivar = risk(yr)
    vol3 = risk(last3)[0]
    horizons = {}
    reasons = {}
    for months in (1, 3, 6, 12, 36, 60, 84, 120):
        horizons[months], reasons[months] = anchor_return(adj, months)
    raw_high = series(frame, "High")
    raw_low = series(frame, "Low")
    raw_high52 = raw_high.loc[raw_high.index >= CUTOFF-pd.Timedelta(days=365)]
    raw_low52 = raw_low.loc[raw_low.index >= CUTOFF-pd.Timedelta(days=365)]
    raw_all_high = float(raw_high.max()) if len(raw_high) else np.nan
    raw_high_date = raw_high.idxmax().date().isoformat() if len(raw_high) else None
    rec = {
        "yahoo_status": status, "yahoo_history_start_date": dates[0].date().isoformat(),
        "yahoo_history_end_date": last.date().isoformat(),
        "yahoo_history_row_count": len(adj), "yahoo_history_months": (last-dates[0]).days/30.4375,
        "yahoo_terminal_lag_days": lag, "yahoo_provider_exchange": "NSE" if str(frame.attrs.get("symbol", "")).endswith(".NS") else "BSE",
        "yahoo_latest_adjusted_close": float(p[-1]),
        "yahoo_latest_raw_close": float(raw.iloc[-1]) if len(raw) else np.nan,
        "yahoo_adjusted_ath": float(p[peak_idx]),
        "yahoo_adjusted_ath_date": dates[peak_idx].date().isoformat(),
        "yahoo_days_since_adjusted_ath": (last-dates[peak_idx]).days,
        "yahoo_years_since_adjusted_ath": (last-dates[peak_idx]).days/365.0,
        "yahoo_distance_below_adjusted_ath": float(p[-1]/p[peak_idx]-1),
        "yahoo_current_drawdown": float(dd[-1]),
        "yahoo_max_drawdown": float(dd[trough_idx]),
        "yahoo_worst_drawdown_date": dates[trough_idx].date().isoformat(),
        "yahoo_current_underwater_days": int(durations[-1]),
        "yahoo_longest_underwater_days": int(durations.max()),
        "yahoo_recovery_from_deepest_trough": float(p[-1]/p[trough_idx]-1),
        "yahoo_adjusted_52w_high": float(yr.max()),
        "yahoo_adjusted_52w_low": float(yr.min()),
        "yahoo_distance_from_adjusted_52w_high": float(p[-1]/yr.max()-1),
        "yahoo_recovery_from_adjusted_52w_low": float(p[-1]/yr.min()-1),
        "yahoo_raw_ath_high": raw_all_high, "yahoo_raw_ath_high_date": raw_high_date,
        "yahoo_raw_52w_high": float(raw_high52.max()) if len(raw_high52) else np.nan,
        "yahoo_raw_52w_low": float(raw_low52.min()) if len(raw_low52) else np.nan,
        "yahoo_realized_volatility_1y": vol, "yahoo_realized_volatility_3y": vol3,
        "yahoo_downside_volatility_1y": down,
        "yahoo_downside_frequency_1y": freq,
        "yahoo_negative_return_severity_1y": severity,
        "yahoo_semivariance_1y": semivar,
        "yahoo_new_high_count_1y": int(np.sum((p >= peaks*(1-1e-10)) &
            (dates >= CUTOFF-pd.Timedelta(days=365)))),
    }
    for months, label in [(1,"1m"),(3,"3m"),(6,"6m"),(12,"1y"),
                          (36,"3y"),(60,"5y"),(84,"7y"),(120,"10y")]:
        rec[f"yahoo_return_{label}" if months < 12 else f"yahoo_strict_cagr_{label}"] = horizons[months]
        rec[f"yahoo_reason_{label}"] = reasons[months]
    rec["yahoo_momentum_6m_minus_1m"] = horizons[6]-horizons[1] if np.isfinite(horizons[6]) and np.isfinite(horizons[1]) else np.nan
    rec["yahoo_recent_recovery_3m"] = horizons[3]
    return rec, status


def main():
    base = pd.read_csv(SOURCE, low_memory=False)
    prior = pd.read_csv(PRIOR, low_memory=False)
    assert len(base) == len(prior) == 4436
    cands = [candidates(base.iloc[i], prior.iloc[i]) for i in range(len(base))]
    symbols = [c[0][0] for c in cands if c]
    # Prior name/price-verified BSE resolutions are retained, while the provider
    # and exact exchange symbols remain auditable in the map.
    frames = download(symbols)
    missed = [s for s in dict.fromkeys(symbols) if len(series(frames.get(s), "Adj Close")) == 0]
    if missed:
        frames.update(download(missed, "retry"))
    fallback = []
    for choices in cands:
        if not choices:
            continue
        first = frames.get(choices[0][0])
        first_adj = series(first, "Adj Close")
        if len(first_adj) >= 2 and (CUTOFF-first_adj.index[-1]).days <= 7:
            continue
        fallback.extend(sym for sym, _ in choices[1:] if sym not in frames)
    if fallback:
        frames.update(download(fallback, "fallback"))
    records, maps = [], []
    for i, choices in enumerate(cands):
        chosen, feat = None, None
        for symbol, method in choices:
            frame = frames.get(symbol)
            if frame is None:
                continue
            frame.attrs["symbol"] = symbol
            got, status = metrics(frame)
            if got is None:
                continue
            if chosen is None or (got["yahoo_terminal_lag_days"] <= 7 and feat["yahoo_terminal_lag_days"] > 7):
                chosen, feat = (symbol, method), got
            if got["yahoo_terminal_lag_days"] <= 7:
                break
        old = prior.iloc[i]
        if feat is None:
            feat = {"yahoo_status": "NO_HISTORY" if choices else "SYMBOL_UNRESOLVED"}
            for symbol, method in choices:
                one = series(frames.get(symbol), "Adj Close")
                if len(one) == 1:
                    chosen = (symbol, method)
                    feat = {"yahoo_status":"INSUFFICIENT_HISTORY_ROWS",
                            "yahoo_history_start_date":one.index[0].date().isoformat(),
                            "yahoo_history_end_date":one.index[0].date().isoformat(),
                            "yahoo_history_row_count":1,
                            "yahoo_history_months":0.0,
                            "yahoo_terminal_lag_days":(CUTOFF-one.index[0]).days}
                    break
        feat.update(row=i, yahoo_symbol=chosen[0] if chosen else None,
                    yahoo_symbol_method=chosen[1] if chosen else None)
        records.append(feat)
        maps.append({"row": i, "ticker": base.at[i,"ticker"], "company": base.at[i,"company"],
                     "isin": base.at[i,"isin"], "primary_exchange": base.at[i,"primary_exchange"],
                     "candidate_symbols": "|".join(x[0] for x in choices),
                     "yahoo_symbol": feat["yahoo_symbol"], "resolution_method": feat["yahoo_symbol_method"],
                     "prior_yahoo_symbol": old.get("yahoo_symbol"),
                     "status": feat["yahoo_status"]})
        if (i+1) % 500 == 0:
            print("METRICS", i+1, len(base), flush=True)
    m = pd.DataFrame(records).set_index("row")
    result = base.copy()
    for col in m:
        if col not in result:
            result[col] = m[col].reindex(result.index).values
    ledger = []
    def fill(target, source, semantic):
        if target not in result or source not in result:
            return
        mask = ~nonblank(result[target]) & nonblank(result[source]) & result.yahoo_status.eq("CURRENT_HISTORY")
        for i in result.index[mask]:
            value = result.at[i,source]
            result.at[i,target] = value
            ledger.append({"row": int(i), "ticker": result.at[i,"ticker"],
                           "isin": result.at[i,"isin"], "field": target,
                           "value": value, "source_column": source,
                           "semantic_basis": semantic, "yahoo_symbol": result.at[i,"yahoo_symbol"],
                           "source": "YAHOO_FINANCE_CURRENT_2026-10-03",
                           "provider_last_date": result.at[i,"yahoo_history_end_date"]})
    for years, target in [(1,"product_baseline_yoy_growth"),(3,"product_baseline_cagr_3y"),
                          (5,"product_baseline_cagr_5y"),(7,"current_cagr_7y"),
                          (10,"current_cagr_10y")]:
        fill(target, f"yahoo_strict_cagr_{years}y", "ADJUSTED_CLOSE_STRICT_ANCHOR")
    # The repo's recorded highs are adjusted-close extrema. Raw OHLC extrema
    # stay in separate Yahoo columns, including when split semantics differ.
    for target, source in [("high_52w","yahoo_adjusted_52w_high"),
                           ("low_52w","yahoo_adjusted_52w_low"),
                           ("recorded_high","yahoo_adjusted_ath"),
                           ("recorded_high_date","yahoo_adjusted_ath_date"),
                           ("product_baseline_days_since_recorded_high","yahoo_days_since_adjusted_ath"),
                           ("latest_price","yahoo_latest_raw_close")]:
        fill(target, source, "RAW_CLOSE" if target=="latest_price" else "ADJUSTED_CLOSE_EXTREMUM")
    # Explicit current aliases for the V14 inference contract.
    aliases = {"current_history_months":"yahoo_history_months",
               "current_distance_from_recorded_high":"yahoo_distance_below_adjusted_ath",
               "current_full_history_max_drawdown":"yahoo_max_drawdown",
               "current_drawdown_duration_days":"yahoo_current_underwater_days",
               "current_downside_volatility_1y":"yahoo_downside_volatility_1y",
               "current_realized_volatility_1y":"yahoo_realized_volatility_1y"}
    for target, source in aliases.items():
        if target not in result:
            result[target] = np.nan
        fill(target, source, "ADJUSTED_CLOSE_CURRENT")
    for years in (1,3,5,7,10):
        target = f"current_has_true_{years}y"
        result[target] = result[f"yahoo_strict_cagr_{years}y"].notna() & result.yahoo_status.eq("CURRENT_HISTORY")

    # Every original cell with content must compare equal after serialization.
    for col in base:
        old = base[col]
        mask = nonblank(old)
        a = old.loc[mask].astype(str).reset_index(drop=True)
        b = result.loc[mask,col].astype(str).reset_index(drop=True)
        if not a.equals(b):
            raise AssertionError(f"V6 nonblank changed: {col}")
    result.to_csv(FINAL, index=False, compression="gzip")
    check = pd.read_csv(FINAL, low_memory=False)
    for col in base:
        mask = nonblank(base[col])
        if pd.api.types.is_numeric_dtype(base[col]):
            a = pd.to_numeric(base.loc[mask,col],errors="coerce").to_numpy(float)
            b = pd.to_numeric(check.loc[mask,col],errors="coerce").to_numpy(float)
            if not np.allclose(a,b,rtol=0,atol=1e-10,equal_nan=True):
                raise AssertionError(f"serialized V6 nonblank changed: {col}")
        elif not base.loc[mask,col].astype(str).reset_index(drop=True).equals(check.loc[mask,col].astype(str).reset_index(drop=True)):
            raise AssertionError(f"serialized V6 text changed: {col}")

    pd.DataFrame(maps).to_csv(OUT/"yahoo_symbol_map.csv",index=False)
    cover = result[["ticker","company","isin","primary_exchange","yahoo_symbol","yahoo_status",
                    "yahoo_history_start_date","yahoo_history_end_date","yahoo_history_row_count",
                    "yahoo_history_months","yahoo_terminal_lag_days"]].copy()
    cover.to_csv(OUT/"yahoo_coverage.csv",index=False)
    cover.loc[cover.yahoo_status.isin(["NO_HISTORY","SYMBOL_UNRESOLVED","INSUFFICIENT_HISTORY_ROWS"])].to_csv(OUT/"yahoo_failed_symbols.csv",index=False)
    cover.loc[cover.yahoo_status.eq("STALE_HISTORY")].to_csv(OUT/"yahoo_stale_symbols.csv",index=False)
    pd.DataFrame(ledger,columns=["row","ticker","isin","field","value","source_column","semantic_basis","yahoo_symbol","source","provider_last_date"]).to_csv(OUT/"yahoo_filled_cells.csv",index=False)
    fields = {"1Y":"product_baseline_yoy_growth","3Y":"product_baseline_cagr_3y",
              "5Y":"product_baseline_cagr_5y","7Y":"current_cagr_7y","10Y":"current_cagr_10y",
              "history_months":"current_history_months","52W high":"high_52w","52W low":"low_52w",
              "ATH":"recorded_high","ATH date":"recorded_high_date",
              "days since ATH":"product_baseline_days_since_recorded_high",
              "distance below ATH":"current_distance_from_recorded_high",
              "max drawdown":"current_full_history_max_drawdown",
              "current drawdown":"yahoo_current_drawdown",
              "underwater duration":"current_drawdown_duration_days",
              "downside volatility":"current_downside_volatility_1y",
              "realized volatility":"current_realized_volatility_1y"}
    cov = []
    for label, col in fields.items():
        before = int(nonblank(base[col]).sum()) if col in base else 0
        after = int(nonblank(result[col]).sum()) if col in result else 0
        cov.append({"feature":label,"column":col,"before":before,"after":after,"new":after-before})
    pd.DataFrame(cov).to_csv(OUT/"yahoo_feature_coverage_before_after.csv",index=False)
    missing, reasons = [], []
    for years, field in [(1,fields["1Y"]),(3,fields["3Y"]),(5,fields["5Y"]),
                         (7,fields["7Y"]),(10,fields["10Y"])]:
        reason_col = f"yahoo_reason_{years}y"
        for i in result.index[~nonblank(result[field])]:
            status = result.at[i,"yahoo_status"]
            if status == "SYMBOL_UNRESOLVED": reason = "PROVIDER_SYMBOL_UNRESOLVED"
            elif status == "NO_HISTORY": reason = "YAHOO_NO_DATA_OR_DELISTED"
            elif status == "INSUFFICIENT_HISTORY_ROWS": reason = "INSUFFICIENT_HISTORY_ROWS"
            elif status == "STALE_HISTORY": reason = "STALE_OR_SUSPENDED"
            else: reason = result.at[i,reason_col]
            listing = pd.to_datetime(result.at[i,"listing_date"],errors="coerce") if "listing_date" in result else pd.NaT
            if reason == "YAHOO_HISTORY_SHORTER_THAN_HORIZON" and pd.notna(listing) and listing > CUTOFF-pd.DateOffset(years=years):
                reason = "LISTED_LESS_THAN_HORIZON"
            missing.append({"row":int(i),"ticker":result.at[i,"ticker"],"isin":result.at[i,"isin"],
                            "horizon_years":years,"field":field,"reason_code":reason,
                            "yahoo_symbol":result.at[i,"yahoo_symbol"],
                            "first_price_date":result.at[i,"yahoo_history_start_date"],
                            "last_price_date":result.at[i,"yahoo_history_end_date"]})
        frame = pd.DataFrame(x for x in missing if x["horizon_years"]==years)
        for reason, count in frame.reason_code.value_counts().items():
            reasons.append({"horizon_years":years,"reason_code":reason,"count":int(count)})
    pd.DataFrame(missing).to_csv(OUT/"yahoo_remaining_missing.csv",index=False)
    pd.DataFrame(reasons).to_csv(OUT/"yahoo_missing_reason_codes.csv",index=False)
    audits=[]
    for target, source, unit in [("product_baseline_yoy_growth","yahoo_strict_cagr_1y","return"),
                                 ("product_baseline_cagr_3y","yahoo_strict_cagr_3y","return"),
                                 ("product_baseline_cagr_5y","yahoo_strict_cagr_5y","return"),
                                 ("latest_price","yahoo_latest_raw_close","price"),
                                 ("high_52w","yahoo_adjusted_52w_high","adjusted_close"),
                                 ("low_52w","yahoo_adjusted_52w_low","adjusted_close"),
                                 ("recorded_high","yahoo_adjusted_ath","adjusted_close")]:
        if target not in base: continue
        a = pd.to_numeric(base[target],errors="coerce")
        b = pd.to_numeric(result[source],errors="coerce")
        for i in result.index[a.notna() & b.notna()]:
            diff = float(b[i]-a[i]); pct = abs(diff/a[i]) if a[i] else np.nan
            audits.append({"row":int(i),"ticker":result.at[i,"ticker"],"field":target,
                           "existing":float(a[i]),"yahoo":float(b[i]),"absolute_difference":abs(diff),
                           "relative_difference":pct,"unit":unit,
                           "likely_reason":"ADJUSTED_VS_RAW_OR_CORPORATE_ACTION" if unit=="raw_price" and pct>0.1 else "SOURCE_OR_DATE_DIFFERENCE" if pct>0.05 else "SMALL_OR_NONE",
                           "yahoo_last_date":result.at[i,"yahoo_history_end_date"]})
    pd.DataFrame(audits).to_csv(OUT/"yahoo_discrepancy_audit.csv",index=False)
    status_counts = result.yahoo_status.value_counts().to_dict()
    ledger_df = pd.DataFrame(ledger)
    v6_fills = sum(x["field"] in base.columns for x in ledger)
    alias_fills = len(ledger)-v6_fills
    yahoo_columns = [c for c in result if c.startswith("yahoo_") and c not in base]
    yahoo_cells = sum(int(nonblank(result[c]).sum()) for c in yahoo_columns)
    summary = {"schema":"yahoo_full_recovery_v1","cutoff":"2026-10-03","total_stocks":len(result),
               "symbol_resolved":int(result.yahoo_symbol.notna().sum()),
               "symbol_unresolved":int(result.yahoo_symbol.isna().sum()),
               "successful_history_download":int(result.yahoo_status.isin(["CURRENT_HISTORY","STALE_HISTORY","INSUFFICIENT_HISTORY_ROWS"]).sum()),
               "current_history":status_counts.get("CURRENT_HISTORY",0),
               "stale_history":status_counts.get("STALE_HISTORY",0),
               "failed_history_download":status_counts.get("NO_HISTORY",0),
               "insufficient_history_rows":status_counts.get("INSUFFICIENT_HISTORY_ROWS",0),
               "no_verified_symbol":int(result.yahoo_symbol.isna().sum()),
               "insufficient_true_5y_history":int((result.yahoo_status.eq("CURRENT_HISTORY") & ~result.current_has_true_5y).sum()),
               "nse_current":int(((result.yahoo_status=="CURRENT_HISTORY") & result.yahoo_symbol.astype(str).str.endswith(".NS")).sum()),
               "bse_current":int(((result.yahoo_status=="CURRENT_HISTORY") & result.yahoo_symbol.astype(str).str.endswith(".BO")).sum()),
               "true_5y_history":int(result.current_has_true_5y.sum()),
               "true_7y_history":int(result.current_has_true_7y.sum()),
               "true_10y_history":int(result.current_has_true_10y.sum()),
               "structurally_under_5y":int((pd.to_datetime(result.listing_date,errors="coerce") > CUTOFF-pd.DateOffset(years=5)).sum()),
               "new_existing_blank_cells_filled":len(ledger),
               "v6_existing_field_blank_fills":v6_fills,
               "new_current_alias_cells":alias_fills,
               "new_yahoo_diagnostic_cells":yahoo_cells,
               "total_new_nonblank_cells":len(ledger)+yahoo_cells+int(sum(nonblank(result[c]).sum() for c in result if c.startswith("current_has_true_") and c not in base)),
               "stocks_improved":int(ledger_df.row.nunique()) if len(ledger_df) else 0,
               "v6_nonblank_unchanged":True,"production_modified":False,
               "historical_panels_modified":False,
               "coverage":cov,"reason_counts":reasons}
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,default=str),encoding="utf-8")
    lines = ["# Yahoo current full recovery — 2026-10-03", "",
             f"Base: `{SOURCE.relative_to(ROOT)}`. Final: `{FINAL.relative_to(ROOT)}`.", "",
             f"Universe {len(result):,}; Yahoo symbol with observed adjusted price {summary['symbol_resolved']:,} ({summary['symbol_resolved']/len(result):.2%}); current usable histories {summary['current_history']:,}; stale histories {summary['stale_history']:,}; unresolved symbols {summary['symbol_unresolved']:,}; no-data histories {summary['failed_history_download']:,}; one-row histories {summary['insufficient_history_rows']:,}.",
             f"NSE current {summary['nse_current']:,}; BSE current {summary['bse_current']:,}. Blanks-only feature fills {len(ledger):,} across {summary['stocks_improved']:,} stocks ({v6_fills:,} in original V6 columns; {alias_fills:,} in new current aliases). Separate Yahoo diagnostic columns add {yahoo_cells:,} nonblank cells.",
             "", "## Coverage", "", "| Feature | Before | After | New |", "|---|---:|---:|---:|"]
    lines += [f"| {x['feature']} | {x['before']:,} | {x['after']:,} | {x['new']:,} |" for x in cov]
    lines += ["", "## Method", "", "Yahoo adjusted close drives returns, drawdowns, volatility and adjusted ATH. Raw high/low drive raw-price high fields. Strict annual anchors use the latest observation on or before the calendar anchor, within seven days, and annualize over actual elapsed days. Shorter momentum uses exact observed interval return. Stale means the last Yahoo close is more than seven calendar days before 2026-10-03; stale histories contribute no blank fills. Volatility uses daily log returns and 252 trading days; downside deviation uses zero target and the same annualization. All dates and features stop at 2026-10-03.",
              "", f"True 5Y {summary['true_5y_history']:,}; true 7Y {summary['true_7y_history']:,}; true 10Y {summary['true_10y_history']:,}. Listing date proves fewer than five years for {summary['structurally_under_5y']:,} stocks.",
              "", "## Missingness and discrepancies", "", "Per-stock reasons are in `yahoo_remaining_missing.csv`; aggregates are in `yahoo_missing_reason_codes.csv`. Discrepancies are audit only; existing professor, Screener and accepted provider cells are preserved."]
    for target, group in pd.DataFrame(audits).groupby("field"):
        rel = group.relative_difference.dropna()
        if len(rel):
            absdiff = group.absolute_difference.dropna()
            unit = " percentage points" if group.unit.iloc[0] == "return" else " price units"
            scale = 100 if group.unit.iloc[0] == "return" else 1
            lines.append(f"- {target}: {len(rel):,} comparable; median absolute difference {absdiff.median()*scale:.2f}{unit}; p90 {absdiff.quantile(.9)*scale:.2f}{unit}; over 10% relative difference {(rel>.1).sum():,}.")
    lines += ["", "## Five Screener nonmatches", ""]
    names = ["TRUSTWAVE SECURITIES LIMITED","MIDWEST ENERGY LIMITED","Naturite Agro Products Limited","Kalyani Commercials Limited","Taal Tech Limited"]
    for name in names:
        q = result.loc[result.company.astype(str).str.casefold().eq(name.casefold())]
        for _, r in q.iterrows():
            lines.append(f"- {r['company']}: {r['yahoo_symbol']} — {r['yahoo_status']}; last {r['yahoo_history_end_date']}.")
    lines += ["", "## Integrity", "", "All V6 nonblank cells were compared before and after serialization. This runner writes only the current recovery directory and this report. Existing historical panels, frozen champion artifacts, production, website and Railway were not written.", ""]
    REPORT.write_text("\n".join(lines),encoding="utf-8")
    artifacts = [*OUT.glob("*.csv"), OUT/"summary.json", FINAL, REPORT]
    manifest = {str(p.relative_to(ROOT)): {"sha256":sha(p),"bytes":p.stat().st_size} for p in artifacts}
    manifest["input_v6"] = {"path":str(SOURCE.relative_to(ROOT)),"sha256":sha(SOURCE)}
    manifest["prior_symbol_evidence"] = {"path":str(PRIOR.relative_to(ROOT)),"sha256":sha(PRIOR)}
    manifest["cache_batches"] = {
        str(p.relative_to(ROOT)): {"sha256": sha(p), "bytes": p.stat().st_size}
        for p in CACHE.glob("*.pkl")
    }
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k not in ("coverage","reason_counts")},indent=2),flush=True)


if __name__ == "__main__":
    main()
