import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.evals import runs, shoots
from app.evals.__main__ import main
from app.jobs import queue
from tests.support.bucket import bucket  # noqa: F401
from tests.support.evals_rows import add_job, add_style, finish_job, make_shoot_folders
from tests.support.jobs_rows import planning_idle  # noqa: F401
from tests.support.library_rows import add_song

STYLE = "Golden hour"


@pytest.fixture(autouse=True)
def _quick_polls(monkeypatch, planning_idle):  # noqa: F811
    """Polls are short, and planning threads finish before the test's database goes away."""
    monkeypatch.setattr(runs, "POLL_S", 0.01)
    monkeypatch.setattr(shoots, "LABEL_POLL_S", 0.01)


class FakeJobs:
    """Wraps the real create and submit that Evals calls: records them, ends a submitted job
    at once (unless `finish` is off), and answers a seeded finished job for a shoot instead."""

    def __init__(self, real_create, real_submit):
        self.created = []
        self.submitted = []
        self.by_shoot: dict[str, str] = {}
        self.finish = True
        self.real_create, self.real_submit = real_create, real_submit

    def create_job(self, body):
        self.created.append(body)
        if body.photoshoot_id in self.by_shoot:
            return queue.get_job(self.by_shoot[body.photoshoot_id])
        return self.real_create(body)

    def submit_job(self, job_id):
        self.submitted.append(job_id)
        if job_id in self.by_shoot.values():
            return queue.get_job(job_id)
        job = self.real_submit(job_id)
        if self.finish:
            finish_job(job_id)
        return job


@pytest.fixture
def fake_jobs(monkeypatch):
    jobs = FakeJobs(runs.drafts.create_job, runs.queue.submit_job)
    monkeypatch.setattr(runs.drafts, "create_job", jobs.create_job)
    monkeypatch.setattr(runs.queue, "submit_job", jobs.submit_job)
    return jobs


@pytest.fixture
def world(tmp_path, bucket):  # noqa: F811
    """12 shoots really imported and the style "Golden hour" with a reference video, whose
    demo shoot is Shoot 01."""
    song = add_song()
    out = tmp_path / "out"
    assert main(["import", "--folder", str(make_shoot_folders(tmp_path)), "--out", str(out)]) == 0
    ids = list(json.loads((out / "shoots.json").read_text()).values())
    reference = add_job(ids[0], song, None, minutes=8)
    style = add_style(STYLE, song, demo_photoshoot_id=ids[0], reference_job_id=reference)
    return SimpleNamespace(song=song, shoots=ids, style=style, out=out, reference=reference)


def run_suite(world, suite: str) -> Path:
    """Runs `evals run` and returns the run folder it wrote."""
    assert main(["run", "--suite", suite, "--style", STYLE, "--out", str(world.out)]) == 0
    (folder,) = [p for p in world.out.iterdir() if p.is_dir()]
    return folder


def read_sheet(folder: Path) -> list[dict]:
    with open(folder / "sheet.csv", newline="") as handle:
        return list(csv.DictReader(handle))
