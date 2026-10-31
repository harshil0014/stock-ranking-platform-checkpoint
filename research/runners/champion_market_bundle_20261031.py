"""Select compact public evidence and create the user's standalone research bundle."""
from pathlib import Path
import json,hashlib,zipfile,shutil,datetime
import champion_market_common_20261031 as c
DEST=Path('C:/Users/Harshil/Documents/Codex/2026-10-31/you/outputs')

def public_paths():
 names=['README.md','protocol.json','panel_receipt.json','score_registry.json','sequence_data_receipt.json','sequence_implementation_freeze.json','tabular_environment.json','sequence_environment.json','index_acquisition_receipts.json','bse_acquisition_receipt.json','bse_tri_acquisition_receipt.json','iima_acquisition_receipt.json','index_series_validation.json','index_launch_source_notes.json','index_execution_failures.json','index_sip_summary.csv','index_live_only_summary.csv','index_sip_cashflow_results.csv.gz','portfolio_cashflow_results.csv.gz','portfolio_paired_comparisons.csv','portfolio_summary.csv','portfolio_scope.json','portfolio_failures.json','validation_receipt.json','runtime_summary.csv','fit_registry.csv','test_receipt.json']
 names+=['sequence_adapter_validation.json','portfolio_anchor_path_coverage_before_outcomes.json'];paths=[c.OUT/n for n in names]
 for tier in ['full','sequence']:
  folder=c.OUT/tier
  paths.extend(p for p in folder.glob('*') if p.is_file() and (p.suffix in ['.json','.csv']) and p.name not in ['scored_panel.pkl.gz'])
 for family in ['tabular','sequence']:
  paths.extend((c.OUT/family).glob('*_audit.json'));paths.extend((c.OUT/family).glob('*_receipt.json'));paths.extend((c.OUT/family).glob('*_complete.json'))
 paths.extend((c.OUT/'inference').glob('*_replay.json'));paths.append(c.OUT/'inference/replay_audit.json');paths.extend((c.OUT/'figures').glob('*'))
 missing=[str(p) for p in paths if not p.exists()]
 if missing:raise RuntimeError('Missing required completed evidence '+str(missing))
 return sorted(set(paths))

def main():
 paths=public_paths();records=[dict(path=str(p.relative_to(c.ROOT)).replace('\\','/'),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
 private=[]
 for family in ['tabular','sequence','inference']:
  for p in (c.OUT/family).glob('*'):
   if p.is_file() and p not in paths:private.append(dict(path=str(p.relative_to(c.ROOT)).replace('\\','/'),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
 c.save('evidence_manifest.json',dict(generated_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),public=records,local_model_and_prediction_snapshots=private,raw_data_status='Provider price paths, official raw index series and IIMA factor file remain local; acquisition receipts and source hashes are public',production_changed=False))
 paths.append(c.OUT/'evidence_manifest.json');c.save('public_bundle_paths.json',[str(p.relative_to(c.ROOT)).replace('\\','/') for p in paths]);paths.append(c.OUT/'public_bundle_paths.json')
 code=list((c.ROOT/'research/runners').glob('champion_market*20261031.py'))+[c.ROOT/'research/runners/market_index_acquisition_20261031.py',c.ROOT/'research/protocols/champion_vs_market_20261031.json',c.ROOT/'research/protocols/champion_vs_market_implementation_20261031.md',c.ROOT/'research/reports/champion_vs_market_20261031.md',c.ROOT/'research/reports/champion_vs_market_literature_20261031.md',c.ROOT/'tests/test_champion_market_20261031.py']+list((c.ROOT/'research/literature/20261031').rglob('*'))
 DEST.mkdir(parents=True,exist_ok=True);zipdest=DEST/'champion-vs-market-20261031-evidence.zip'
 with zipfile.ZipFile(zipdest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
  for p in paths+code:
   if p.is_file() and '__pycache__' not in str(p):archive.write(p,str(p.relative_to(c.ROOT)))
 public='https://github.com/harshil0014/stock-ranking-platform-checkpoint/blob/main/'
 for name in ['champion_vs_market_20261031.md','champion_vs_market_literature_20261031.md']:
  content=(c.ROOT/'research/reports'/name).read_text(encoding='utf-8').replace('](champion_vs_market_literature_20261031.md)',']('+public+'research/reports/champion_vs_market_literature_20261031.md)').replace('](../literature/20261031/REFERENCES.md)',']('+public+'research/literature/20261031/REFERENCES.md)').replace('../../experiments/champion-vs-market-20261031/figures/','champion-market-');(DEST/name).write_text(content,encoding='utf-8')
 for p in (c.OUT/'figures').glob('*.png'):shutil.copy2(p,DEST/('champion-market-'+p.name))
 (DEST/'champion-vs-market-20261031-evidence.sha256').write_text(hashlib.sha256(zipdest.read_bytes()).hexdigest()+'  '+zipdest.name+'\n',encoding='utf-8');print('BUNDLED',len(paths),'public evidence files',zipdest.stat().st_size,flush=True)
if __name__=='__main__':main()
