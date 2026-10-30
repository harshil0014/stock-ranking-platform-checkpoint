"""Independent GPU checkpoint replay and matched final neural diagnostics."""
import json
import pickle
import sys
import numpy as np
import pandas as pd
import torch
import sector_tabm_continuation_20261011 as n
import audit_sector_specialist_ensemble_20261011 as audit


def replay():
    assert torch.cuda.is_available()
    x=n.s.panel();rows=[];torch.set_num_threads(2)
    torch.backends.cuda.matmul.allow_tf32=False
    torch.backends.cudnn.allow_tf32=False
    for year in [2020,2021,2022,2023,2024,2025,'current']:
        z=n.s.h.current() if year=='current' else x[x.decision_date.str.startswith(str(year))]
        cutoff=n.s.p.ASOF if year=='current' else f'{year}-01-01'
        t=n.s.training(x,cutoff)
        saved_identity=pd.read_csv(n.s.OUT/f'training_identity_{year}.csv.gz')
        pd.testing.assert_frame_equal(saved_identity,t[n.s.p.KEYS+['endpoint','sector']],check_dtype=False)
        for family in n.FAMILIES:
            receipt=json.loads((n.OUT/f'{family}_{year}_audit.json').read_text())
            assert receipt['max_endpoint']<receipt['cutoff']==cutoff
            assert receipt['training_identity_sha256']==n.s.digest(n.s.OUT/f'training_identity_{year}.csv.gz')
            prep_path=n.s.OUT/f'{family}_{year}_prep.pkl'
            assert receipt['preprocessor_sha256']==n.s.digest(prep_path)
            with prep_path.open('rb') as stream:
                prep=pickle.load(stream)
            rawpath=n.OUT/f'{family}_{year}_raw.csv.gz'
            assert receipt['raw_sha256']==n.s.digest(rawpath)
            raw=pd.read_csv(rawpath)
            pd.testing.assert_frame_equal(raw[n.s.p.KEYS],z[n.s.p.KEYS].reset_index(drop=True),check_dtype=False)
            cols=n.s.FEATURES[family]
            values=torch.tensor(prep.transform(z[cols]),dtype=torch.float32,device='cuda')
            for epoch in n.CHECKPOINTS:
                path=n.OUT/f'{family}_e{epoch}_{year}.pt'
                assert receipt['models_sha256'][path.name]==n.s.digest(path)
                model=n.s.torch_model(len(cols),family=='tabm_embedded').cuda()
                model.load_state_dict(torch.load(path,map_location='cuda',weights_only=True))
                output=n.predict(model,values)
                saved=raw[[f'e{epoch}_{target}' for target in n.s.TARGETS]].to_numpy().astype(output.dtype)
                np.testing.assert_array_equal(output,saved)
                rows.append(dict(year=year,family=family,epoch=epoch,rows=len(z),maximum_error=0.,cutoff_verified=True,model_sha256=n.s.digest(path)))
                del model
            del values;torch.cuda.empty_cache()
        print('REPLAY',year,flush=True)
    pd.DataFrame(rows).to_csv(n.OUT/'serialized_replay.csv',index=False)
    n.write('replay_verification.json',dict(fits=len(rows),native_predictions_exact=True,cutoffs_verified=True,source_identities_verified=True))


def evaluate():
    audit.OUT=n.OUT;audit.s.OUT=n.OUT;audit.c.NAMES=n.NAMES
    for year in range(2020,2026):
        target=n.OUT/f'combined_{year}.csv.gz'
        if not target.exists():
            target.hardlink_to(n.OUT/f'predictions_{year}.csv.gz')
    audit.evaluate();audit.company_audit()


if __name__=='__main__':
    {'replay':replay,'evaluate':evaluate}[sys.argv[1]]()
