"""Synthetic job rows for the queue tests: raw SQL inserts, test-only."""

import uuid

from sqlalchemy import text

from app.db.base import session_scope
from app.db.schema import init_db
from tests.support.library_rows import add_song  # noqa: F401  (re-exported for the tests)


def add_shoot(label="12 Oak Street", n_photos=3) -> tuple[str, list[str]]:
    init_db()
    photoshoot_id = str(uuid.uuid4())
    photo_ids = [str(uuid.uuid4()) for _ in range(n_photos)]
    with session_scope() as session:
        session.execute(
            text("insert into photoshoots (id, label, status) values (:i, :l, 'uploaded')"),
            {"i": photoshoot_id, "l": label},
        )
        for position, photo_id in enumerate(photo_ids):
            session.execute(
                text(
                    "insert into photos (id, photoshoot_id, position, original_name,"
                    " content_type, size_bytes, file_key, status)"
                    " values (:i, :p, :pos, :n, 'image/jpeg', 1000, :k, 'uploaded')"
                ),
                {
                    "i": photo_id,
                    "p": photoshoot_id,
                    "pos": position,
                    "n": f"photo-{position}.jpg",
                    "k": f"photoshoots/{photoshoot_id}/{photo_id}.jpg",
                },
            )
    return photoshoot_id, photo_ids


def add_job(
    photoshoot_id,
    song_id,
    status="draft",
    plan_status="ready",
    created_at=None,
    submitted_at=None,
    started_at=None,
    finished_at=None,
    first_submitted_at=None,
    video_key=None,
    video_duration_s=None,
    video_width=None,
    video_height=None,
    style_id=None,
    stop_reason=None,
) -> str:
    init_db()
    job_id = str(uuid.uuid4())
    columns = {
        "id": job_id,
        "style_id": style_id,
        "style_text": "Slow and warm.",
        "photoshoot_id": photoshoot_id,
        "plan_status": plan_status,
        "status": status,
        "stop_reason": stop_reason,
        "song_id": song_id,
        "song_offset_s": 0,
        "fps": 30,
        "first_submitted_at": first_submitted_at,
        "submitted_at": submitted_at,
        "started_at": started_at,
        "finished_at": finished_at,
        "video_key": video_key,
        "video_duration_s": video_duration_s,
        "video_width": video_width,
        "video_height": video_height,
    }
    if created_at is not None:
        columns["created_at"] = created_at
    names = ", ".join(columns)
    marks = ", ".join(f":{name}" for name in columns)
    with session_scope() as session:
        session.execute(text(f"insert into jobs ({names}) values ({marks})"), columns)
    return job_id


def add_shot(
    job_id,
    position,
    photo_id,
    status="pending",
    round=0,
    failure_reason=None,
    status_detail=None,
    removed=0,
) -> str:
    shot_id = str(uuid.uuid4())
    with session_scope() as session:
        session.execute(
            text(
                "insert into job_shots (id, job_id, position, room, photo_id, movement_name,"
                " movement_prompt, model, length_s, status, status_detail, failure_reason,"
                " round, removed)"
                " values (:i, :j, :pos, 'living', :ph, 'dolly_in', 'Slow dolly in.',"
                " 'google/veo-3.1', 3.0, :s, :d, :f, :r, :rm)"
            ),
            {
                "i": shot_id,
                "j": job_id,
                "pos": position,
                "ph": photo_id,
                "s": status,
                "d": status_detail,
                "f": failure_reason,
                "r": round,
                "rm": removed,
            },
        )
    return shot_id


def add_attempt(shot_id, attempt_no, status, clip_key=None, round=0, requested_s=3.0) -> str:
    attempt_id = str(uuid.uuid4())
    with session_scope() as session:
        session.execute(
            text(
                "insert into attempts (id, job_shot_id, round, attempt_no, prompt, model,"
                " requested_s, status, clip_key, started_at)"
                " values (:i, :s, :r, :n, 'Slow dolly in.', 'google/veo-3.1', :q, :st, :k,"
                " '2026-10-19T08:00:00.000Z')"
            ),
            {
                "i": attempt_id,
                "s": shot_id,
                "r": round,
                "n": attempt_no,
                "st": status,
                "k": clip_key,
                "q": requested_s,
            },
        )
    return attempt_id


def set_final_attempt(shot_id, attempt_id) -> None:
    with session_scope() as session:
        session.execute(
            text("update job_shots set final_attempt_id = :a where id = :i"),
            {"a": attempt_id, "i": shot_id},
        )


def job_row(job_id) -> dict:
    with session_scope() as session:
        row = session.execute(text("select * from jobs where id = :i"), {"i": job_id}).mappings()
        return dict(row.one())


def shot_rows(job_id) -> dict[int, dict]:
    """The job's job_shots rows keyed by position."""
    with session_scope() as session:
        rows = session.execute(
            text("select * from job_shots where job_id = :i"), {"i": job_id}
        ).mappings()
        return {row["position"]: dict(row) for row in rows}
