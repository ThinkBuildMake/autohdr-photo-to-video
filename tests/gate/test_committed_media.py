import subprocess
from pathlib import Path

from scripts.check_media import find_committed_media, main

REPO = Path(__file__).resolve().parents[2]


def _git_repo(tmp_path, files):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "x")
    return tmp_path


def test_media_outside_fixtures_is_found(tmp_path):
    root = _git_repo(tmp_path, ["docs/house.jpg", "clip.MP4", "a.png", "notes.txt"])
    assert sorted(find_committed_media(root)) == ["a.png", "clip.MP4", "docs/house.jpg"]


def test_fixtures_are_allowed(tmp_path):
    root = _git_repo(tmp_path, ["tests/fixtures/tiny.png"])
    assert find_committed_media(root) == []


def test_real_repo_has_no_committed_media():
    assert find_committed_media(REPO) == []


def test_main_exits_1_and_names_the_file(tmp_path, capsys):
    root = _git_repo(tmp_path, ["docs/house.jpg"])
    assert main([str(root)]) == 1
    assert "docs/house.jpg" in capsys.readouterr().out
