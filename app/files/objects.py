"""Whole-file transfers between a local path and the private bucket."""

import mimetypes

from app.files.client import bucket_name, get_client


def put(key: str, path: str) -> None:
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    get_client().upload_file(path, bucket_name(), key, ExtraArgs={"ContentType": content_type})


def get(key: str, path: str) -> None:
    get_client().download_file(bucket_name(), key, path)


def delete_object(key: str) -> None:
    get_client().delete_object(Bucket=bucket_name(), Key=key)
