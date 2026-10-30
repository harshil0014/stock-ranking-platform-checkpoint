"""Hash completed research outputs for portable integrity checks."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"experiments/personalized-deep-championship-20261002/v3"
TARGET=OUT/"artifact_manifest.json"
if TARGET.exists():
    raise FileExistsError(TARGET)
files=[]
for path in sorted(OUT.rglob("*")):
    if not path.is_file():
        continue
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            h.update(block)
    files.append({"path":path.relative_to(OUT).as_posix(),"bytes":path.stat().st_size,
                  "sha256":h.hexdigest()})
TARGET.write_text(json.dumps({"schema":"personalized_v12_artifact_manifest_v1",
                              "files":files},indent=2)+"\n",encoding="utf-8")
print("manifested",len(files),"files")
