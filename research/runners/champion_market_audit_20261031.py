"""Read model-fit receipts without confusing aggregate diagnostic audit files."""
import json

def fit_audits(folder):
 for path in sorted(folder.glob('*_audit.json')):
  if '__' not in path.stem:continue
  record=json.loads(path.read_text(encoding='utf-8'))
  if not isinstance(record,dict):raise ValueError('Model-fit receipt must be an object: '+path.name)
  for key in ['train_rows','max_training_endpoint']:
   if key not in record:raise ValueError('Incomplete model-fit receipt: '+path.name)
  if 'year' not in record:record['year']=int(path.name.split('__')[2].split('_')[0])
  yield path,record
