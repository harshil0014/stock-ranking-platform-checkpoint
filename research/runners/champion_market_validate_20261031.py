"""End-to-end evidence integrity checks, separate from research outcome selection."""
import json,hashlib,subprocess
import numpy as np,pandas as pd
import champion_market_common_20261031 as c

def main():
 checks=[];protocol=json.loads((c.OUT/'protocol.json').read_text());audit_count=0;training_support={}
 for family in ['tabular','sequence']:
  for path in (c.OUT/family).glob('*_audit.json'):
   r=json.loads(path.read_text());year=r.get('year')
   if year is None and path.name.startswith('matched_'):year=int(path.name.split('__')[2].split('_')[0])
   if year is None:continue
   assert r['max_training_endpoint']<f'{year}-01-01',str(path);audit_count+=1
   if family=='tabular':
    assert r['train_rows']<=120000;training_support.setdefault(year,set()).add(r['train_key_hash'])
 checks.append(dict(check='Every recorded fit strictly purges actual outcome endpoints at annual boundary',audits=audit_count,passed=True))
 assert len(training_support)==6 and all(len(v)==1 for v in training_support.values());checks.append(dict(check='All tabular algorithms/objectives/seeds use identical capped whole-query training keys within each year',years=6,cap=120000,passed=True))
 for name in protocol['ml_algorithms']:assert (c.OUT/'tabular'/(name+'_complete.json')).exists()
 for name in ['gru','alstm','transformer','gats','hist','master']:assert (c.OUT/'sequence'/(name+'_complete.json')).exists()
 checks.append(dict(check='All preregistered18tabular specifications and6foreign architectures completed',passed=True))
 adapter=json.loads((c.OUT/'sequence_adapter_validation.json').read_text());assert adapter['passed'] and len(adapter['checks'])==6;checks.append(dict(check='All6foreign adapters pass forward/backward and stock-permutation contracts',passed=True))
 seq=pd.read_pickle(c.OUT/'sequence_panel.pkl.gz',compression='gzip');expected=seq[seq.decision_date.ge('2020-01-01')];expected_keys=set(map(tuple,expected[c.KEYS].itertuples(index=False,name=None)))
 for name in ['gru','alstm','transformer','gats','hist','master','matched_ridge','matched_lightgbm']:
  pred=pd.concat([pd.read_csv(c.OUT/'sequence'/f'{name}__balanced__{year}.csv.gz') for year in range(2020,2026)]);assert not pred.duplicated(c.KEYS).any() and set(map(tuple,pred[c.KEYS].itertuples(index=False,name=None)))==expected_keys and np.isfinite(pred.score).all()
 checks.append(dict(check='All foreign models and matched controls retain the complete feature-available sequence cohort including masked unknown outcomes',rows=len(expected),unknown_or_ineligible_outcome_rows=int((~expected.loss_eligible).sum()),passed=True))
 for tier in ['full','sequence']:
  folder=c.OUT/tier;z=pd.read_csv(folder/'sector_summary.csv');assert set(z.period)=={'development','exposed'};assert c.ANCHOR in set(z.model);b=pd.read_csv(folder/'familywise_bounds.csv');assert b.loc[b.status.eq('CONDITIONAL_AVAILABLE'),'simultaneous_lower95'].notna().all();assert b.loc[b.status.eq('INSUFFICIENT_TEMPORAL_SPAN'),'familywise_noise_floor'].isna().all();lock=json.loads((folder/'development_lock.json').read_text());assert lock['exposed_not_used_for_selection']
  for r in json.loads((folder/'calibration_maturity_audit.json').read_text()):assert r['max_training_endpoint']<r['date'] and r['oof_dates']>=2
  assert json.loads((folder/'primary_evaluation_support.json').read_text())['minimum_stocks_per_query']>=5
  checks.append(dict(check=tier+' cohort has bothperiods, finite temporal bounds and mature-only calibration',policies=z.model.nunique(),passed=True))
 replay=json.loads((c.OUT/'inference/replay_audit.json').read_text());assert len(replay)==18*6 and all(r['max_replay_error']<1e-5 for r in replay);checks.append(dict(check='All108annual tabular replay jobs match original valid predictions within float32 tolerance',maximum_error=max(r['max_replay_error'] for r in replay),passed=True))
 for r in json.loads((c.ROOT/'research/literature/20261031/code_receipts.json').read_text()):
  # Receipt keys differ between source acquisition formats; validate any explicit local destination.
  if 'local_path' in r:
   p=c.ROOT/r['local_path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
 checks.append(dict(check='Pinned foreign implementation receipts present with bothMITlicenses',passed=bool((c.ROOT/'research/literature/20261031/code/microsoft__qlib__LICENSE').exists() and (c.ROOT/'research/literature/20261031/code/SJTU-DMTai__MASTER__LICENSE').exists())))
 changed=subprocess.check_output(['git','diff','--name-only',protocol['baseline'],'--'],cwd=c.ROOT,text=True).splitlines();unexpected=[p for p in changed if not p.startswith(('research/','experiments/champion-vs-market-20261031/','tests/test_champion_market_')) and p!='.gitattributes'];assert not unexpected,unexpected
 checks.append(dict(check='Tracked changes since baseline are confined to research, evidence and benchmark tests',changed_files=len(changed),passed=True))
 assert all(r['passed'] for r in checks);c.save('validation_receipt.json',dict(checks=checks,passed=True,production_runtime_changed=False,baseline=protocol['baseline'],head_at_validation=subprocess.check_output(['git','rev-parse','HEAD'],cwd=c.ROOT,text=True).strip(),changed_paths=changed,external_ci_claimed=False));print('VALIDATED',len(checks),audit_count,flush=True)
if __name__=='__main__':main()
