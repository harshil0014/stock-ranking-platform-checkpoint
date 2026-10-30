"""Standalone replication of Master Sheet v4.3 SIP Portfolio, without ranking models.

Inputs are worksheet price cells, not a replacement market-data provider. Run --help.
Only the Python standard library is needed. The source workbook is never modified.
"""
from __future__ import annotations

import argparse
import calendar
import csv
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKBOOK = Path.home() / 'Downloads/_Organized/Documents/Copy of OK Strategy - Master Sheet v4.3 (1).xlsx'
M = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
EPOCH = date(1899, 12, 30)
ERRORS = {'#N/A', '#VALUE!', '#DIV/0!', '#REF!', '#NUM!', '#NAME?', '#NULL!'}


def column(n):
    result = ''
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def error(value):
    return isinstance(value, str) and value in ERRORS


def numeric(value):
    if value is None or value == '':
        return 0.0
    return value if number(value) or error(value) else '#VALUE!'


def mul(a, b):
    a, b = numeric(a), numeric(b)
    return a if error(a) else b if error(b) else a * b


def divide(a, b):
    a, b = numeric(a), numeric(b)
    return a if error(a) else b if error(b) else '#DIV/0!' if b == 0 else a / b


def sheets_sum(values):
    values = list(values)
    return next((v for v in values if error(v)), sum(v for v in values if number(v)))


def workday(value: date, days: int):
    step = 1 if days >= 0 else -1
    remaining = abs(days)
    while remaining:
        value += timedelta(days=step)
        remaining -= value.weekday() < 5
    return value


def schedule(as_of: date, months=36, interval=30):
    """B3, A5, B4#, C3:C9991 and the GF request date, literally."""
    if months < 0 or int(months) != months or interval <= 0 or int(interval) != interval:
        raise ValueError('Supported controls: nonnegative integer months, positive integer interval')
    y, m = divmod(as_of.year * 12 + as_of.month - 1 - months, 12)
    base = date(y, m + 1, calendar.monthrange(y, m + 1)[1])
    count = math.trunc((as_of - base).days / interval)
    if count < 1:
        raise ValueError('SEQUENCE(A5,...) has nonpositive row count; workbook schedule is invalid')
    if count + 3 > 9991:
        raise ValueError('Schedule exceeds the source workbook formula extent (row 9991)')
    result = []
    for i in range(count + 1):  # B3 is itself a contribution, followed by A5 rows.
        b = base + timedelta(days=i * interval)
        c = workday(b, 1)
        result.append({'history_row': i + 3, 'scheduled_date': b.isoformat(),
                       'workday_date': c.isoformat(), 'request_start': workday(c, -2).isoformat(),
                       'request_num_days': 1})
    return result


def calculate(prices, quote, amount=7500, static_quantity=None, first_slot=False,
              code_present=True, invested_guard_present=True):
    """Evaluate F/G history columns and E:I summary. None means a truly blank cell.

    Receipt rows are the actual output cells of INDEX(GOOGLEFINANCE(...),2).
    This boundary preserves GF errors/spills and the Frontier guard without guessing
    a provider's holiday, adjustment, timezone or coercion behavior.
    """
    trades = []
    for row, price in sorted(prices.items()):
        if not 3 <= row <= 9991:
            raise ValueError('History receipt row outside source formula range')
        qty = '' if price is None else static_quantity
        if price is not None and static_quantity is None:
            quotient = divide(amount, price)
            qty = quotient if error(quotient) else math.trunc(quotient)
        cost = mul(price, qty)
        trades.append({'history_row': row, 'close': price, 'shares_bought': qty, 'cost': cost,
                       'included_in_invested': row <= 2499})
    shares = sheets_sum(t['shares_bought'] for t in trades) if code_present else ''
    invested = sheets_sum(t['cost'] for t in trades if t['included_in_invested']) if invested_guard_present else ''
    average = divide(invested, shares)
    if not first_slot and error(average):
        average = 0
    current = mul(quote, shares)
    profit = '' if error(current) or error(invested) else divide(numeric(current) - numeric(invested), invested)
    if error(profit):
        profit = ''
    return {'shares_bought': shares, 'average_price': average, 'invested': invested,
            'current_value': current, 'profit_fraction': profit}, trades


def rank_rows(rows):
    scores = [r['profit_fraction'] for r in rows if number(r['profit_fraction'])]
    for row in rows:
        score = row['profit_fraction']
        row['rank'] = 1 + sum(v > score for v in scores) if number(score) else '#N/A'
    return rows


