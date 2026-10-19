import base64
import io
import logging
import random

from PIL import Image
from uvicorn.logging import AccessFormatter

from app.access import scrubbing
from app.config import reset_settings

API_KEY = "sk-or-v1-" + "0123456789abcdef" * 4
SIGNATURE = "fedcba9876543210" * 4
PRESIGNED_URL = (
    "https://t3.storageapi.dev/bucket/photoshoots/p1/a.jpg"
    "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAEXAMPLE%2F20260101%2Fauto%2Fs3"
    f"&X-Amz-Date=20260101T000000Z&X-Amz-Expires=3600&X-Amz-Signature={SIGNATURE}"
)


def _png_base64() -> str:
    buffer = io.BytesIO()
    pixels = random.Random(7).randbytes(40 * 40 * 3)
    Image.frombytes("RGB", (40, 40), pixels).save(buffer, format="PNG")
    assert buffer.tell() >= 1024
    return base64.b64encode(buffer.getvalue()).decode()


def _configure(monkeypatch, **env):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    reset_settings()


def test_key_presigned_url_and_base64_are_scrubbed(monkeypatch, capsys, caplog):
    _configure(monkeypatch, OPENROUTER_API_KEY=API_KEY)
    encoded = _png_base64()
    logger = logging.getLogger("app.test")
    with caplog.at_level(logging.INFO):
        logger.info(
            "key=%s link=%s image=data:image/png;base64,%s", API_KEY, PRESIGNED_URL, encoded
        )
        logger.info(f"in message {API_KEY} {PRESIGNED_URL} {encoded}")
        logger.info("mapping %(k)s %(u)s", {"k": API_KEY, "u": PRESIGNED_URL})
    written = capsys.readouterr().err
    for text in (written, caplog.text):
        for secret in (API_KEY, PRESIGNED_URL, SIGNATURE, encoded, encoded[:200]):
            assert secret not in text
        assert "[api key]" in text or "[redacted]" in text
        assert "[presigned url]" in text
        assert "[base64 data]" in text
    assert "INFO app.test: " in written


def test_passphrase_and_basic_header_are_scrubbed(monkeypatch, capsys):
    _configure(monkeypatch, DEMO_PASSPHRASE="test-pass")
    token = base64.b64encode(b"anyone:other-secret").decode()
    logging.getLogger("app.test").info("pass test-pass header %s", f"Authorization: Basic {token}")
    written = capsys.readouterr().err
    assert "test-pass" not in written
    assert token not in written
    assert "Basic [redacted]" in written


def test_bearer_token_and_bucket_secrets_are_scrubbed(monkeypatch, capsys):
    _configure(
        monkeypatch,
        BUCKET_SECRET_ACCESS_KEY="bucket-secret-value",
        BUCKET_ACCESS_KEY_ID="bucket-key-id",
    )
    logging.getLogger("app.test").info("Bearer abc.def-123456 bucket-secret-value bucket-key-id")
    written = capsys.readouterr().err
    assert "abc.def-123456" not in written
    assert "bucket-secret-value" not in written
    assert "bucket-key-id" not in written


def test_exception_traceback_is_scrubbed(monkeypatch, capsys, caplog):
    _configure(monkeypatch, OPENROUTER_API_KEY=API_KEY)
    logger = logging.getLogger("app.test")
    try:
        raise RuntimeError(f"provider said no to {API_KEY}")
    except RuntimeError:
        logger.exception("call failed")
    written = capsys.readouterr().err
    assert "RuntimeError" in written
    assert "Traceback" in written
    assert API_KEY not in written
    assert API_KEY not in caplog.text


def test_third_party_logger_is_scrubbed(caplog):
    with caplog.at_level(logging.INFO):
        logging.getLogger("httpx").info('HTTP Request: GET %s "HTTP/1.1 200 OK"', PRESIGNED_URL)
    assert SIGNATURE not in caplog.text
    assert "[presigned url]" in caplog.text


def test_uvicorn_access_record_keeps_its_shape():
    record = logging.getLogger("uvicorn.access").makeRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", f"/img?X-Amz-Signature={SIGNATURE}", "1.1", 200),
        None,
    )
    assert isinstance(record.args, tuple) and len(record.args) == 5
    assert record.args[4] == 200
    line = AccessFormatter("%(levelprefix)s %(message)s", use_colors=False).format(record)
    assert "200" in line
    assert "GET" in line
    assert SIGNATURE not in line


def test_install_twice_wraps_the_factory_once():
    scrubbing.install_log_scrubbing()
    first = logging.getLogRecordFactory()
    scrubbing.install_log_scrubbing()
    assert logging.getLogRecordFactory() is first
    assert len(logging.getLogger("app").handlers) == 1


def test_plain_line_is_unchanged(capsys):
    logging.getLogger("app.test").info("shot %d of %s done in %.1fs", 3, "p1", 2.5)
    assert "shot 3 of p1 done in 2.5s" in capsys.readouterr().err


def test_scrub_leaves_plain_text_and_unsigned_urls():
    text = "see https://t3.storageapi.dev/bucket/a.jpg and sk-short"
    assert scrubbing.scrub(text) == text


def test_signature_argument_swallowed_by_format_string_does_not_leak(monkeypatch, capsys, caplog):
    _configure(monkeypatch)
    logger = logging.getLogger("app.probe")
    with caplog.at_level(logging.INFO):
        logger.info("https://t3.storageapi.dev/b/a.jpg?X-Amz-Signature=%s", SIGNATURE)
        logger.info("query X-Amz-Signature=%s&X-Amz-Date=1", SIGNATURE)
    err = capsys.readouterr().err
    assert SIGNATURE not in err
    assert SIGNATURE not in caplog.text
    assert "Logging error" not in err
    assert "[presigned url]" in err
    assert "X-Amz-Signature=[redacted]" in err
