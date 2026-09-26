"""One entry point for frozen prediction verification and prospective checkpoints."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from stock_research.personalized_shadow import load_freeze, evaluate

DEFAULT = ROOT / 'research/freezes/personalized-d499580'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['verify', 'reproduce', 'init-evidence', 'evaluate', 'schedule'])
    parser.add_argument('--freeze', type=Path, default=DEFAULT)
    parser.add_argument('--months', type=int, choices=[3, 6, 12])
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    config, selections, manifest = load_freeze(args.freeze)
    if args.command in ['verify', 'schedule']:
        print(json.dumps({'fingerprint': manifest['fingerprint'], 'challenger_commit': config['challenger_commit'], 'prospective_origin': config['prospective_origin'], 'checkpoints': config['checkpoints'], 'selections': len(selections)}, indent=2))
    elif args.command == 'reproduce':
        import numpy as np
        import pandas as pd
        from lightgbm import Booster
        features = pd.read_csv(args.freeze / 'features.csv.gz', low_memory=False)
        ranks = pd.read_csv(args.freeze / 'rankings.csv.gz', low_memory=False)
        valid = features.enhanced_carry_xirr_score.notna()
        recovered = features.loc[valid, ['profile_name', 'isin']].copy()
        recovered['prediction'] = Booster(model_file=str(args.freeze / 'lambdarank.txt')).predict(features.loc[valid, config['features']])
        joined = ranks.merge(recovered, on=['profile_name', 'isin'], how='left', validate='one_to_one')
        if not np.allclose(joined.lightgbm_lambdarank_score, joined.prediction, rtol=0, atol=1e-12, equal_nan=True):
            raise ValueError('Frozen model inference mismatch')
        votes = ranks.groupby('profile_name')[['enhanced_goal_score', 'lightgbm_lambdarank_score']].rank(pct=True)
        score = votes.iloc[:, 0] * .67 + votes.iloc[:, 1] * .33
        if not np.allclose(score, ranks.selected_ensemble_score, rtol=0, atol=1e-12, equal_nan=True):
            raise ValueError('Frozen ensemble mismatch')
        print('PASS: serialized model inference and 67/33 ensemble reproduce original predictions; no fitting performed.')
    elif args.command == 'init-evidence':
        import pandas as pd
        if args.evidence is None:
            parser.error('--evidence required')
        args.evidence.mkdir(parents=True, exist_ok=False)
        (args.evidence / 'sources').mkdir()
        pd.DataFrame(columns=['isin', 'date', 'close', 'source_url', 'source_sha256']).to_csv(args.evidence / 'prices.csv', index=False)
        pd.DataFrame(columns=['event_id', 'isin', 'ex_date', 'type', 'numerator', 'denominator', 'child_isin', 'cash_per_share', 'payment_date', 'fraction_cash_per_share', 'fraction_payment_date', 'source_url', 'source_sha256']).to_csv(args.evidence / 'actions.csv', index=False)
        ids = sorted(selections['isin'].unique())
        pd.DataFrame({'isin': ids, 'through_date': '', 'price_basis': 'OBSERVED_NOMINAL_CLOSE', 'action_status': 'PENDING', 'source_url': '', 'source_sha256': ''}).to_csv(args.evidence / 'coverage.csv', index=False)
        print(f'Created templates for {len(ids)} selected identities. Include resulting securities when actions create them. Preserve raw source files under sources/.')
    else:
        if args.months is None or args.evidence is None or args.output is None:
            parser.error('--months, --evidence and --output required')
        result = evaluate(args.freeze, args.evidence, args.months, args.output)
        print(json.dumps({'checkpoint_months': result['checkpoint_months'], 'endpoint': result['endpoint'], 'complete_security_profiles': result['complete_security_profiles'], 'security_profiles': result['security_profiles']}, indent=2))


if __name__ == '__main__':
    main()
