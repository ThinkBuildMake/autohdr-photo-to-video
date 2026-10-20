import pytest

from tests.support.bucket import bucket  # noqa: F401
from tests.support.fixtures import client  # noqa: F401
from tests.support.queue_rows import (
    add_attempt,
    add_job,
    add_shoot,
    add_shot,
    add_song,
    set_final_attempt,
)

SUBMITTED = "2026-10-19T09:00:00.000Z"
FINISHED = "2026-10-19T09:20:00.000Z"


@pytest.fixture
def shoot():
    return add_shoot(n_photos=8)


@pytest.fixture
def make_job(shoot):
    """A finished job: `passed` shots with a 4 s clip, then `failed` shots, from position 1."""
    song = add_song()

    def make(status="ready", passed=6, failed=0, **job):
        shoot_id, photos = shoot
        job_id = add_job(
            shoot_id,
            song,
            status=status,
            first_submitted_at=SUBMITTED,
            submitted_at=SUBMITTED,
            finished_at=FINISHED,
            **job,
        )
        for position in range(1, passed + failed + 1):
            if position <= passed:
                shot = add_shot(job_id, position, photos[position - 1], status="passed")
                clip = f"jobs/{job_id}/shots/{position}/r0/a1.mp4"
                set_final_attempt(shot, add_attempt(shot, 1, "passed", clip, requested_s=4.0))
            else:
                add_shot(
                    job_id,
                    position,
                    photos[position - 1],
                    status="failed",
                    failure_reason="flagged_every_attempt",
                    status_detail="A person appears.",
                )
        return job_id

    return make
