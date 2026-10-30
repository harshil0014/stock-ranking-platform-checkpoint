from pathlib import Path
import hashlib, json
ROOT=Path(__file__).resolve().parents[2]
EXP=ROOT/"experiments/personalized-v13-20261002"
extra=[
 ROOT/"research/reports/personalized_v13_history_weekly_20261002.md",
 ROOT/"research/runners/personalized_v13_history_weekly_probe.py",
 ROOT/"research/runners/personalized_v13_smooth_history_probe.py",
 ROOT/"research/runners/seal_personalized_v13_selection.py",
 ROOT/"research/runners/evaluate_personalized_v13_blind_20240131.py",
 ROOT/"research/runners/audit_personalized_v13_known_2025.py",
]
files=sorted([p for p in EXP.rglob("*") if p.is_file()]+extra,key=lambda p:str(p))
rows=[]
for p in files:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    rows.append({"path":str(p.relative_to(ROOT)).replace("\\","/"),"bytes":p.stat().st_size,"sha256":h.hexdigest()})
(EXP/"artifact_manifest.json").write_text(json.dumps({"schema":"personalized_v13_manifest_v1","files":rows},indent=2)+"\n")
print("manifest_files",len(rows))
