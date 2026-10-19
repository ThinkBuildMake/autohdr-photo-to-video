import pytest

from tests.support.fixtures import DEMO_PASSPHRASE, live_server  # noqa: F401


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 800},
        "http_credentials": {"username": "demo", "password": DEMO_PASSPHRASE},
    }
