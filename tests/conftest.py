import pytest

from app.config import reset_settings
from app.db.base import reset_engine
from tests.support.bucket import bucket  # noqa: F401


@pytest.fixture(autouse=True)
def _isolated_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("FAKE_PROVIDERS", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    reset_settings()
    reset_engine()
    yield
    reset_engine()
    reset_settings()
