"""Hash-validated frozen global selection for the tested base SIP profile."""
import csv
import hashlib
import json
from pathlib import Path
from stock_ranker.runtime import PROJECT_ROOT
from stock_ranker.personalized_product import PersonalizationError

DEFAULT_PACKAGE = PROJECT_ROOT / 'research/runtime/global-rank-correction-20261106'


class GlobalChampionSelection:
    def __init__(self, package=None):
        self.package = Path(package or DEFAULT_PACKAGE)
        self.manifest = json.loads((self.package / 'manifest.json').read_text(encoding='utf-8'))
        if self.manifest['model_id'] != 'global_rank_correction_20261106':
            raise PersonalizationError('Unexpected global champion package')
        for name, expected in self.manifest['files'].items():
            path = self.package / name
            if path.parent != self.package or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise PersonalizationError('Global champion package integrity mismatch')
        with (self.package / 'ranking.csv').open(encoding='utf-8', newline='') as file:
            self.rows = list(csv.DictReader(file))
        if len(self.rows) != self.manifest['eligible_stocks'] or len({r['isin'] for r in self.rows}) != len(self.rows):
            raise PersonalizationError('Global champion universe mismatch')
        for index, row in enumerate(self.rows, 1):
            row['global_champion_rank'] = int(row['global_champion_rank'])
            row['global_champion_score'] = float(row['global_champion_score'])
            if row['global_champion_rank'] != index or row['decision_date'] != self.manifest['as_of_date']:
                raise PersonalizationError('Global champion rank or snapshot mismatch')

    def selection(self, profile):
        expected = self.manifest['base_profile']
        matches = (profile.amount == expected['amount']
                   and profile.lookback_months == expected['lookback_months']
                   and profile.interval_days == expected['interval_days']
                   and abs(profile.target_cagr - expected['target_cagr_percent']/100) < 1e-12
                   and profile.horizon_months == expected['horizon_months'])
        common = dict(model_id=self.manifest['model_id'], model_name=self.manifest['model_name'],
                      as_of_date=self.manifest['as_of_date'], eligible_stocks=len(self.rows),
                      profile_supported=matches, fresh_daily_inputs=False)
        if not matches:
            return dict(**common, available=False, rows=[],
                        note='Global selection supports ₹7,500 every 30 days, 36-month lookback, 20% target and 12-month horizon. Sector ranks support your submitted profile.')
        return dict(**common, available=True, rows=self.rows[:20],
                    note=f"Saved {self.manifest['as_of_date']} snapshot. Global Top-20 selected from {len(self.rows):,} stocks with complete professor-factor and residual-history inputs. Research comparison, with current prices and execution still requiring verification.")
