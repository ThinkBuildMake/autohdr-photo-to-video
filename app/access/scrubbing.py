"""Log scrubbing: no secret, presigned link or image/video data reaches a log line.

A log record factory is installed once per process (on import of the `app` package), so every
logger (app, uvicorn, httpx, botocore) and every handler sees scrubbed records. Values passed
through `extra` are not scrubbed.
"""

import logging
import re
import sys
from collections.abc import Mapping
from typing import Any

from app.config import get_settings

_SECRET_FIELDS = (
    "OPENROUTER_API_KEY",
    "DEMO_PASSPHRASE",
    "BUCKET_SECRET_ACCESS_KEY",
    "BUCKET_ACCESS_KEY_ID",
)
_MIN_SECRET_LENGTH = 4

_DATA_URI = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]+")
_URL = re.compile(r"https?://[^\s'\"<>)\]]+", re.IGNORECASE)
_SIGNED_NAMES = r"X-Amz-Signature|X-Amz-Credential|X-Amz-Security-Token|Signature|AWSAccessKeyId"
_SIGNED_QUERY = re.compile(rf"[?&;](?:{_SIGNED_NAMES})=", re.IGNORECASE)
_SIGNED_PARAM = re.compile(rf"\b({_SIGNED_NAMES})=[^&\s]+", re.IGNORECASE)
_API_KEY = re.compile(r"sk-or-[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]{20,}")
_AUTH_TOKEN = re.compile(r"\b(Basic|Bearer)\s+[A-Za-z0-9+/=._-]{6,}")
_BARE_BASE64 = re.compile(r"[A-Za-z0-9+/]{100,}={0,2}")

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_MARKER = "_app_scrubbing"


def _secret_values() -> list[str]:
    try:
        settings = get_settings()
    except Exception:
        return []
    values = {str(getattr(settings, name, "") or "") for name in _SECRET_FIELDS}
    return sorted((v for v in values if len(v) >= _MIN_SECRET_LENGTH), key=len, reverse=True)


def _scrub_url(match: re.Match[str]) -> str:
    return "[presigned url]" if _SIGNED_QUERY.search(match.group(0)) else match.group(0)


def scrub(text: str) -> str:
    for value in _secret_values():
        text = text.replace(value, "[redacted]")
    text = _DATA_URI.sub("[base64 data]", text)
    text = _URL.sub(_scrub_url, text)
    text = _SIGNED_PARAM.sub(r"\1=[redacted]", text)
    text = _API_KEY.sub("[api key]", text)
    text = _AUTH_TOKEN.sub(r"\1 [redacted]", text)
    return _BARE_BASE64.sub("[base64 data]", text)


def _scrub_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return scrub(str(value))


def _scrub_args(args: Any) -> Any:
    if isinstance(args, tuple):
        return tuple(_scrub_value(a) for a in args)
    if isinstance(args, Mapping):
        return {k: _scrub_value(v) for k, v in args.items()}
    return args


class _StderrHandler(logging.StreamHandler):
    """Writes to whatever `sys.stderr` is at emit time (so capture and redirection work)."""

    def __init__(self) -> None:
        logging.Handler.__init__(self)

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, value) -> None:
        return None


def _still_formats(record: logging.LogRecord, original_msg: str) -> bool:
    if record.msg != original_msg:
        return False
    try:
        record.getMessage()
    except Exception:
        return False
    return True


def _scrub_record(record: logging.LogRecord) -> None:
    original_msg, original_args = record.msg, record.args
    record.msg = scrub(str(original_msg))
    if original_args:
        record.args = _scrub_args(original_args)
    if original_args and not _still_formats(record, str(original_msg)):
        # The scrubbed format string no longer matches its arguments: format the originals,
        # scrub the whole text and drop the args so nothing unscrubbed stays on the record.
        record.msg = scrub(str(original_msg) % original_args)
        record.args = None
    if record.exc_info and record.exc_info[0] is not None:
        record.exc_text = scrub(logging.Formatter().formatException(record.exc_info))
    if record.stack_info:
        record.stack_info = scrub(record.stack_info)


def install_log_scrubbing() -> None:
    previous = logging.getLogRecordFactory()
    if not getattr(previous, _MARKER, False):

        def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = previous(*args, **kwargs)
            try:
                _scrub_record(record)
            except Exception:
                record.msg = "[log line withheld: scrubbing failed]"
                record.args = None
                record.exc_info = None
                record.exc_text = None
                record.stack_info = None
            return record

        setattr(factory, _MARKER, True)
        logging.setLogRecordFactory(factory)

    app_logger = logging.getLogger("app")
    if not app_logger.handlers:
        handler = _StderrHandler()
        handler.setFormatter(logging.Formatter(_FORMAT))
        app_logger.addHandler(handler)
        app_logger.setLevel(logging.INFO)
