"""Serial, thermally paced Windows research queue. Limits only its own child jobs.

One compute thread, Windows CPU hard cap, low priority, and real process-tree
suspension between short bursts. No system power plan or GPU settings are changed.
"""
from pathlib import Path
import os,sys,json,time,subprocess,ctypes,datetime,argparse
from ctypes import wintypes as w
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'work/champion-vs-market-20261031';OUT=ROOT/'experiments/champion-vs-market-20261031'
WORK.mkdir(parents=True,exist_ok=True)

class CpuRate(ctypes.Structure):_fields_=[('flags',w.DWORD),('rate',w.DWORD)]
class BasicLimit(ctypes.Structure):_fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),('flags',w.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active',w.DWORD),('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
class Io(ctypes.Structure):_fields_=[('v',ctypes.c_ulonglong*6)]
class ExtendedLimit(ctypes.Structure):_fields_=[('basic',BasicLimit),('io',Io),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
class Pids(ctypes.Structure):_fields_=[('assigned',w.DWORD),('count',w.DWORD),('ids',ctypes.c_size_t*128)]

class ManagedJob:
 def __init__(self,rate=1250):
  self.k=ctypes.WinDLL('kernel32',use_last_error=True);self.nt=ctypes.WinDLL('ntdll');self.process=None
  declarations={'CreateJobObjectW':([ctypes.c_void_p,w.LPCWSTR],w.HANDLE),'SetInformationJobObject':([w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD],w.BOOL),'QueryInformationJobObject':([w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.c_void_p],w.BOOL),'AssignProcessToJobObject':([w.HANDLE,w.HANDLE],w.BOOL),'TerminateJobObject':([w.HANDLE,w.UINT],w.BOOL),'CloseHandle':([w.HANDLE],w.BOOL),'OpenProcess':([w.DWORD,w.BOOL,w.DWORD],w.HANDLE)}
  for name,(args,result) in declarations.items():getattr(self.k,name).argtypes=args;getattr(self.k,name).restype=result
  for name in ['NtSuspendProcess','NtResumeProcess']:getattr(self.nt,name).argtypes=[w.HANDLE];getattr(self.nt,name).restype=ctypes.c_long
  self.handle=self.k.CreateJobObjectW(None,None)
  if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
  limit=ExtendedLimit();limit.basic.flags=0x2000
  self.check(self.k.SetInformationJobObject(self.handle,9,ctypes.byref(limit),ctypes.sizeof(limit)))
  cpu=CpuRate(1|4,rate);self.check(self.k.SetInformationJobObject(self.handle,15,ctypes.byref(cpu),ctypes.sizeof(cpu)))
  actual=CpuRate();self.check(self.k.QueryInformationJobObject(self.handle,15,ctypes.byref(actual),ctypes.sizeof(actual),None));assert actual.flags==5 and actual.rate==rate
 def check(self,result):
  if not result:raise ctypes.WinError(ctypes.get_last_error())
 def start(self,cmd,log,env):
  self.process=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=0x00000004|subprocess.IDLE_PRIORITY_CLASS|subprocess.CREATE_NO_WINDOW)
  try:self.check(self.k.AssignProcessToJobObject(self.handle,w.HANDLE(int(self.process._handle))));status=self.nt.NtResumeProcess(w.HANDLE(int(self.process._handle)));assert status==0,status
  except BaseException:self.process.kill();raise
 def ids(self):
  p=Pids();self.check(self.k.QueryInformationJobObject(self.handle,3,ctypes.byref(p),ctypes.sizeof(p),None));return list(p.ids[:p.count])
 def suspend(self,paused):
  for pid in reversed(self.ids()) if paused else self.ids():
   handle=self.k.OpenProcess(0x0800,False,pid)
   if handle:
    try:getattr(self.nt,'NtSuspendProcess' if paused else 'NtResumeProcess')(handle)
    finally:self.k.CloseHandle(handle)
 def close(self):
  if self.handle:
   self.k.TerminateJobObject(self.handle,1);self.k.CloseHandle(self.handle);self.handle=None

def temperature():
 try:return float(subprocess.check_output(['nvidia-smi','--query-gpu=temperature.gpu','--format=csv,noheader,nounits'],creationflags=subprocess.CREATE_NO_WINDOW,text=True,timeout=5).strip().splitlines()[0])
 except (OSError,ValueError,subprocess.SubprocessError):return None

def status(**values):
 data=dict(updated_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),supervisor_pid=os.getpid(),single_worker=True,compute_threads=1,cpu_hard_cap_percent=12.5,gpu_active_seconds=2,gpu_rest_seconds=4,cpu_active_seconds=4,cpu_rest_seconds=2,thermal_pause_celsius=58,thermal_resume_celsius=52,**values)
 dest=WORK/'low_load_status.json';temp=dest.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2),encoding='utf-8');os.replace(temp,dest)

