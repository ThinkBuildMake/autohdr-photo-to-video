"""One claimed job's run: the deadline, the stop cases, and cutting the passed shots."""

import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.comparison import service as comparison
from app.files import service as files
from app.files.keys import video_key
from app.jobs import worker_interface
from app.jobs.errors import JobNotRunning
from app.jobs.worker_interface import CutPlan, CutShot
from app.media import service as media
from app.providers.errors import ProviderError
from app.shared.enums import ProviderErrorKind, StopReason
from app.shared.types import Job

log = logging.getLogger(__name__)

# Time one more clip and its check need (VIDEO_RESEARCH §7: 48-88 s per clip).
CLIP_AND_CHECK = timedelta(minutes=2)
WIDTH, HEIGHT = 1920, 1080


def now_utc() -> datetime:
    return datetime.now(UTC)


class Run:
    def __init__(self, job_id: str, deadline: datetime) -> None:
        self.job_id = job_id
        self.deadline = deadline
        self.stopped = False

    @classmethod
    def for_job(cls, job: Job) -> "Run":
        return cls(job.id, datetime.fromisoformat(job.started_at) + worker_interface.RUN_BUDGET)

    def has_time(self) -> bool:
        """True while the deadline leaves time for one more clip and check (PF-3)."""
        return not self.stopped and now_utc() + CLIP_AND_CHECK <= self.deadline

    def stop(self, reason: StopReason) -> None:
        self.stopped = True
        with contextlib.suppress(JobNotRunning):
            worker_interface.stop_job(self.job_id, reason)

    def run_shot(self, shot_id: str, work: Callable[[], object]) -> None:
        """Run one shot's work; its failure never stops the other shots (RL-3)."""
        if self.stopped:
            return
        try:
            work()
        except JobNotRunning:
            return
        except Exception as e:
            if isinstance(e, ProviderError) and e.kind == ProviderErrorKind.out_of_credit:
                self.stop(StopReason.out_of_credit)
                return
            log.exception("shot %s failed", shot_id)
            with contextlib.suppress(Exception):
                worker_interface.set_shot_result(shot_id, "failed", "provider_error")


def finish_run(run: Run, folder: Path) -> None:
    """Cut the passed shots to the song and finish the job, or stop it with the reason."""
    if run.stopped:
        return
    try:
        plan = worker_interface.cut_plan(run.job_id)
    except JobNotRunning:
        return
    passed = [shot for shot in plan.shots if shot.status == "passed"]
    if not passed:
        run.stop(StopReason.no_shot_passed)
        return
    try:
        video = _cut(run.job_id, plan, passed, folder / "cut")
        status = "ready" if len(passed) == len(plan.shots) else "ready_with_failures"
        worker_interface.finish_job(run.job_id, status, video=video)
    except JobNotRunning:
        return
    except Exception:
        log.exception("job %s could not be cut", run.job_id)
        run.stop(StopReason.assembly_failed)
        return
    try:
        comparison.record_cuts(run.job_id)
    except Exception:
        log.exception("cut check for job %s failed", run.job_id)


def _cut(job_id: str, plan: CutPlan, passed: list[CutShot], folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    clips = []
    for shot in passed:
        path = str(folder / f"{shot.position}.mp4")
        files.get(shot.clip_key, path)
        clips.append(
            {
                "path": path,
                "lengthS": shot.length_s,
                "transition": shot.transition,
                "transitionS": shot.transition_s,
            }
        )
    song = str(folder / f"song{Path(plan.song_key).suffix}")
    files.get(plan.song_key, song)
    out = str(folder / "video.mp4")
    result = media.assemble(clips, song, plan.song_offset_s, out, WIDTH, HEIGHT, plan.fps)
    key = video_key(job_id, plan.video_version + 1)
    worker_interface.cut_plan(job_id)
    files.put(key, out)
    return {
        "key": key,
        "duration_s": result["durationS"],
        "width": WIDTH,
        "height": HEIGHT,
        "fps": plan.fps,
    }
