"""Download links (presigned GET)."""

import re

from app.files.client import bucket_name, get_client

DOWNLOAD_EXPIRES_S = 3600

_UNSAFE_NAME_CHARS = re.compile(r'["/\\]')


def presign_download(key: str, as_attachment: bool = False, filename: str | None = None) -> str:
    """Returns a link valid 1 hour; with as_attachment the browser saves it under a name."""
    params = {"Bucket": bucket_name(), "Key": key}
    if as_attachment:
        name = _UNSAFE_NAME_CHARS.sub("", filename or key.rsplit("/", 1)[-1])
        params["ResponseContentDisposition"] = f'attachment; filename="{name}"'
    return get_client().generate_presigned_url(
        "get_object", Params=params, ExpiresIn=DOWNLOAD_EXPIRES_S
    )
