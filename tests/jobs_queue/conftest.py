import pytest

from tests.support.bucket import bucket  # noqa: F401
from tests.support.fixtures import client  # noqa: F401
from tests.support.queue_rows import add_shoot, add_song


@pytest.fixture
def song():
    return add_song()


@pytest.fixture
def shoot():
    return add_shoot()
