"""Package the refined V17 snapshot for read-only website inference; no fitting."""
from pathlib import Path
import sys, json, shutil, hashlib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'research/runners')]
import personalized_v15_20261003 as source

def build():
    out = ROOT/'research/runtime/personalized-v17'
    out.mkdir(parents=True, exist_ok=True)
    refined = ROOT/'experiments/v17-refinement-20261004'
    original = ROOT/'experiments/personalized-v17-20261003'
    # The evidence loader writes an acquisition receipt: direct it exclusively
    # into this new package, never into the frozen research directories.
    source.OUT = out
    source.ACTION = refined/'actions/normalized_ledger.csv.gz'
    source.SPLITS = refined/'provider_splits'
    facts = pd.read_csv(source.V7, low_memory=False)
    pack = out/'history.npz'
    if not pack.exists():
        book = source.load_current_book(facts)
        names, offsets, arrays = [], [0], [[] for _ in range(5)]
        for identity, values in sorted(book.arrays.items()):
            names.append(identity)
            for target, value in zip(arrays, values): target.append(value)
            offsets.append(offsets[-1]+len(values[0]))
        np.savez_compressed(pack, identities=np.asarray(names), offsets=np.asarray(offsets),
            dates=np.concatenate(arrays[0]).astype('datetime64[D]').astype(np.int32),
            **{name:np.concatenate(values) for name,values in zip(['raw','adjusted','nominal','factor'],arrays[1:])},
            errors_json=np.frombuffer(json.dumps(book.errors).encode(),dtype=np.uint8))
        # Preserve the loader's resolved resulting-equity mechanics as used in research.
        pd.concat(book.actions.values(),ignore_index=True).to_csv(out/'actions.csv.gz',index=False)
        book.resulting_terms.to_csv(out/'terms.csv',index=False)
    reviewed = ROOT/'experiments/closing-high-recovery-20261004'
    reviewed_names = ['peak_current.csv.gz','peak_features_reviewed.csv.gz','peak_history.npz',
                      'peak_actions.csv.gz','history_validation.json']
    reviewed_copies = {}
    if any((reviewed/name).exists() for name in reviewed_names):
        receipt=json.loads((reviewed/'history_build_manifest.json').read_text())
        for name in reviewed_names:
            path=reviewed/name
            if hashlib.sha256(path.read_bytes()).hexdigest()!=receipt['files'][name]:
                raise ValueError('Reviewed history integrity check failed: '+name)
            reviewed_copies[name]=path
    elif any((out/name).exists() for name in reviewed_names):
        raise ValueError('Reviewed sources are absent; refusing to reuse stale overlay files')
    copies = {
        'current.csv.gz':refined/'final_current_rankings.csv.gz',
        'reference.csv.gz':original/'current_rankings.csv.gz',
        'peak_features.csv.gz':ROOT/'experiments/v17-peak-activity-20261004/dated_features.csv.gz',
        'peak_selection.json':ROOT/'experiments/v17-peak-confirmation-20261004/selection_lock.json',
        'peak_review.csv':ROOT/'research/reports/top100-human-review-20261004/company_due_diligence.csv',
        **reviewed_copies,
        'facts.csv.gz':source.V7,
        'definition.json':refined/'model_definition.json',
        'champion.txt':source.FREEZE/'lambdarank.txt',
        'monotone.txt':original/'model_current_monotone.txt',
        'regime.txt':refined/'model_refined_current_regime.txt',
        **{f'partner{n}.txt':original/f'model_current_partner_look{n}.txt' for n in [12,36,60]},
        **{f'bag{n}.txt':refined/f'model_refined_current_bag60_{n}.txt' for n in range(20261003,20261010)},
    }
    for name,path in copies.items(): shutil.copyfile(path,out/name)
    manifest = {'model_id':'personalized_v17_refined','as_of_date':'2026-10-03',
        'action_checked_through':'2026-10-04','universe':4436,
        'source_files':{name:str(path.relative_to(ROOT)) for name,path in copies.items()},
        'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name!='manifest.json'}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'package':str(out),'files':len(manifest['files'])}),flush=True)

if __name__=='__main__': build()
