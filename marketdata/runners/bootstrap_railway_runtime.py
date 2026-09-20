"""Seed Railway's persistent runtime volume from the private deployment bucket."""
from __future__ import annotations

import os
from pathlib import Path
import zipfile

import boto3
from botocore.config import Config

MARKET_FINGERPRINT = "98adc0296bff77fd44fc4c6815692a86033b14763d689791df14752550983eb1"


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


def main() -> int:
    runtime_root = Path(os.environ.get("STOCK_RANKER_RUNTIME_ROOT", "/var/lib/stock-ranking"))
    data_root = runtime_root / "data"
    ready = data_root / "live_market" / "snapshots" / f"2026-09-18-{MARKET_FINGERPRINT}" / "bundle_manifest.json"
    if ready.is_file():
        print("Railway runtime payload already present.", flush=True)
        return 0
    runtime_root.mkdir(parents=True, exist_ok=True)
    archive = Path("/tmp/core_runtime.zip")
    print("Downloading validated core runtime payload...", flush=True)
    _client().download_file(_required("DEPLOY_BUCKET_NAME"), "core_runtime.zip", str(archive))
    print("Extracting validated core runtime payload...", flush=True)
    with zipfile.ZipFile(archive) as handle:
        handle.extractall(runtime_root)
    if not ready.is_file():
        raise RuntimeError("core runtime extraction completed but accepted market bundle is missing")
    archive.unlink(missing_ok=True)
    print("Railway runtime payload seeded.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
