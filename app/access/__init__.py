"""Access: the shared passphrase.

Must hold (ARCHITECTURE, Module: Access):
- No route other than /healthz answers without the passphrase.
- The passphrase is never logged.

S02 adds the passphrase check and log scrubbing here; install() does nothing yet.
"""

from fastapi import FastAPI


def install(app: FastAPI) -> None:
    return None
