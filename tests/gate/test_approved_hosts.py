from dataclasses import replace
from pathlib import Path

from app.config import get_settings
from scripts.check_hosts import find_unapproved_hosts, main

REPO = Path(__file__).resolve().parents[2]


def _empty_repo(tmp_path, env=""):
    (tmp_path / ".env.example").write_text(env)
    (tmp_path / "app").mkdir()
    return tmp_path


def test_real_repo_has_no_unapproved_hosts():
    assert find_unapproved_hosts(REPO, get_settings()) == []


def test_env_example_unapproved_host(tmp_path):
    root = _empty_repo(tmp_path, "OPENROUTER_BASE_URL=https://api.example.com\n")
    found = find_unapproved_hosts(root, get_settings())
    assert len(found) == 1
    assert "OPENROUTER_BASE_URL" in found[0][0]
    assert found[0][1] == "api.example.com"


def test_settings_unapproved_host(tmp_path):
    settings = replace(get_settings(), BUCKET_ENDPOINT="https://s3.amazonaws.com")
    found = find_unapproved_hosts(_empty_repo(tmp_path), settings)
    assert found == [("Settings.BUCKET_ENDPOINT", "s3.amazonaws.com")]


def test_app_string_constant_unapproved_host(tmp_path):
    root = _empty_repo(tmp_path)
    (root / "app" / "x.py").write_text('URL = "https://api.replicate.com/v1"\n')
    found = find_unapproved_hosts(root, get_settings())
    assert len(found) == 1
    assert found[0][0].startswith("app/x.py")
    assert found[0][1] == "api.replicate.com"


def test_docstring_counts(tmp_path):
    root = _empty_repo(tmp_path)
    (root / "app" / "x.py").write_text('"""See https://example.org/docs."""\n')
    assert [h for _, h in find_unapproved_hosts(root, get_settings())] == ["example.org"]


def test_approved_and_local_hosts_pass(tmp_path):
    root = _empty_repo(tmp_path, "BUCKET_ENDPOINT=https://my-bucket.t3.storageapi.dev\n")
    (root / "app" / "x.py").write_text(
        'A = "http://localhost:9000"\nB = "https://my-bucket.t3.storageapi.dev/x"\n'
        'C = "https://openrouter.ai/api/v1"\nD = "http://127.0.0.1:8000"\n'
    )
    assert find_unapproved_hosts(root, get_settings()) == []


def test_main_exits_zero_on_real_repo():
    assert main() == 0
