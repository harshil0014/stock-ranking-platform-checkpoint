"""Seed Railway's persistent runtime volume from the private deployment bucket."""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import shutil
import zipfile

import boto3
from botocore.config import Config

MARKET_FINGERPRINT = "98adc0296bff77fd44fc4c6815692a86033b14763d689791df14752550983eb1"
PERSONALIZED_RUNTIME_KEY = "personalized-ui-d499580.npz"
PERSONALIZED_RUNTIME_SHA256 = "515eac8ffc555a571406a4a41f9d931a016cb6280871a3d89f59846d2692ed0c"
PERSONALIZED_RUNTIME_BYTES = 98_546_546


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def _client():
    return boto3.client(
        "s3",
        endpoint_url=_required("DEPLOY_BUCKET_ENDPOINT"),
        aws_access_key_id=_required("DEPLOY_BUCKET_ACCESS_KEY_ID"),
        aws_secret_access_key=_required("DEPLOY_BUCKET_SECRET_ACCESS_KEY"),
        region_name=os.environ.get("DEPLOY_BUCKET_REGION", "auto"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_and_extract(s3, bucket: str, key: str, runtime_root: Path) -> None:
    archive = Path("/tmp") / key
    print(f"Downloading {key}...", flush=True)
    s3.download_file(bucket, key, str(archive))
    print(f"Extracting {key}...", flush=True)
    with zipfile.ZipFile(archive) as handle:
        handle.extractall(runtime_root)
    archive.unlink(missing_ok=True)


def _ensure_personalized_runtime(s3, bucket: str, runtime_root: Path) -> Path:
    target = runtime_root / "research" / "runtime" / PERSONALIZED_RUNTIME_KEY

    if target.is_file():
        if target.stat().st_size == PERSONALIZED_RUNTIME_BYTES and _sha(target) == PERSONALIZED_RUNTIME_SHA256:
            print("Personalized runtime pack already verified.", flush=True)
            return target
        print("Existing personalized runtime pack failed integrity validation; replacing it.", flush=True)

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    temporary.unlink(missing_ok=True)

    print(f"Downloading {PERSONALIZED_RUNTIME_KEY}...", flush=True)
    s3.download_file(bucket, PERSONALIZED_RUNTIME_KEY, str(temporary))

    actual_size = temporary.stat().st_size
    actual_sha = _sha(temporary)
    if actual_size != PERSONALIZED_RUNTIME_BYTES or actual_sha != PERSONALIZED_RUNTIME_SHA256:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(
            "personalized runtime pack failed integrity validation after download "
            f"(bytes={actual_size}, sha256={actual_sha})"
        )

    temporary.replace(target)
    print("Personalized runtime pack verified.", flush=True)
    return target


def main() -> int:
    runtime_root = Path(os.environ.get("STOCK_RANKER_RUNTIME_ROOT", "/var/lib/stock-ranking"))
    data_root = runtime_root / "data"
    ready = data_root / "live_market" / "snapshots" / f"2026-09-18-{MARKET_FINGERPRINT}" / "bundle_manifest.json"
    accepted_state = data_root / "live_market" / "accepted_state.json"
    history_root = data_root / "live_market" / "history_cache"
    history_archive = runtime_root / "history_cache.zip"

    runtime_root.mkdir(parents=True, exist_ok=True)
    s3 = _client()
    bucket = _required("DEPLOY_BUCKET_NAME")

    if not ready.is_file() or not accepted_state.is_file():
        _download_and_extract(s3, bucket, "core_runtime.zip", runtime_root)

    # Hosted deployment keeps the large history cache compressed and reads
    # individual CSV members on demand. This fits the Railway trial volume
    # without weakening the underlying observed data.
    if not history_archive.is_file():
        if history_root.exists():
            shutil.rmtree(history_root)
        print("Downloading compressed history cache...", flush=True)
        s3.download_file(bucket, "history_cache.zip", str(history_archive))

    personalized_runtime = _ensure_personalized_runtime(s3, bucket, runtime_root)

    if not ready.is_file():
        raise RuntimeError("accepted market bundle is missing after runtime bootstrap")
    if not accepted_state.is_file():
        raise RuntimeError("accepted_state.json is missing after runtime bootstrap")
    if not history_archive.is_file():
        raise RuntimeError("compressed history cache is missing after runtime bootstrap")
    if not personalized_runtime.is_file():
        raise RuntimeError("personalized runtime pack is missing after runtime bootstrap")

    print("Railway runtime payload ready.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