def run(label,python,args,gpu=False):
 env=os.environ.copy()
 for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','STOCK_RESEARCH_THREADS']:env[key]='1'
 cmd=[str(ROOT/python)]+args;active=2 if gpu else 4;rest=4 if gpu else 2;job=ManagedJob();started=time.monotonic();cycles=0
 try:
  with (WORK/('low-load-'+label+'.log')).open('a',encoding='utf-8') as log:
   log.write('\nLOW LOAD RESUME '+datetime.datetime.now(datetime.timezone.utc).isoformat()+'\n');log.flush();job.start(cmd,log,env)
   while job.process.poll() is None:
    time.sleep(active);job.suspend(True);temp=temperature() if gpu else None;cycles+=1;reason='cooling_pause'
    control=WORK/'low_load_control.json';paused=control.exists() and json.loads(control.read_text()).get('pause',False)
    status(state=reason,worker=label,child_pids=job.ids(),gpu_temperature_celsius=temp,elapsed_seconds=round(time.monotonic()-started),cycles=cycles)
    time.sleep(rest)
    hot=gpu and temp is not None and temp>=58
    while paused or hot:
     status(state='user_paused' if paused else 'thermal_pause',worker=label,child_pids=job.ids(),gpu_temperature_celsius=temp);time.sleep(10);paused=control.exists() and json.loads(control.read_text()).get('pause',False);temp=temperature() if gpu else None
     hot=hot and temp is not None and temp>52
    job.suspend(False)
   code=job.process.wait()
   if code:raise RuntimeError(f'{label} failed with exit{code}; see low-load log')
 finally:job.close()
 status(state='stage_complete',worker=label,elapsed_seconds=round(time.monotonic()-started));print('LOW LOAD COMPLETE',label,flush=True)

def main(probe=False):
 if os.name!='nt':raise RuntimeError('Windows job objects required')
 if probe:
  run('governor-probe','.venv/Scripts/python.exe',['-c','import time; print("controlled child started",flush=True); time.sleep(12); print("controlled child finished",flush=True)']);return
 lock=WORK/'low_load_supervisor.lock'
 with lock.open('x') as f:f.write(str(os.getpid()))
 try:
  regular='.venv/Scripts/python.exe';gpu='.venv-gpu-research-20261011/Scripts/python.exe'
  for name in ['hist','master']:
   if not (OUT/'sequence'/f'{name}_complete.json').exists():run('sequence-'+name,gpu,['research/runners/champion_market_sequence_20261031.py',name,'--lease-owner','--cpu-threads','1'],True)
  evaluation_complete=['icir.csv','development_lock.json','sector_summary.csv','global_summary.csv','primary_evaluation_support.json']
  if not all((OUT/'sequence'/name).exists() for name in evaluation_complete):run('sequence-evaluate',regular,['research/runners/champion_market_evaluate_20261031.py','sequence'])
  if not (OUT/'sequence/coverage.json').exists():run('sequence-review',regular,['research/runners/champion_market_review_20261031.py','sequence','--resume'])
  if not (OUT/'tabular/random_forest_complete.json').exists():run('random-forest',regular,['research/runners/champion_market_tabular_20261031.py','random_forest','--lease-owner'])
  stages=[('inference',['champion_market_inference_20261031.py']),('full-evaluate',['champion_market_evaluate_20261031.py','full']),('full-review',['champion_market_review_20261031.py','full']),('portfolio',['champion_market_portfolio_20261031.py']),('validate',['champion_market_validate_20261031.py']),('report',['champion_market_publish_20261031.py']),('plots',['champion_market_plots_20261031.py'])]
  for label,args in stages:run(label,regular,['research/runners/'+args[0]]+args[1:])
  tests=[str(p.relative_to(ROOT)) for p in sorted((ROOT/'tests').glob('*20261031.py'))];run('tests',regular,['-m','pytest','-q']+tests)
  receipt=dict(passed=True,command='python -m pytest -q tests/*20261031.py',log_sha256=__import__('hashlib').sha256((WORK/'low-load-tests.log').read_bytes()).hexdigest(),execution='Serial Windows-managed low-load queue',external_ci=False);(OUT/'test_receipt.json').write_text(json.dumps(receipt,indent=2));run('bundle',regular,['research/runners/champion_market_bundle_20261031.py']);status(state='complete_pending_result_and_visual_review',worker=None)
 except BaseException as error:status(state='failed',error=str(error));raise
 finally:lock.unlink(missing_ok=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--probe',action='store_true');main(p.parse_args().probe)
