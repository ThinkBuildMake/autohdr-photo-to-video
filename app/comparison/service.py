"""Comparison module interface: cut checks, setReference and getReproduction."""

import logging
from collections import Counter
from itertools import accumulate
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory

from sqlalchemy import delete, select

from app.comparison.models import CutCheck
from app.comparison.schemas import (
    Reproduction,
    ShotRow,
    ShotTiming,
    SongSame,
    Summary,
    VideoRef,
    VideoSummary,
)
from app.db.base import session_scope
from app.errors import AppError
from app.files import service as files
from app.jobs.errors import JobNotFound
from app.jobs.models import Job, JobShot
from app.library import service as library
from app.library.models import Style as StyleRow
from app.library.service import StyleNotFound
from app.media import service as media
from app.photoshoots.models import Photoshoot
from app.shared.types import Style

log = logging.getLogger(__name__)

MATCH_WINDOW_S = 0.5
_FINISHED = ("ready", "ready_with_failures")


def set_reference(style_id: str, job_id: str) -> Style:
    with session_scope() as session:
        style = session.get(StyleRow, style_id)
        if style is None:
            raise StyleNotFound(style_id)
        job = session.get(Job, job_id)
        if job is None:
            raise JobNotFound(job_id)
        if job.status != "ready" or (job.style_text, job.song_id, job.fps) != (
            style.style_text,
            style.song_id,
            style.fps,
        ):
            raise AppError(
                409,
                "not_eligible",
                "The reference must be a ready job made from the style's saved text, song and fps.",
            )
        library.set_reference_job(style_id, job_id, session)
    return library.get_style(style_id)


def _in_video(shot: JobShot) -> bool:
    return not shot.removed and shot.status not in ("failed", "skipped")


def _flagged(shot: JobShot) -> bool:
    fallback = shot.model_used is not None and shot.model_used != shot.model
    return not _in_video(shot) or fallback or shot.edited_at is not None


def _summary(shots: list[JobShot]) -> VideoSummary:
    shown = [shot for shot in shots if _in_video(shot)]
    lengths = [shot.length_s for shot in shown]
    return VideoSummary(
        shot_count=len(shown),
        total_s=round(sum(lengths), 3),
        median_shot_s=median(lengths) if lengths else 0.0,
        movements=Counter(shot.movement_name for shot in shown),
        transitions=Counter(shot.transition for shot in shown[1:]),
    )


def _timing(shot: JobShot | None, errors: dict[int, float | None]) -> ShotTiming | None:
    if shot is None or not _in_video(shot):
        return None
    return ShotTiming(length_s=shot.length_s, cut_error_s=errors.get(shot.position))


def _read(session, job: Job) -> tuple[VideoRef, list[JobShot], dict[int, float | None]]:
    label = session.scalar(select(Photoshoot.label).where(Photoshoot.id == job.photoshoot_id))
    shots = session.scalars(
        select(JobShot).where(JobShot.job_id == job.id).order_by(JobShot.position)
    ).all()
    errors = session.execute(
        select(CutCheck.position, CutCheck.error_s).where(CutCheck.job_id == job.id)
    ).all()
    video = VideoRef(
        job_id=job.id,
        video_url=files.presign_download(job.video_key),
        photoshoot_label=label,
    )
    return video, shots, dict(errors)


def get_reproduction(style_id: str, job_id: str) -> Reproduction:
    style = library.get_style(style_id)
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise JobNotFound(job_id)
        if style.reference_job_id is None:
            raise AppError(409, "no_reference", "This style has no reference video yet.")
        if job.style_id != style_id or job.purpose != "reproduction":
            raise AppError(
                409, "not_a_reproduction", "That job is not a reproduction of this style."
            )
        reference = session.get(Job, style.reference_job_id)
        if any(j is None or j.status not in _FINISHED or not j.video_key for j in (reference, job)):
            raise AppError(409, "not_ready", "Both videos must be finished first.")
        ref_video, ref_shots, ref_errors = _read(session, reference)
        rep_video, rep_shots, rep_errors = _read(session, job)
        song_id, style_text, ref_song_id = job.song_id, job.style_text, reference.song_id
    ref_by, rep_by = {s.position: s for s in ref_shots}, {s.position: s for s in rep_shots}
    rows = []
    for position in sorted(ref_by | rep_by):
        ref, rep = ref_by.get(position), rep_by.get(position)
        shown = rep or ref
        rows.append(
            ShotRow(
                position=position,
                movement_name=shown.movement_name,
                transition=shown.transition,
                reference=_timing(ref, ref_errors),
                reproduction=_timing(rep, rep_errors),
                flagged=rep is not None and _flagged(rep),
            )
        )
    errors = [abs(e) for e in [*ref_errors.values(), *rep_errors.values()] if e is not None]
    return Reproduction(
        reference=ref_video,
        reproduction=rep_video,
        song=SongSame(
            same_song=song_id == ref_song_id,
            credit=next(song.credit for song in library.list_songs() if song.id == song_id),
        ),
        same_text=style_text == style.style_text,
        summary=Summary(reference=_summary(ref_shots), reproduction=_summary(rep_shots)),
        shots=rows,
        max_cut_error_s=max(errors, default=None),
    )


def _match(expected: list[float], detected: list[float]) -> dict[int, float]:
    """Expected cut index -> detected cut; each detected cut is used once, nearest pair first."""
    pairs = sorted(
        (abs(d - e), i, j)
        for i, e in enumerate(expected)
        for j, d in enumerate(detected)
        if abs(d - e) <= MATCH_WINDOW_S
    )
    matched, used = {}, set()
    for _, i, j in pairs:
        if i not in matched and j not in used:
            matched[i] = detected[j]
            used.add(j)
    return matched


def record_cuts(job_id: str) -> None:
    """Detects the cuts in the job's video and replaces its cut_checks rows.

    A detector failure leaves detected_s null on every row; it never fails the job.
    """
    with session_scope() as session:
        video_key = session.scalar(select(Job.video_key).where(Job.id == job_id))
        shots = session.scalars(
            select(JobShot).where(JobShot.job_id == job_id).order_by(JobShot.position)
        ).all()
    shots = [shot for shot in shots if _in_video(shot)]
    try:
        with TemporaryDirectory() as folder:
            path = str(Path(folder) / "video.mp4")
            files.get(video_key, path)
            detected = media.detect_cuts(path)
    except Exception as exc:
        log.warning("cut detection failed for job %s (%s)", job_id, type(exc).__name__)
        detected = []
    expected = list(accumulate(shot.length_s for shot in shots[:-1]))
    found = _match(expected, detected)
    rows = [
        CutCheck(
            job_id=job_id,
            position=shot.position,
            expected_s=round(expected_s, 3),
            detected_s=found.get(i),
            error_s=None if i not in found else round(found[i] - expected_s, 3),
            transition=shot.transition,
        )
        for i, (shot, expected_s) in enumerate(zip(shots[1:], expected, strict=True))
    ]
    with session_scope() as session:
        session.execute(delete(CutCheck).where(CutCheck.job_id == job_id))
        session.add_all(rows)
