"""Read-only, cell-grounded professor benchmark, retaining duplicate display rows."""
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile
import math

import pandas as pd

from stock_ranker.professor_reference import _XlsxCells, NS


def professor_benchmark(path):
    path = Path(path)
    values, formulas = {}, {}
    with ZipFile(path) as archive:
        shared = _XlsxCells._shared_strings(archive)
        paths = _XlsxCells._sheet_paths(archive)
        for sheet in ('SIP Portfolio', 'StockHistoryData'):
            with archive.open(paths[sheet]) as handle:
                for _, cell in ET.iterparse(handle, events=('end',)):
                    if cell.tag != f"{{{NS['m']}}}c":
                        continue
                    address = cell.attrib.get('r')
                    kind = cell.attrib.get('t')
                    raw = cell.findtext('m:v', None, NS)
                    value = raw
                    if kind == 's' and raw is not None:
                        value = shared[int(raw)]
                    elif kind == 'inlineStr':
                        value = ''.join(cell.itertext())
                    elif kind not in ('str', 'e') and raw is not None:
                        value = float(raw)
                    values[sheet, address] = value
                    f = cell.find('m:f', NS)
                    if f is not None and f.text:
                        formulas[f'{sheet}!{address}'] = f.text
                    cell.clear()
    def number(sheet, cell):
        v = values.get((sheet, cell))
        return float(v) if isinstance(v, (float, int)) and math.isfinite(v) else None
    sheet = 'SIP Portfolio'
    target = number(sheet, 'P1')
    rows = []
    for r in range(7, 21):
        code = values.get((sheet, f'B{r}'))
        if not code:
            continue
        price, shares, invested = [number(sheet, f'{c}{r}') for c in ('D', 'E', 'G')]
        value = price * shares if price is not None and price > 0 and shares is not None else None
        gain = value - invested if value is not None and invested is not None and invested > 0 else None
        row = {'workbook_row': r, 'requested_code': code, 'shares_bought': shares,
               'average_price': invested / shares if invested is not None and shares else None,
               'amount_invested': invested, 'current_price': price, 'current_value': value,
               'profit_loss': gain, 'profit_loss_pct': gain / invested if gain is not None else None,
               'cached_rank': number(sheet, f'N{r}'), 'cached_profit_loss_pct': number(sheet, f'I{r}'),
               'status': ('UNUSABLE_ZERO_INVESTMENT_CACHE' if invested is None or invested <= 0 else
                          'CACHED_ARITHMETIC_ONLY' if value is not None else 'MISSING_CURRENT_PRICE'),
               'source_cells': f'{sheet}!B{r}:N{r}'}
        for y, c in ((10, 'J'), (5, 'K'), (3, 'L')):
            row[f'cagr_{y}y'] = number(sheet, f'{c}{r}')
            row[f'target_{y}y'] = ('UNKNOWN' if row[f'cagr_{y}y'] is None or target is None else
                                    'ACHIEVED_HISTORICALLY' if row[f'cagr_{y}y'] >= target else 'SHORTFALL')
        rows.append(row)
    frame = pd.DataFrame(rows)
    frame['professor_style_rank'] = frame.profit_loss_pct.rank(ascending=False, method='min')
    audit = {'workbook_sha256': sha256(path.read_bytes()).hexdigest(),
             'amount': number(sheet, 'B1'), 'lookback_months': number(sheet, 'B2'),
             'interval_days': number(sheet, 'B3'), 'target_cagr': target,
             'rank_formula': formulas.get('SIP Portfolio!N7'),
             'purchase_formula': formulas.get('StockHistoryData!F3'),
             'calendar_formula': formulas.get('StockHistoryData!B3'),
             'price_lookup_formula': formulas.get('StockHistoryData!D3'),
             'unknowns': ['GoogleFinance live recalculation and exchange holiday behavior',
                          'Uncached/spilled execution-price cells', 'Corporate-action basis of cached prices',
                          'Delisting proceeds and historical membership'],
             'duplicate_display_rows': int(frame.requested_code.duplicated().sum()),
             'rank_basis': 'profit/loss divided by actual amount spent; no target weight',
             'cached_arithmetic_matches': int((frame.profit_loss_pct - frame.cached_profit_loss_pct).abs().lt(1e-10).sum()),
             'source_is_instruction': False}
    return frame, audit


def professor_purchase_benchmark(execution_prices, amount, current_price, *, verified_raw_basis=False):
    """Workbook ROUNDOWN(amount/price), no unused-cash reinvestment, gain/spend.

    Dates/prices must already follow the supplied workbook's execution schedule;
    this function does not invent missing GoogleFinance/holiday behavior. Splits
    must be reconciled externally to a common share basis. This is deliberately
    separate from the enhanced contribution-and-cash accounting engine.
    """
    import numpy as np
    if not verified_raw_basis:
        raise ValueError('verified purchase prices and corporate-action share basis required')
    prices = np.asarray(execution_prices, dtype=float)
    if not math.isfinite(amount) or amount <= 0 or len(prices) == 0 or not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError('invalid purchase inputs')
    shares = np.floor(amount / prices)
    quantity, spent = float(shares.sum()), float(np.dot(shares, prices))
    valid_terminal = current_price is not None and math.isfinite(current_price) and current_price > 0
    value = quantity * current_price if valid_terminal else None
    return {'shares_bought': quantity, 'amount_invested': spent, 'average_price': spent / quantity if quantity else None,
            'amount_allocated': amount * len(prices), 'unused_cash_excluded_by_professor': amount * len(prices) - spent,
            'current_value': value, 'profit_loss': value - spent if value is not None else None,
            'profit_loss_pct': value / spent - 1 if value is not None and spent > 0 else None,
            'status': 'AVAILABLE' if valid_terminal and spent > 0 else 'UNKNOWN_RETURN'}
