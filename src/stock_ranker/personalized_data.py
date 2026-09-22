"""Read-only exact-identity adapters for the personalized research layer."""
from hashlib import sha256
from pathlib import Path
import pandas as pd

from stock_ranker.personalized import HistoryBook


def load_history_book(facts, history_root):
    if facts['isin'].isna().any() or facts['isin'].duplicated().any() or facts.ticker.duplicated().any():
        raise ValueError('unique complete security identities required')
    root = Path(history_root).resolve()
    book, hashes = HistoryBook({}), {}
    for item in facts.itertuples(index=False):
        path = (root / f'{item.ticker}.csv').resolve()
        if path.parent != root:
            raise ValueError('unsafe history filename')
        if not path.is_file():
            book.errors[item.isin] = 'HISTORY_FILE_MISSING'
            continue
        raw = path.read_bytes()
        hashes[path.name] = sha256(raw).hexdigest()
        try:
            from io import BytesIO
            frame = pd.read_csv(BytesIO(raw), usecols=['date', 'adjusted_close'])
            listing = pd.to_datetime(item.listing_date, errors='coerce')
            if pd.notna(listing):
                frame = frame.loc[pd.to_datetime(frame.date) >= listing]
            one = HistoryBook({item.isin: frame})
            book.arrays.update(one.arrays)
            book.errors.update(one.errors)
        except (ValueError, OSError) as exc:
            book.errors[item.isin] = type(exc).__name__ + ':' + str(exc)
    return book, hashes


def current_evidence(facts, *, knowledge_date, ensemble=None):
    """Current evidence only. Fundamentals require observed-at <= knowledge date.

    Current sector labels must never be relabelled as historical classifications.
    A caller attempting a historical snapshot must instead use the existing PIT
    research adapters and pass their verified evidence to the ranking layer.
    """
    cutoff = pd.Timestamp(knowledge_date, tz='UTC')
    if 'trade_date' in facts and pd.to_datetime(facts.trade_date, utc=True).gt(cutoff).any():
        raise ValueError('current snapshot cannot be used before its trade date')
    evidence = facts[['isin', 'product_sector']].rename(columns={'product_sector': 'sector'}).copy()
    for target, source, sign in [('production_score', 'product_baseline_sector_rank', -1),
                                 ('research_v2_score', 'research_v2_score', 1)]:
        if source in facts:
            evidence[target] = sign * pd.to_numeric(facts[source], errors='coerce')
    observed = pd.to_datetime(facts.get('screener_source_observed_at', pd.Series(pd.NaT, index=facts.index)), utc=True, errors='coerce')
    for target, source, sign in [('quality_score', 'screener_roce_pct', 1), ('valuation_score', 'screener_pe_ratio', -1)]:
        if source in facts:
            values = pd.to_numeric(facts[source], errors='coerce').where(observed.le(cutoff))
            if source == 'screener_pe_ratio':
                values = values.where(values > 0)
            evidence[target] = sign * values
    if ensemble is not None:
        if pd.to_datetime(ensemble.as_of_date, utc=True).gt(cutoff).any():
            raise ValueError('ensemble is newer than knowledge cutoff')
        evidence = evidence.merge(ensemble[['isin', 'ensemble_score']], on='isin', how='left', validate='one_to_one')
    return evidence
