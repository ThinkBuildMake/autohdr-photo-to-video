from pathlib import Path

import pytest

from scripts.check_ownership import find_ownership_violations, main

REPO = Path(__file__).resolve().parents[2]


def _tree(tmp_path, files):
    for name, code in files.items():
        path = tmp_path / "app" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code)
    return tmp_path / "app"


def test_real_app_has_no_violations():
    assert find_ownership_violations(REPO / "app") == []
    assert main() == 0


@pytest.mark.parametrize(
    ("name", "code", "table"),
    [
        ("pipeline/bad.py", "from sqlalchemy import insert\nq = insert(Job)\n", "jobs"),
        ("comparison/x.py", "def f(session):\n    session.add(Attempt(id=1))\n", "attempts"),
        ("library/y.py", "SQL = \"UPDATE jobs SET status='x'\"\n", "jobs"),
        ("web/z.py", "def f(s):\n    s.add_all([CutCheck(job_id=1)])\n", "cut_checks"),
        ("library/y2.py", 'Q = "update jobs set status=1"', "jobs"),
        ("worker.py", "def f(s):\n    s.add(Job(id=1))\n", "jobs"),
        ("pipeline/a.py", "def f(s):\n    a = Attempt(id=1)\n    s.add(a)\n", "attempts"),
        ("pipeline/b.py", "def f(s):\n    xs = [Attempt(id=1)]\n    s.add_all(xs)\n", "attempts"),
        (
            "pipeline/c.py",
            "def f(s):\n    a: Attempt = Attempt(id=1)\n    s.merge(a)\n",
            "attempts",
        ),
        ("jobs/w.py", 'SQL = "INSERT OR IGNORE INTO songs (id) VALUES (1)"\n', "songs"),
    ],
)
def test_foreign_write_is_a_violation(tmp_path, name, code, table):
    root = _tree(tmp_path, {name: code})
    assert find_ownership_violations(root) == [(f"app/{name}", table)]


def test_owners_and_db_are_allowed(tmp_path):
    root = _tree(
        tmp_path,
        {
            "jobs/ok.py": "q = insert(Job)\n",
            "providers/ok.py": "q = insert(ProviderCall)\n",
            "db/seed.py": "q = insert(Song)\n",
        },
    )
    assert find_ownership_violations(root) == []


def test_prose_mentioning_update_is_not_a_write(tmp_path):
    root = _tree(tmp_path, {"library/doc.py": '"""we update jobs here"""\n'})
    assert find_ownership_violations(root) == []
