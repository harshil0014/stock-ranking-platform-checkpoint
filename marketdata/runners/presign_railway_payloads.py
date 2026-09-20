"""Generate short-lived presigned upload URLs for Railway deployment payloads."""
from __future__ import annotations

import os

import boto3
from botocore.config import Config

OBJECTS = ("core_runtime.zip", "history_cache.zip")


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def client():
    return boto3.client(
        "s3",
        endpoint_url=_required("DEPLOY_BUCKET_ENDPOINT"),
        aws_access_key_id=_required("DEPLOY_BUCKET_ACCESS_KEY_ID"),
        aws_secret_access_key=_required("DEPLOY_BUCKET_SECRET_ACCESS_KEY"),
        region_name=os.environ.get("DEPLOY_BUCKET_REGION", "auto"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def main() -> int:
    s3 = client()
    bucket = _required("DEPLOY_BUCKET_NAME")
    for key in OBJECTS:
        url = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=3600,
        )
        print(f"UPLOAD_URL_{key}={url}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
