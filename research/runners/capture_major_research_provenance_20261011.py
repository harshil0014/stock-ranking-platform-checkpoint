"""Capture local environment and stage artifact provenance without secrets."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/sector-specialist-ensemble-20261011'
sys.path.insert(0,str(ROOT/'experiments/sector_ensemble_dependencies_20261011'))


def main():
    packages={}
    for name in ['numpy','pandas','scipy','scikit-learn','lightgbm','torch','tabm','rtdl-num-embeddings','interpret-core','psutil','pytest']:
        try:
            dist=importlib.metadata.distribution(name)
            packages[name]=dict(version=dist.version,location=str(dist.locate_file('')))
        except importlib.metadata.PackageNotFoundError:
            packages[name]=dict(available=False)
    files=[]
    for folder in ['research/runners','tests']:
        for path in (ROOT/folder).glob('*.py'):
            if any(token in path.name for token in ['specialist','execution_activity','major_research']):
                files.append(path)
    for folder in ['sector-specialist-ensemble-20261011','sector-execution-specialist-20261011']:
        directory=ROOT/'experiments'/folder
        for name in ['protocol.json','combination_protocol.json','locked_finalists.json','current_activity_repair.json','replay_verification.json','evaluation_verification.json']:
            path=directory/name
            if path.exists():
                files.append(path)
    manifest={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    report=dict(python=sys.version,executable=sys.executable,platform=platform.platform(),packages=packages,sha256=manifest,
                scope='Snapshot at capture time; missing pending stage files are not completion evidence. No credentials or environment variables collected.')
    (OUT/'resume_provenance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(packages=packages,hashed_files=len(files)),indent=2),flush=True)


if __name__=='__main__':
    main()