def read_workbook(path):
    """Stream both dependent sheets; retain cached price cells and formula evidence."""
    cells = {}
    prices = {r: {} for r in range(7, 21)}
    scans = {}
    with ZipFile(path) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            shared = [''.join(t.text or '' for t in s.iter(M + 't'))
                      for s in ET.fromstring(z.read('xl/sharedStrings.xml')).findall(M + 'si')]
        rels = {r.attrib['Id']: r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        sheets = ET.fromstring(z.read('xl/workbook.xml')).findall(M + 'sheets/' + M + 'sheet')
        for sheet in sheets:
            name = sheet.attrib['name']
            if name not in ('SIP Portfolio', 'StockHistoryData'):
                continue
            target = rels[sheet.attrib[R + 'id']].lstrip('/')
            if not target.startswith('xl/'):
                target = 'xl/' + target
            if '..' in Path(target).parts:
                raise ValueError('Unsafe workbook sheet path')
            retained, definitions, counts = {}, {}, {'cells': 0, 'numeric_price_cells': 0, 'price_error_cells': 0}
            price_cols = {column(5 + 4 * i): 7 + i for i in range(14)}
            with z.open(target) as stream:
                for _, row in ET.iterparse(stream, events=['end']):
                    if row.tag != M + 'row':
                        continue
                    rn = int(row.attrib['r'])
                    for c in row.findall(M + 'c'):
                        counts['cells'] += 1
                        addr, kind = c.attrib['r'], c.attrib.get('t', 'n')
                        raw, f = c.find(M + 'v'), c.find(M + 'f')
                        val = raw.text if raw is not None else None
                        if kind == 's' and val is not None:
                            val = shared[int(val)]
                        elif kind == 'inlineStr':
                            val = ''.join(t.text or '' for t in c.iter(M + 't'))
                        elif kind == 'n' and val is not None:
                            val = float(val)
                        formula = f.text if f is not None else None
                        attrs = dict(f.attrib) if f is not None else {}
                        if formula and attrs.get('t') == 'shared':
                            definitions[attrs['si']] = {'origin': addr, 'formula': formula, 'attributes': attrs}
                        if (name == 'SIP Portfolio' and rn <= 21) or (name == 'StockHistoryData' and rn <= 42):
                            retained[addr] = {'value': val, 'type': kind, 'formula': formula, 'formula_attributes': attrs}
                        col = re.sub(r'\d', '', addr)
                        if name == 'StockHistoryData' and rn >= 3 and col in price_cols and val is not None:
                            prices[price_cols[col]][rn] = val
                            counts['numeric_price_cells'] += number(val)
                            counts['price_error_cells'] += kind == 'e'
                    row.clear()
            cells[name] = {'cells': retained, 'shared_formula_definitions': definitions}
            scans[name] = counts
    return cells, prices, scans


def write_csv(path, rows, fields=None):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def value(cells, sheet, address):
    return cells[sheet]['cells'].get(address, {}).get('value')


def parse_cell(text):
    if text == '':
        return None
    if text in ERRORS:
        return text
    v = float(text)
    if not math.isfinite(v):
        raise ValueError('Nonfinite price input')
    return v


def validate_layout(cells):
    """Reject formula revisions instead of quietly running a different workbook."""
    norm = lambda s: re.sub(r'\s+', '', s or '').upper()
    expected = {
        ('SIP Portfolio', 'N7'): 'rank(I7,$I$7:$I$20)',
        ('SIP Portfolio', 'H7'): 'D7*E7',
        ('SIP Portfolio', 'I7'): 'iferror((H7-G7)/G7,"")',
        ('SIP Portfolio', 'F7'): 'G7/E7',
        ('SIP Portfolio', 'F8'): 'IFERROR(G8/E8,0)',
        ('StockHistoryData', 'B3'): 'EOMONTH(Today(),-A4)',
        ('StockHistoryData', 'A5'): 'rounddown((today()-B3)/B2,0)',
        ('StockHistoryData', 'B4'): 'sequence(A5,1,B3+B2,B2)',
        ('StockHistoryData', 'C3'): 'if(isblank(B3),"",workday(B3,1))',
        ('StockHistoryData', 'D1'): "'SIP Portfolio'!B1",
        ('StockHistoryData', 'B2'): "'SIP Portfolio'!B3",
        ('StockHistoryData', 'A4'): "'SIP Portfolio'!B2",
    }
    for slot in range(7, 21):
        i = slot - 7
        p, q, c = column(5 + i * 4), column(6 + i * 4), column(7 + i * 4)
        expected['StockHistoryData', f'{p}1'] = f"'SIP Portfolio'!B{slot}"
        expected['StockHistoryData', f'{q}3'] = f'if(isblank({p}3),"",if(isblank($B$1),ROUNDDOWN($D$1/{p}3,0),$B$1))'
        expected['StockHistoryData', f'{c}3'] = f'{p}3*{q}3'
        expected['SIP Portfolio', f'E{slot}'] = f'IF(ISBLANK(B{slot}),"",SUM(StockHistoryData!{q}:{q}))'
        guard = slot - 1 if slot >= 11 else slot
        expected['SIP Portfolio', f'G{slot}'] = (f'sum(StockHistoryData!{c}3:{c}2499)' if slot == 7 else
                                               f'IF(ISBLANK(B{guard}),"",sum(StockHistoryData!{c}3:{c}2499))')
    for (sheet, addr), formula in expected.items():
        actual = cells[sheet]['cells'].get(addr, {}).get('formula')
        if norm(actual) != norm(formula):
            raise ValueError(f'Unsupported workbook formula revision at {sheet}!{addr}: {actual}')
    return len(expected)


def screenshot_checks():
    """Independent transcription of visible summary inputs and ranks, not trade data.

    Screenshot values are rounded whole rupees; comparisons concern ranks only.
    It contains CEMPRO twice and is a different snapshot from the XLSX.
    """
    inputs = [
        ('KRISHANA', 275903, 0, 12), ('GVT&D', 233610, 797148, 4),
        ('TITAN BIOTECH', 274212, 833461, 6), ('SHAILY', 251237, 863648, 3),
        ('WELCORP', 258686, 971730, 2), ('V2RETAIL', 276375, 760232, 8),
        ('TERASOFT', 272650, 570008, 11), ('APOLLO', 273636, 789007, 7),
        ('LUMAXTECH', 258794, 0, 12), ('KWALITY PHARMA', 258593, 1319413, 1),
        ('TDPOWERSYS', 272630, 916727, 5), ('INDOTECH', 240878, 0, 12),
        ('CEMPRO', 267671, 697910, 9), ('CEMPRO', 267671, 697910, 9)]
    rows = rank_rows([{'slot': i + 7, 'stock_code': code, 'displayed_invested': invested,
                       'displayed_current_value': current, 'profit_fraction': (current - invested) / invested,
                       'screenshot_rank': rank} for i, (code, invested, current, rank) in enumerate(inputs)])
    for r in rows:
        r['matches'] = r['rank'] == r['screenshot_rank']
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook', type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument('--output', type=Path, default=ROOT / 'experiments/professor-exact-20261005')
    parser.add_argument('--as-of', type=date.fromisoformat, default=date(2026, 10, 5), help='Explicit TODAY() for a new run; never inferred from cached quotes')
    parser.add_argument('--receipts', type=Path, help='Complete filled price_cells_template.csv; literal worksheet output cells, blank closes allowed')
    parser.add_argument('--quotes', type=Path, help='Complete filled quotes_template.csv, required with --receipts')
    args = parser.parse_args(argv)
    if bool(args.receipts) != bool(args.quotes):
        parser.error('--receipts and --quotes must be supplied together')
    args.output.mkdir(parents=True, exist_ok=True)
    cells, prices, scans = read_workbook(args.workbook)
    formula_checks = validate_layout(cells)
    sip = lambda a: value(cells, 'SIP Portfolio', a)
    hist = lambda a: value(cells, 'StockHistoryData', a)
    amount, months, interval = sip('B1'), int(sip('B2')), int(sip('B3'))
    audit = {'workbook': str(args.workbook), 'sha256': hashlib.sha256(args.workbook.read_bytes()).hexdigest(),
             'scan': scans, 'sheets': cells}
    (args.output / 'formula_audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    results, checks = [], []
    for slot in range(7, 21):
        guard_slot = slot - 1 if slot >= 11 else slot
        r, _ = calculate(prices[slot], sip(f'D{slot}'), amount, hist('B1'), slot == 7,
                         sip(f'B{slot}') is not None, slot == 7 or sip(f'B{guard_slot}') is not None)
        results.append({'slot': slot, 'stock_code': sip(f'B{slot}'), **r})
    rank_rows(results)
    for r in results:
        for col, key in [('E', 'shares_bought'), ('F', 'average_price'), ('G', 'invested'), ('H', 'current_value'), ('I', 'profit_fraction'), ('N', 'rank')]:
            expected, actual = sip(f'{col}{r["slot"]}'), r[key]
            same = (expected in (None, '') and actual == '') or expected == actual
            if number(expected) and number(actual):
                same = math.isclose(expected, actual, rel_tol=1e-12, abs_tol=1e-8)
            checks.append({'cell': f'{col}{r["slot"]}', 'expected': expected, 'actual': actual, 'matches': same})
    write_csv(args.output / 'cached_replay.csv', results)
    write_csv(args.output / 'cached_cell_checks.csv', checks)
    screen_checks = screenshot_checks()
    write_csv(args.output / 'screenshot_rank_checks.csv', screen_checks)
    dates = schedule(args.as_of, months, interval)
    write_csv(args.output / 'schedule.csv', dates)
    templates = [{'slot': slot, 'stock_code': sip(f'B{slot}'), **d, 'returned_date': '', 'close': '',
                  'captured': 'no', 'source': '', 'query_guard': 'first_stock_cost_cell' if slot == 20 else 'schedule_cell'}
                 for slot in range(7, 21) for d in dates]
    if not args.receipts:
        # Never overwrite the user's filled templates when they are input files.
        write_csv(args.output / 'price_cells_template.csv', templates)
        write_csv(args.output / 'quotes_template.csv', [{'slot': slot, 'stock_code': sip(f'B{slot}'), 'current_quote': '', 'captured': 'no', 'source': ''} for slot in range(7, 21)])
    # A fully specified arithmetic example, explicitly synthetic, including a rank tie.
    worked = []
    for label, ps, quote in [('A', {3: 100, 4: 120}, 150), ('B', {3: 100, 4: 120}, 150), ('C', {3: 100, 4: 100}, 100)]:
        row, _ = calculate(ps, quote)
        worked.append({'example': label, **row})
    write_csv(args.output / 'synthetic_worked_examples.csv', rank_rows(worked))
    receipt_results = None
    if args.receipts:
        receipt_data = list(csv.DictReader(args.receipts.open(encoding='utf-8-sig')))
        quote_data = list(csv.DictReader(args.quotes.open(encoding='utf-8-sig')))
        expected_keys = {(t['slot'], t['history_row']): t for t in templates}
        observed = {}
        for r in receipt_data:
            key = int(r['slot']), int(r['history_row'])
            if key in observed or key not in expected_keys:
                raise ValueError(f'Duplicate/unexpected receipt {key}')
            t = expected_keys[key]
            if r['captured'].lower() != 'yes' or not r['source'].strip():
                raise ValueError(f'Receipt not captured/documented: {key}')
            if any(str(r[k]) != str(t[k]) for k in ('stock_code', 'scheduled_date', 'workday_date', 'request_start', 'request_num_days', 'query_guard')):
                raise ValueError(f'Receipt does not match requested formula/date: {key}')
            observed[key] = parse_cell(r['close'])
            if number(observed[key]) and not r['returned_date']:
                raise ValueError(f'Missing returned date: {key}')
            if r['returned_date']:
                date.fromisoformat(r['returned_date'])
        if set(observed) != set(expected_keys):
            raise ValueError('Every requested worksheet cell must be captured, including blanks/errors')
        quotes = {}
        for r in quote_data:
            slot = int(r['slot'])
            if slot in quotes or slot not in range(7, 21) or r['stock_code'] != sip(f'B{slot}') or r['captured'].lower() != 'yes' or not r['source'].strip():
                raise ValueError('Invalid/duplicate/undocumented quote')
            quotes[slot] = parse_cell(r['current_quote'])
        if set(quotes) != set(range(7, 21)):
            raise ValueError('All 14 quote cells required')
        receipt_results, trades = [], []
        for slot in range(7, 21):
            guard_slot = slot - 1 if slot >= 11 else slot
            r, ts = calculate({row: p for (s, row), p in observed.items() if s == slot}, quotes[slot], amount, hist('B1'), slot == 7,
                              sip(f'B{slot}') is not None, slot == 7 or sip(f'B{guard_slot}') is not None)
            receipt_results.append({'slot': slot, 'stock_code': sip(f'B{slot}'), **r})
            trades.extend({'slot': slot, 'stock_code': sip(f'B{slot}'), **t} for t in ts)
        write_csv(args.output / 'receipt_rankings.csv', rank_rows(receipt_results))
        write_csv(args.output / 'receipt_trade_ledger.csv', trades)
    verification = {'cached_cells_compared': len(checks), 'cached_cells_matched': sum(c['matches'] for c in checks),
                    'source_formula_definitions_checked': formula_checks,
                    'screenshot_ranks_compared': len(screen_checks), 'screenshot_ranks_matched': sum(r['matches'] for r in screen_checks),
                    'cached_valid_ranks': sum(number(r['rank']) for r in results),
                    'as_of_for_new_schedule': args.as_of.isoformat(), 'new_schedule_rows_per_stock': len(dates),
                    'receipt_ranking_computed': receipt_results is not None,
                    'live_googlefinance_validated': False, 'model_imports': [],
                    'source_workbook_sha256': audit['sha256']}
    if args.receipts:
        verification['receipt_inputs'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.receipts, args.quotes)}
    (args.output / 'verification.json').write_text(json.dumps(verification, indent=2), encoding='utf-8')
    print(json.dumps(verification, indent=2))
    if not all(c['matches'] for c in checks) or not all(r['matches'] for r in screen_checks):
        raise SystemExit('Cached replay differs: inspect cached_cell_checks.csv')


if __name__ == '__main__':
    main()
