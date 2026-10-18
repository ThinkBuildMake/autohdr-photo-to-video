"""Files: bucket objects and presigned links. Stub: S04 builds it."""

_NOT_BUILT = "Files is built in S04."


def presign_upload(key: str, content_type: str, max_bytes: int) -> dict:
    """Returns {url, fields}, valid 15 minutes."""
    raise NotImplementedError(_NOT_BUILT)


def presign_download(key: str, as_attachment: bool = False, filename: str | None = None) -> str:
    """Returns a link valid 1 hour."""
    raise NotImplementedError(_NOT_BUILT)


def put(key: str, path: str) -> None:
    raise NotImplementedError(_NOT_BUILT)


def get(key: str, path: str) -> None:
    raise NotImplementedError(_NOT_BUILT)


def head_object(key: str) -> dict | None:
    """Returns {sizeBytes} or None when the object does not exist."""
    raise NotImplementedError(_NOT_BUILT)
