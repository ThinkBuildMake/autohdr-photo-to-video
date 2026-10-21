"""Synthetic shoot folders and raw-SQL rows for the Evals tests (test-only)."""

import io
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image
from sqlalchemy import text

from app.db.base import session_scope
from app.db.schema import init_db

SUBMITTED = datetime(2026, 10, 19, 9, 0, 0)


def _jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 90, 60)).save(buffer, "JPEG")
    return buffer.getvalue()


def make_shoot_folders(root: Path, count: int = 12) -> Path:
    """`count` subfolders "Shoot 01".., each with two tiny synthetic photos (real JPEGs)."""
    folder = root / "shoots"
    for n in range(1, count + 1):
        sub = folder / f"Shoot {n:02d}"
        sub.mkdir(parents=True)
        for name in ("a.jpg", "b.jpg"):
            (sub / name).write_bytes(_jpeg())
    return folder


def _uid() -> str:
    return str(uuid.uuid4())


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _run(sql: str, **params) -> None:
    with session_scope() as session:
        session.execute(text(sql), params)


def add_photoshoot(label: str, created_at: str = "2026-10-19T08:00:00.000Z") -> str:
    """A ready shoot with no photos (a job on it cannot be planned)."""
    init_db()
    shoot = _uid()
    _run(
        "insert into photoshoots (id, label, status, created_at) values (:i, :l, 'ready', :c)",
        i=shoot,
        l=label,
        c=created_at,
    )
    return shoot


def add_style(
    name: str,
    song_id: str,
    demo_photoshoot_id: str | None = None,
    reference_job_id: str | None = None,
) -> str:
    style = _uid()
    _run(
        "insert into styles (id, name, author_name, style_text, song_id, fps,"
        " demo_photoshoot_id, reference_job_id) values (:i, :n, 'AutoHDR', :t, :s, 24, :d, :r)",
        i=style,
        n=name,
        t=f"{name}: slow and warm.",
        s=song_id,
        d=demo_photoshoot_id,
        r=reference_job_id,
    )
    return style


def add_job(
    photoshoot_id: str,
    song_id: str,
    style_id: str | None = None,
    purpose: str = "video",
    status: str = "ready",
    stop_reason: str | None = None,
    minutes: float | None = 10.0,
    shots: list[list[str]] = (),
) -> str:
    """A finished job. Each shot is its attempts' statuses; the last passed one is delivered."""
    job = _uid()
    finished = None if minutes is None else _iso(SUBMITTED + timedelta(minutes=minutes))
    _run(
        "insert into jobs (id, style_id, style_text, photoshoot_id, song_id, song_offset_s, fps,"
        " plan_status, purpose, status, stop_reason, first_submitted_at, submitted_at,"
        " first_finished_at, finished_at, video_key)"
        " values (:i, :st, 't', :p, :s, 0, 24, 'ready', :pu, :status, :sr, :sub, :sub,"
        " :fin, :fin, :vk)",
        i=job,
        st=style_id,
        p=photoshoot_id,
        s=song_id,
        pu=purpose,
        status=status,
        sr=stop_reason,
        sub=_iso(SUBMITTED),
        fin=finished,
        vk=None if status == "stopped" else f"videos/{job}.mp4",
    )
    for position, attempts in enumerate(shots, start=1):
        add_shot(job, position, attempts)
    return job


def finish_job(
    job_id: str,
    status: str = "ready",
    stop_reason: str | None = None,
    minutes: float = 10.0,
    shots: list[list[str]] | None = None,
) -> None:
    """Ends a real submitted job at once; `shots` (attempt statuses per shot) replaces its plan."""
    _run(
        "update jobs set status = :st, stop_reason = :sr, video_key = :vk,"
        " first_finished_at = strftime('%Y-%m-%dT%H:%M:%S.000Z', first_submitted_at, :plus),"
        " finished_at = strftime('%Y-%m-%dT%H:%M:%S.000Z', first_submitted_at, :plus)"
        " where id = :i",
        st=status,
        sr=stop_reason,
        plus=f"+{minutes} minutes",
        vk=None if status == "stopped" else f"videos/{job_id}.mp4",
        i=job_id,
    )
    if shots is not None:
        _run("delete from job_shots where job_id = :i", i=job_id)
        for position, attempts in enumerate(shots, start=1):
            add_shot(job_id, position, attempts)


def add_shot(job_id: str, position: int, attempts: list[str]) -> None:
    shot = _uid()
    passed = "passed" in attempts
    _run(
        "insert into job_shots (id, job_id, position, room, movement_name, movement_prompt,"
        " model, length_s, status, failure_reason)"
        " values (:i, :j, :p, 'living', 'dolly_in', 'm', 'google/veo-3.1', 3, :st, :fr)",
        i=shot,
        j=job_id,
        p=position,
        st="passed" if passed else "failed",
        fr=None if passed else "flagged_every_attempt",
    )
    for number, status in enumerate(attempts, start=1):
        attempt = _uid()
        _run(
            "insert into attempts (id, job_shot_id, round, attempt_no, prompt, model,"
            " requested_s, status, clip_key, started_at)"
            " values (:i, :s, 0, :n, 'p', 'google/veo-3.1', 3, :st, :ck, :at)",
            i=attempt,
            s=shot,
            n=number,
            st=status,
            ck=None if status == "error" else f"clips/{attempt}.mp4",
            at=_iso(SUBMITTED),
        )
        if status == "passed":
            _run("update job_shots set final_attempt_id = :a where id = :i", a=attempt, i=shot)


def add_cut_check(job_id: str, position: int, error_s: float) -> None:
    _run(
        "insert into cut_checks (job_id, position, expected_s, detected_s, error_s, transition)"
        " values (:j, :p, 3, 3, :e, 'cut')",
        j=job_id,
        p=position,
        e=error_s,
    )
