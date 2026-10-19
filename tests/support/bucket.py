"""A moto bucket that refuses presigned POST forms the way S3 does.

moto stores a posted file without reading its policy, so this wraps its POST handler
to check the signature, expiry, size range and field conditions first.
"""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest
from moto import mock_aws
from moto.s3.responses import S3Response

from app.config import reset_settings
from app.files.client import get_client, reset_client

BUCKET = "test-bucket"
MOTO_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
SECRET = "testing"
REGION = "us-east-1"

_SKIPPED_FIELDS = {"x-amz-signature", "policy", "file", "bucket"}


def _refusal(reason: str):
    body = f"<Error><Code>AccessDenied</Code><Message>{reason}</Message></Error>"
    return 403, {}, body


def _sign(secret: str, date: str, region: str, policy: str) -> str:
    key = ("AWS4" + secret).encode()
    for part in (date, region, "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    return hmac.new(key, policy.encode(), hashlib.sha256).hexdigest()


def _field(querystring, name: str):
    for key, values in querystring.items():
        if key.lower() == name.lower():
            return values[0]
    return None


def check_post_policy(querystring, body: bytes):
    """Returns None when the form is acceptable, else a refusal response."""
    policy_b64 = _field(querystring, "policy")
    if not policy_b64:
        return _refusal("Access Denied: a POST must carry a policy")
    credential = _field(querystring, "x-amz-credential") or ""
    try:
        _, date, region, _, _ = credential.split("/")
    except ValueError:
        return _refusal("Invalid credential")
    expected = _sign(SECRET, date, region, policy_b64)
    if not hmac.compare_digest(expected, _field(querystring, "x-amz-signature") or ""):
        return _refusal("The request signature we calculated does not match")
    policy = json.loads(base64.b64decode(policy_b64))
    expires = datetime.fromisoformat(policy["expiration"].replace("Z", "+00:00"))
    if expires <= datetime.now(UTC):
        return _refusal("Invalid according to Policy: Policy expired.")
    for condition in policy["conditions"]:
        if isinstance(condition, dict):
            checks = [("eq", name, value) for name, value in condition.items()]
        elif condition[0] == "content-length-range":
            if not condition[1] <= len(body) <= condition[2]:
                return _refusal("Your proposed upload is outside the size range")
            continue
        else:
            checks = [(condition[0], condition[1].lstrip("$"), condition[2])]
        for operator, name, value in checks:
            if name.lower() in _SKIPPED_FIELDS:
                continue
            actual = _field(querystring, name)
            if actual is None:
                return _refusal(f"Missing field {name}")
            if operator == "eq" and actual != value:
                return _refusal(f"Policy condition failed on {name}")
            if operator == "starts-with" and not actual.startswith(value):
                return _refusal(f"Policy condition failed on {name}")
    return None


def install_post_policy(monkeypatch) -> None:
    original = S3Response._bucket_response_post

    def enforcing(self, request, bucket_name):
        refusal = check_post_policy(self.querystring, self.body)
        if refusal is not None:
            return refusal
        return original(self, request, bucket_name)

    monkeypatch.setattr(S3Response, "_bucket_response_post", enforcing)


@pytest.fixture
def bucket(monkeypatch):
    monkeypatch.setenv("BUCKET_ENDPOINT", MOTO_ENDPOINT)
    monkeypatch.setenv("BUCKET_REGION", REGION)
    monkeypatch.setenv("BUCKET_NAME", BUCKET)
    monkeypatch.setenv("BUCKET_ACCESS_KEY_ID", SECRET)
    monkeypatch.setenv("BUCKET_SECRET_ACCESS_KEY", SECRET)
    reset_settings()
    reset_client()
    with mock_aws():
        get_client().create_bucket(Bucket=BUCKET)
        install_post_policy(monkeypatch)
        yield BUCKET
    reset_client()
