"""Continuous closing-high scoring and explicit evidence checks.

Financial thresholds are review flags, not fitted weights or trade advice.
"""
import numpy as np
import pandas as pd

RECOVERY_BAND = .05


def recovery_freshness(age, distance):
    """Keep age outside recoveries; converge continuously to 1 at the high."""
    freshness = np.exp(-age.clip(lower=0) / 1095.75)
    depth = -distance.clip(-1, 0)
    recovery = np.exp(-np.square(depth / RECOVERY_BAND))
    return freshness + (1 - freshness) * recovery


def high_component(age, distance, annual_freshness):
    return (.5 * recovery_freshness(age, distance)
            + .3 * (1 + distance.clip(-1, 0)) + .2 * annual_freshness)


FINANCIAL_SECTORS = {'Banks', 'Finance', 'Capital Markets', 'Fintech'}


def review_stock(fact, evidence, receipt=None):
    """Return observable concerns without inventing missing lot/history data."""
    flags = []
    def number(name):
        return pd.to_numeric(fact.get(name), errors='coerce')
    if number('screener_pe_ratio') > 60:
        flags.append('Valuation: P/E above 60')
    if number('screener_pledged_pct') > 20:
        flags.append('Promoter pledge above 20%')
    if fact.get('product_sector') not in FINANCIAL_SECTORS:
        if number('screener_operating_cash_flow_crore') < 0:
            flags.append('Negative operating cash flow')
        if number('screener_debt_to_equity') > 1:
            flags.append('Debt/equity above 1')
    history = evidence.get('history_months', np.nan)
    if pd.notna(history) and history < 60:
        flags.append('Available price history under five years; not company age')
    series = str(fact.get('series', '')).upper()
    exchange = str(fact.get('primary_exchange', '')).upper()
    sme = ((exchange == 'BSE' and series in {'M', 'MT'})
           or (exchange == 'NSE' and series in {'SM', 'ST'}))
    execution = 'Reported activity only; fills and historical lot sizes unverified'
    if sme:
        execution = 'SME market lot unverified; excluded from ranked shortlist'
        flags.append(execution)
    elif series in {'T', 'XT', 'BE', 'BZ'}:
        flags.append('Trade-to-trade settlement: delivery and trading constraints require review')
    source = None
    if receipt is not None:
        tag = str(receipt.get('review_flag', ''))
        source = receipt.get('source_url')
        if 'business_continuity' in tag:
            flags.append('Business transformation: long price history is not continuous operating history')
        if 'historical_lot' in tag:
            flags.append('Former SME: historical SIP fills require dated lot sizes')
    return {'review_flags': flags, 'execution_evidence': execution,
            'sme_lot_unverified': sme, 'review_source_url': source,
            'history_scope': 'Available adjusted price series; lifetime cross-exchange coverage unverified'}
