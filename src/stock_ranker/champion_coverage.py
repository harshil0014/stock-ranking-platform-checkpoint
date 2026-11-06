"""Current vendor evidence and explicitly separated full-universe fallback ranks.

This adapter never feeds current financial vintages into the frozen trained model.
The private, hash-checked package is produced by build_champion_coverage_20261106.
"""
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import os
from pathlib import Path

from stock_ranker.personalized_product import PersonalizationError
from stock_ranker.runtime import PROJECT_ROOT

DEFAULT_PACKAGE = PROJECT_ROOT / 'work/champion-coverage-20261106/runtime'


class ChampionCoverage:
    def __init__(self, package=None):
        self.package = Path(package or os.environ.get('STOCK_RANKER_CHAMPION_COVERAGE', DEFAULT_PACKAGE))
        self.manifest = json.loads((self.package / 'manifest.json').read_text(encoding='utf-8'))
        if self.manifest.get('policy_id') != 'champion_coverage_20261106':
            raise PersonalizationError('Unexpected champion coverage policy')
        for name, digest in self.manifest['files'].items():
            if Path(name).name != name or hashlib.sha256((self.package / name).read_bytes()).hexdigest() != digest:
                raise PersonalizationError('Champion coverage integrity mismatch: ' + name)
        with gzip.open(self.package / 'universe.json.gz', 'rt', encoding='utf-8') as stream:
            self.records = json.load(stream)
        if len(self.records) != self.manifest['total_stocks'] or len({r['isin'] for r in self.records}) != len(self.records):
            raise PersonalizationError('Champion coverage identities are incomplete or duplicated')
        self.by_isin = {r['isin']: r for r in self.records}
        self.aliases = defaultdict(set)
        for row in self.records:
            current_name=row['current_fundamentals'].get('company_name')
            for alias in row['aliases'] + ([current_name] if current_name else []):
                self.aliases[alias.upper()].add(row['isin'])

    def metadata(self):
        return {k: self.manifest[k] for k in (
            'policy_id', 'total_stocks', 'legacy_stocks', 'additional_stocks',
            'fresh_source_matches', 'source_as_of_date', 'source_observed_range',
            'different_isin_current_only_matches', 'excluded_without_exchange_code')}

    def apply(self, result, global_model_rows, *, securities=None):
        rows = result['rows']
        if {r['isin'] for r in rows} != {r['isin'] for r in self.records if r['legacy']}:
            raise PersonalizationError('Coverage package does not match the frozen champion universe')
        global_map = {r['isin']: r for r in global_model_rows}
        for row in rows:
            current = self.by_isin[row['isin']]
            row.update(current_fundamentals=current['current_fundamentals'],
                       screener_source_isin=current['source_isin'],
                       identity_match_method=current['match_method'],
                       identity_history_bridge_verified=False,
                       financial_observed_at=current['observed_at'],
                       current_data_available=bool(current['source_isin']),
                       current_data_as_of_date=self.manifest['source_as_of_date'] if current['source_isin'] else None,
                       ranking_as_of_date=result['as_of_date'],
                       coverage_tier='TRAINED_GLOBAL' if row['isin'] in global_map else 'FROZEN_SECTOR',
                       coverage_score_kind='FROZEN_CHAMPION',
                       coverage_fallback_score=current['fallback_score'])
            row['search_aliases'] += ' ' + ' '.join(current['aliases']) + ' ' + (current['current_fundamentals'].get('company_name') or '')
            if current['different_isin']:
                row['review_flags'] = list(row.get('review_flags') or []) + [
                    'Current exchange-code match has a changed ISIN; historical continuity is unverified.']
                row['execution_available'] = False
                row['execution_blocker'] = 'Changed ISIN: current-to-historical execution bridge is unverified.'
            g = global_map.get(row['isin'])
            row['global_model_rank'] = g['global_champion_rank'] if g else None
            row['global_model_score'] = g['global_champion_score'] if g else None

        for source in self.records:
            if source['legacy']:
                continue
            score = source['fallback_score']
            row = dict(isin=source['isin'], ticker=source['ticker'], company=source['company'],
                sector=source['sector'], search_aliases=' '.join(source['aliases']), requested_code=None,
                sector_classification_source='Screener current industry group',
                sector_classification_method='CURRENT_VENDOR_GROUP', sector_classification_confidence='VENDOR',
                personalized_available=score is not None, personalized_score=score,
                personalized_rank=None, personalized_sector_rank=None, personalized_sector_peer_count=0,
                sector_security_count=0, result_type='SCREENER_MOMENTUM_FALLBACK' if score is not None else 'INSUFFICIENT_RANKING_EVIDENCE',
                status='CURRENT_REFERENCE_ONLY', execution_status='HISTORY_UNAVAILABLE', execution_available=False,
                blocker='Current-data fallback; trained champion history, high dates and SIP outcomes are unavailable.',
                execution_blocker='No verified daily execution/corporate-action history for this added security.',
                evidence_confidence=0, sector_scoring_fallback=True,
                fallback_available=True, coverage_tier='SCREENER_FALLBACK' if score is not None else 'COVERAGE_ONLY',
                coverage_score_kind='UNVALIDATED_MOMENTUM_QUALITY_PROXY' if score is not None else 'NO_SCORE',
                coverage_fallback_score=score, fallback_factor_coverage=source['fallback_factor_coverage'],
                current_fundamentals=source['current_fundamentals'], current_data_available=True,
                current_data_as_of_date=self.manifest['source_as_of_date'],
                ranking_as_of_date=self.manifest['source_as_of_date'],
                financial_observed_at=source['observed_at'], screener_source_isin=source['source_isin'],
                identity_match_method='NEW_SOURCE_ISIN', identity_history_bridge_verified=False,
                global_model_rank=None, global_model_score=None, review_flags=[])
            for key in ('xirr','target_attainment','target_shortfall','execution_count','shares_bought',
                        'amount_contributed','amount_invested','residual_cash','cash_utilization','unaffordable_rate',
                        'terminal_price','terminal_price_date','days_since_recorded_high','distance_from_recorded_high',
                        'professor_whole_share_score','sip_profit_adjustment','baseline_score','baseline_sector_rank'):
                row[key] = None
            rows.append(row)

        # Never compare a vendor proxy numerically to the trained model's score.
        # Keep the original global order first, then frozen sector evidence, then
        # new proxies; missing-evidence rows receive a display position only.
        order = {'TRAINED_GLOBAL': 0, 'FROZEN_SECTOR': 1, 'SCREENER_FALLBACK': 2, 'COVERAGE_ONLY': 3}
        def key(row):
            return (order[row['coverage_tier']], row.get('global_model_rank') or 10**9,
                    -(row.get('personalized_score') or 0), row['isin'])
        for position, row in enumerate(sorted(rows, key=key), 1):
            row['coverage_global_position'] = position
        sectors = defaultdict(list)
        for row in rows:
            sectors[row['sector']].append(row)
        for members in sectors.values():
            old = [r for r in members if r['coverage_tier'] in ('TRAINED_GLOBAL','FROZEN_SECTOR')]
            new = sorted((r for r in members if r['coverage_tier'] == 'SCREENER_FALLBACK'), key=lambda r: (-r['personalized_score'],r['isin']))
            # Competition ranks skip all tied occupants, including a tie at
            # the tail of the frozen group.
            tail = len(old)
            for offset, row in enumerate(new, 1):
                row['personalized_sector_rank'] = tail + offset
            for row in members:
                row['sector_security_count'] = len(members)
                row['personalized_sector_peer_count'] = len(old) + len(new)
        rows.sort(key=lambda r: (r['sector'], r['personalized_sector_rank'] or 10**9, r['isin']))
        if securities:
            requested = {}
            for raw in securities:
                found = self.aliases.get(str(raw).strip().upper(), set())
                if len(found) != 1:
                    raise PersonalizationError('Unknown or ambiguous security: ' + str(raw))
                requested[next(iter(found))] = str(raw)
            for row in rows:
                row['requested_code'] = requested.get(row['isin'])
        counts = dict(Counter(r['coverage_tier'] for r in rows))
        result.update(coverage={**self.metadata(), 'tiers': counts, 'fresh_daily_inputs': False},
            personalized_count=sum(r['personalized_available'] for r in rows),
            fallback_count=counts.get('SCREENER_FALLBACK',0)+counts.get('COVERAGE_ONLY',0),
            sector_count=len(sectors), total_stocks=len(rows), row_count=len(rows),
            evidence_fallback_count=result.get('evidence_fallback_count',0)+self.manifest['additional_stocks'],
            sector_scoring_note=f"All {len(rows):,} accepted NSE/BSE identities covered. Existing sector order is preserved; new Screener proxies follow frozen champion stocks within each sector. Proxy scores use a separate scale. Rows with no signal have a display position only.")
        return result
