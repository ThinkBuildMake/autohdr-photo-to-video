"""The S3 client for the private bucket, built from settings."""

from functools import lru_cache

import boto3
from botocore.config import Config

from app.config import get_settings


@lru_cache(maxsize=1)
def get_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.BUCKET_ENDPOINT or None,
        region_name=settings.BUCKET_REGION,
        aws_access_key_id=settings.BUCKET_ACCESS_KEY_ID,
        aws_secret_access_key=settings.BUCKET_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def reset_client() -> None:
    get_client.cache_clear()


def bucket_name() -> str:
    return get_settings().BUCKET_NAME
