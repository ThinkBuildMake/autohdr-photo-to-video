from pathlib import Path

from scripts.check_stubs import find_stub_uses, main

REPO = Path(__file__).resolve().parents[2]


def _tree(tmp_path, files):
    for name, body in files.items():
        path = tmp_path / "app" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return tmp_path


def test_real_repo_has_no_stub_use():
    assert find_stub_uses(REPO) == []


def test_imports_of_a_stubs_module_are_found(tmp_path):
    root = _tree(
        tmp_path,
        {
            "a/x.py": "from app.jobs import stubs\n",
            "a/y.py": "from app.jobs.stubs import thing\n",
            "a/z.py": "import app.library.stubs as s\n",
            "a/ok.py": "import os\n",
        },
    )
    assert [f.split(":")[0] for f in find_stub_uses(root)] == [
        "app/a/x.py",
        "app/a/y.py",
        "app/a/z.py",
    ]


def test_a_stubs_module_under_app_is_found_and_stub_media_too(tmp_path, capsys):
    root = _tree(
        tmp_path,
        {"a/stubs.py": "X = 1\n", "b/r.py": "KEY = 'stub-media/x'\n"},
    )
    assert find_stub_uses(root) == [
        "app/a/stubs.py: is a stubs module",
        "app/b/r.py: names stub-media",
    ]
    assert main([str(root)]) == 1
    assert "stub-media" in capsys.readouterr().out
