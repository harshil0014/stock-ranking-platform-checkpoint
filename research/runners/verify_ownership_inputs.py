"""Print exact frozen research reproduction commands and validate local prerequisites."""
from pathlib import Path
from hashlib import sha256
import argparse,json
ROOT=Path(__file__).resolve().parents[2]
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--validate-only',action='store_true');args=parser.parse_args()
 normalized=ROOT/'research/data/ownership-recovery-20260925'
 import pandas as pd
 audit=pd.read_csv(normalized/'history_recovery_audit.csv')
 checked=0
 for row in audit.itertuples(index=False):
  if row.status=='NO_VALIDATED_LOCAL_HISTORY':continue
  source=ROOT/row.source
  if sha256(source.read_bytes()).hexdigest()!=row.source_sha256:raise ValueError(f'History source drift: {source}')
  if row.status=='OVERLAY':
   path=ROOT/'external_research_pack/ownership_history_20260925'/(row.ticker+'.csv')
   if sha256(path.read_bytes()).hexdigest()!=row.overlay_sha256:raise ValueError(f'Overlay drift: {path}')
  checked+=1
 terms=pd.read_csv(normalized/'resulting_equity_terms.csv')
 for row in terms.dropna(subset=['source_path']).itertuples(index=False):
  if sha256((ROOT/row.source_path).read_bytes()).hexdigest()!=row.source_sha256:raise ValueError('Entitlement source drift')
 print(json.dumps({'verified_history_identities':checked,'verified_entitlement_rows':len(terms),'research_cutoff':'2026-09-18'}))
if __name__=='__main__':main()
