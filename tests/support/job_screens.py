"""Synthetic jobs for the Jobs and Job screens, served by stubbing the Jobs reads the pages call."""

from dataclasses import dataclass, field

import pytest

from app.errors import AppError
from app.jobs import queue, stubs
from app.jobs.errors import JobNotFound
from app.shared.types import Job, JobListItem, JobShot

JOB_A = "aaaaaaaa-0000-4000-8000-000000000001"
JOB_B = "bbbbbbbb-0000-4000-8000-000000000002"


def shot(position: int, **changes) -> JobShot:
    base = stubs.stub_shot(0).model_copy(
        update={
            "id": f"55555555-5555-4555-8555-55555555550{position}",
            "position": position,
            "edit_status": "edited",
        }
    )
    return base.model_copy(update=changes)


def job(job_id: str = JOB_A, **changes) -> Job:
    base = stubs.stub_job().model_copy(
        update={"id": job_id, "shots": [shot(1), shot(2), shot(3), shot(4)]}
    )
    return base.model_copy(update=changes)


def list_item(job_id: str, **changes) -> JobListItem:
    base = stubs.stub_list_item().model_copy(update={"id": job_id})
    return base.model_copy(update=changes)


@dataclass
class StubJobs:
    jobs: dict[str, Job] = field(default_factory=dict)
    items: list[JobListItem] = field(default_factory=list)

    def add(self, item: Job) -> None:
        self.jobs[item.id] = item


@pytest.fixture
def stub_jobs(monkeypatch) -> StubJobs:
    """listJobs, getJob and getVideo answer from this object instead of the database."""
    held = StubJobs()

    def get_job(job_id: str) -> Job:
        if job_id not in held.jobs:
            raise JobNotFound(job_id)
        return held.jobs[job_id]

    def get_video(job_id: str) -> dict:
        video = get_job(job_id).video
        if video is None:
            raise AppError(409, "no_video", "This job has no video yet.")
        return {
            "url": video.url,
            "download_url": f"{video.url}?download",
            "duration_s": video.duration_s,
        }

    monkeypatch.setattr(queue, "list_jobs", lambda: list(held.items))
    monkeypatch.setattr(queue, "get_job", get_job)
    monkeypatch.setattr(queue, "get_video", get_video)
    return held
