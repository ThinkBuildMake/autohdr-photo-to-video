"""Hand-written synthetic jobs and shots for the Comparison tests (raw SQL, test-only)."""

import uuid

from sqlalchemy import text

from app.db.base import session_scope
from app.db.schema import init_db

FAILURE = {"failed": "provider_error", "skipped": "no_photo"}


def _run(sql: str, **params) -> None:
    with session_scope() as session:
        session.execute(text(sql), params)


def add_job(
    song_id,
    status="ready",
    style_id=None,
    style_text="t",
    video_key="default",
    label="12 Oak Street",
    purpose="reproduction",
    fps=30,
) -> str:
    init_db()
    job_id, shoot_id = str(uuid.uuid4()), str(uuid.uuid4())
    if video_key == "default":
        video_key = f"jobs/{job_id}/video-v1.mp4"
    _run("insert into photoshoots (id, label) values (:i, :l)", i=shoot_id, l=label)
    _run(
        "insert into jobs (id, style_id, style_text, photoshoot_id, song_id, song_offset_s, fps,"
        " plan_status, status, video_key, purpose) values (:i, :st, :t, :p, :s, 0, :fps, 'ready',"
        " :status, :vk, :purpose)",
        i=job_id,
        st=style_id,
        t=style_text,
        p=shoot_id,
        s=song_id,
        status=status,
        vk=video_key,
        purpose=purpose,
        fps=fps,
    )
    return job_id


def add_shot(
    job_id,
    position,
    length_s=3.0,
    status="passed",
    transition="cut",
    movement="dolly_in",
    model="google/veo-3.1",
    model_used=None,
    edited_at=None,
    removed=0,
) -> None:
    _run(
        "insert into job_shots (id, job_id, position, room, movement_name, movement_prompt, model,"
        " length_s, transition, transition_s, status, failure_reason, model_used, edited_at,"
        " removed) values (:i, :j, :p, 'living', :mv, 'm', :m, :len, :tr, :ts, :st, :fr, :mu,"
        " :ea, :rm)",
        i=str(uuid.uuid4()),
        j=job_id,
        p=position,
        mv=movement,
        m=model,
        len=length_s,
        tr=transition,
        ts=0.5 if transition == "crossfade" else 0.0,
        st=status,
        fr=FAILURE.get(status),
        mu=model_used,
        ea=edited_at,
        rm=removed,
    )


def add_shots(job_id, lengths, **kwargs) -> None:
    for position, length_s in enumerate(lengths, start=1):
        add_shot(job_id, position, length_s, **kwargs)


def add_cut_check(job_id, position, expected_s, detected_s) -> None:
    error_s = None if detected_s is None else round(detected_s - expected_s, 3)
    _run(
        "insert into cut_checks (job_id, position, expected_s, detected_s, error_s, transition)"
        " values (:j, :p, :e, :d, :err, 'cut')",
        j=job_id,
        p=position,
        e=expected_s,
        d=detected_s,
        err=error_s,
    )


def cut_rows(job_id) -> list[dict]:
    with session_scope() as session:
        result = session.execute(
            text("select * from cut_checks where job_id = :j order by position"), {"j": job_id}
        )
        return [dict(r._mapping) for r in result]


def job_status(job_id) -> str:
    with session_scope() as session:
        return session.scalar(text("select status from jobs where id = :i"), {"i": job_id})
