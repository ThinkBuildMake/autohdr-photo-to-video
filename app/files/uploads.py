"""Upload links (presigned POST) and object lookup."""

from botocore.exceptions import ClientError

from app.files.client import bucket_name, get_client

UPLOAD_EXPIRES_S = 900

_MISSING_CODES = {"404", "NoSuchKey", "NotFound"}


def presign_upload(key: str, content_type: str, max_bytes: int) -> dict:
    """Returns {url, fields}, valid 15 minutes, for one file of 1..max_bytes bytes."""
    return get_client().generate_presigned_post(
        Bucket=bucket_name(),
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[{"Content-Type": content_type}, ["content-length-range", 1, max_bytes]],
        ExpiresIn=UPLOAD_EXPIRES_S,
    )


def head_object(key: str) -> dict | None:
    """Returns {sizeBytes} or None when the object does not exist."""
    try:
        response = get_client().head_object(Bucket=bucket_name(), Key=key)
    except ClientError as error:
        if str(error.response.get("Error", {}).get("Code")) in _MISSING_CODES:
            return None
        raise
    return {"sizeBytes": int(response["ContentLength"])}
