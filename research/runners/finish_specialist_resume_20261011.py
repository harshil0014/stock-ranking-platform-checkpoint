"""Continue only after the identified full specialist audit terminates successfully."""
import json
import sys
import time
import psutil
from resume_major_research_20261011 import identity,wait_for,run,OUT


if __name__=='__main__':
    info=identity(int(sys.argv[1]),'audit_sector_specialist_ensemble_20261011.py')
    (OUT/'finish_controller.json').write_text(json.dumps(dict(pid=psutil.Process().pid,created=psutil.Process().create_time(),dependency=info),indent=2))
    wait_for(info)
    report=json.loads((OUT/'evaluation_verification.json').read_text())
    assert report['benchmark_cohorts_verified'] and report['current_ranks_verified']
    replay=json.loads((OUT/'replay_verification.json').read_text())
    assert replay['fits']==42 and replay['cutoffs_verified']
    run('audit_sector_specialist_ensemble_20261011.py','company')
    run('supplemental_global_specialist_audit_20261011.py','specialist')
    run('audit_sector_specialist_ensemble_20261011.py','ledger')
    (OUT/'finish_resume_complete.json').write_text(json.dumps(dict(stages_complete=True,full_goal_complete=False,remaining='Transport sensitivity, independent financial review, architecture contribution analysis, neural continuation, final requirements audit'),indent=2))
