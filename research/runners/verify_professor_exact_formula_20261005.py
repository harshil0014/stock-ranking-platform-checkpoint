"""Exercise the complete CSV input path with explicitly synthetic price cells."""
import csv
import hashlib
import json
from pathlib import Path

from professor_exact_formula_20261005 import ROOT, main, write_csv


def run():
    root = ROOT / 'experiments/professor-exact-20261005'
    out = root / 'synthetic_receipt_run'
    out.mkdir(exist_ok=True)
    prices = list(csv.DictReader((root / 'price_cells_template.csv').open(encoding='utf-8-sig')))
    quotes = list(csv.DictReader((root / 'quotes_template.csv').open(encoding='utf-8-sig')))
    for row in prices:
        row.update(close=100 + int(row['slot']) - 7, returned_date=row['request_start'],
                   captured='yes', source='SYNTHETIC integration fixture; not market data')
    for row in quotes:
        row.update(current_quote=150, captured='yes', source='SYNTHETIC integration fixture; not market data')
    price_path, quote_path = out / 'price_cells_template.csv', out / 'quotes_template.csv'
    write_csv(price_path, prices)
    write_csv(quote_path, quotes)
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (price_path, quote_path)]
    main(['--output', str(out), '--receipts', str(price_path), '--quotes', str(quote_path)])
    after = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (price_path, quote_path)]
    assert before == after, 'Input files overwritten'
    ranked = list(csv.DictReader((out / 'receipt_rankings.csv').open(encoding='utf-8-sig')))
    assert [int(r['rank']) for r in ranked] == list(range(1, 15))
    for r in ranked:
        p = 100 + int(r['slot']) - 7
        assert abs(float(r['profit_fraction']) - (150 / p - 1)) < 1e-12
        assert float(r['shares_bought']) == 36 * (7500 // p)
    # Exercise rejection rather than silently accepting an incomplete history.
    prices[0]['captured'] = 'no'
    invalid = out / 'invalid_receipt_fixture.csv'
    write_csv(invalid, prices)
    try:
        main(['--output', str(out / 'rejected_input_run'), '--receipts', str(invalid), '--quotes', str(quote_path)])
    except ValueError as exc:
        assert 'not captured' in str(exc)
    else:
        raise AssertionError('Incomplete capture was accepted')
    result = {'synthetic_only': True, 'ranks_checked': 14, 'profit_formulas_checked': 14,
              'share_totals_checked': 14, 'input_files_preserved': before == after,
              'uncaptured_input_rejected': True}
    (root / 'integration_verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    run()
