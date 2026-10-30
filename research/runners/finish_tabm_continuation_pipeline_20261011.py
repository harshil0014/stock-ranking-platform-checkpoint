"""Attach to neural training/evaluation controller and run independent audits."""
import json
import sys
import psutil
from resume_major_research_20261011 import identity,wait_for
from run_tabm_continuation_pipeline_20261011 import OUT,stage


if __name__=='__main__':
    info=identity(int(sys.argv[1]),'run_tabm_continuation_pipeline_20261011.py')
    (OUT/'audit_controller.json').write_text(json.dumps(dict(pid=psutil.Process().pid,created=psutil.Process().create_time(),dependency=info),indent=2))
    wait_for(info)
    assert json.loads((OUT/'pipeline_complete.json').read_text())['fits_and_evaluation_complete']
    stage('audit_tabm_continuation_20261011.py','replay')
    stage('audit_tabm_continuation_20261011.py','evaluate')
    stage('supplemental_global_specialist_audit_20261011.py','neural')
    stage('specialist_date_block_audit_20261011.py','neural')
    (OUT/'audit_pipeline_complete.json').write_text(json.dumps(dict(audits_complete=True,full_user_goal_complete=False,remaining='Matched12epoch controls, global transport sensitivity, final synthesis and financial review'),indent=2))
