"""Archive only explicit reproduction inputs, with deterministic ZIP entries.

Large, unused exploratory PDF collections are not needed for reproducing the
frozen feature matrix/model. Preserved normalized terms retain their provenance.
"""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def build(output):
    import pandas as pd
    output.mkdir(parents=True, exist_ok=False)
    paths = set()
    def add(path):
        path = path.resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('Reproduction input outside workspace')
        if path.is_dir():
            paths.update(p for p in path.rglob('*') if p.is_file())
        elif path.is_file():
            paths.add(path)
        else:
            raise FileNotFoundError(path)
    for relative in ['data/live_market/history_cache', 'external_research_pack/ownership_history_20260925',
                     'external_research_pack/corporate_actions', 'external_research_pack/historical_sectors',
                     'external_research_pack/handoff_for_codex', 'external_research_pack/residual_recovery_20260925',
                     'experiments/personalized-final-tournament/checkpoints-03',
                     'experiments/personalized-final-tournament/build-04',
                     'experiments/personalized-official-action-freeze/build-06',
                     'experiments/personalized-official-action-freeze/build-06-rebuild-check',
                     'research/freezes/personalized-d499580', 'research/data/ownership-recovery-20260925']:
        add(ROOT / relative)
    for layer, key in [('company_facts', 'snapshot_path'), ('live_market', 'bundle_path')]:
        state = ROOT / 'data' / layer / 'accepted_state.json'
        add(state);add(state.parent / json.loads(state.read_text())[key])
    audit = pd.read_csv(ROOT / 'research/data/ownership-recovery-20260925/history_recovery_audit.csv')
    for source in audit.source.dropna().unique():
        add(ROOT / source)
    for batch in (ROOT / 'external_research_pack/event_terms_round2').glob('batch_*'):
        for path in batch.iterdir():
            if path.is_file() and path.suffix.lower() in {'.csv','.json','.md','.txt'}:
                add(path)
    # Large panels used by the final diagnostic, plus the published test record.
    add(ROOT / 'experiments/personalized-final-tournament/build-02/validation_predictions.csv.gz')
    add(ROOT / 'experiments/ownership-final-tests.log')
    inventory = [{'path': p.relative_to(ROOT).as_posix(), 'size': p.stat().st_size, 'sha256': digest(p)} for p in sorted(paths)]
    part, size, archive = 0, 0, None
    try:
        for item in inventory:
            if archive is None or size + item['size'] > 450 * 1024 * 1024:
                if archive:
                    archive.close()
                part += 1;size = 0
                archive = zipfile.ZipFile(output / f'reproduction-inputs-{part:02d}.zip', 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True)
            info = zipfile.ZipInfo(item['path'], date_time=(2026,9,26,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            with (ROOT / item['path']).open('rb') as source, archive.open(info, 'w', force_zip64=True) as target:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    target.write(chunk)
            size += item['size']
    finally:
        if archive:
            archive.close()
    # Verify the actual archived bytes, not just the files that preceded packing.
    expected = {i['path']: i for i in inventory}
    restored = set()
    for path in sorted(output.glob('*.zip')):
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                h = hashlib.sha256()
                with z.open(name) as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b''):
                        h.update(chunk)
                if h.hexdigest() != expected[name]['sha256']:
                    raise ValueError('Archive verification failed: ' + name)
                restored.add(name)
    if restored != set(expected):
        raise ValueError('Incomplete archive')
    manifest = {'challenger_commit':'d4995807163bef1ec4b297179e6c54a59c71f390', 'files':inventory,
                'archives':[{'name':p.name,'size':p.stat().st_size,'sha256':digest(p)} for p in sorted(output.glob('*.zip'))],
                'scope':'Frozen feature/model inference, original training checkpoints, price histories/overlays, accepted fact/market snapshots, normalized and core corporate-action evidence. Unused exploratory PDF collections excluded.',
                'archive_bytes_verified':True}
    (output / 'input-backup-manifest.json').write_bytes((json.dumps(manifest, indent=2, sort_keys=True)+'\n').encode())
    print(json.dumps({'files':len(inventory),'uncompressed_bytes':sum(i['size'] for i in inventory),'archives':manifest['archives']},indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);build(p.parse_args().output)
