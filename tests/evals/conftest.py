import csv
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.evals import stubs
from app.evals.__main__ import main
from tests.support.bucket import bucket  # noqa: F401
from tests.support.evals_rows import add_photoshoot, add_style, make_shoot_folders
from tests.support.library_rows import add_song

STYLE = "Golden hour"


class FakeJobs:
    """Stands in for the createJob and submitJob stubs; answers seeded job ids per shoot."""

    def __init__(self):
        self.created = []
        self.submitted = []
        self.by_shoot: dict[str, str] = {}

    def create_job(self, body):
        self.created.append(body)
        return self.by_shoot.get(body.photoshoot_id) or str(uuid.uuid4())

    def submit_job(self, job_id):
        self.submitted.append(job_id)


@pytest.fixture
def fake_jobs(monkeypatch):
    jobs = FakeJobs()
    monkeypatch.setattr(stubs, "create_job", jobs.create_job)
    monkeypatch.setattr(stubs, "submit_job", jobs.submit_job)
    return jobs


@pytest.fixture
def world(tmp_path, bucket):  # noqa: F811
    """12 imported shoots and the style "Golden hour", whose demo shoot is Shoot 01."""
    song = add_song()
    shoots = [add_photoshoot(f"Shoot {n:02d}") for n in range(1, 13)]
    style = add_style(STYLE, song, demo_photoshoot_id=shoots[0])
    out = tmp_path / "out"
    assert main(["import", "--folder", str(make_shoot_folders(tmp_path)), "--out", str(out)]) == 0
    return SimpleNamespace(song=song, shoots=shoots, style=style, out=out)


def run_suite(world, suite: str) -> Path:
    """Runs `evals run` and returns the run folder it wrote."""
    assert main(["run", "--suite", suite, "--style", STYLE, "--out", str(world.out)]) == 0
    (folder,) = [p for p in world.out.iterdir() if p.is_dir()]
    return folder


def read_sheet(folder: Path) -> list[dict]:
    with open(folder / "sheet.csv", newline="") as handle:
        return list(csv.DictReader(handle))
