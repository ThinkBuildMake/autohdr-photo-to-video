"""Access: the shared passphrase.

Must hold (ARCHITECTURE, Module: Access):
- No route other than /healthz answers without the passphrase.
- The passphrase is never logged.

HTTP basic auth: any user name, the password is DEMO_PASSPHRASE. An empty
DEMO_PASSPHRASE refuses everyone (fail closed).
"""

import base64
import binascii
import hmac

from fastapi import FastAPI
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings

OPEN_PATH = "/healthz"
CHALLENGE = 'Basic realm="AutoHDR demo", charset="UTF-8"'


def _password_from(scope: Scope) -> bytes | None:
    for name, value in scope["headers"]:
        if name != b"authorization":
            continue
        scheme, _, token = value.decode("latin-1").partition(" ")
        if scheme.lower() != "basic":
            return None
        try:
            decoded = base64.b64decode(token.strip(), validate=True).decode("utf-8")
        except (binascii.Error, ValueError):
            return None
        _, colon, password = decoded.partition(":")
        return password.encode("utf-8") if colon else None
    return None


class PassphraseMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == OPEN_PATH:
            await self.app(scope, receive, send)
            return
        expected = get_settings().DEMO_PASSPHRASE.encode("utf-8")
        given = _password_from(scope)
        if expected and given is not None and hmac.compare_digest(given, expected):
            await self.app(scope, receive, send)
            return
        refusal = Response(status_code=401, headers={"WWW-Authenticate": CHALLENGE})
        await refusal(scope, receive, send)


def install(app: FastAPI) -> None:
    app.add_middleware(PassphraseMiddleware)
