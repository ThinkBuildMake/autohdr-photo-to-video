"""Hand-written synthetic rows for the Jobs worker tests (raw SQL, test-only)."""

import uuid

from sqlalchemy import text

from app.db.base import session_scope
from app.db.schema import init_db


def _uid() -> str:
    return str(uuid.uuid4())


def _run(sql: str, **params) -> None:
    with session_scope() as session:
        session.execute(text(sql), params)


def add_shoot(n_photos: int = 3) -> tuple[str, list[str]]:
    init_db()
    shoot = _uid()
    photos = []
    _run("insert into photoshoots (id) values (:i)", i=shoot)
    for position in range(1, n_photos + 1):
        photo = _uid()
        _run(
            "insert into photos (id,photoshoot_id,position,original_name,content_type,"
            "size_bytes,file_key) values (:i,:s,:p,'a.jpg','image/jpeg',1000,'k')",
            i=photo,
            s=shoot,
            p=position,
        )
        photos.append(photo)
    return shoot, photos


def add_job(
    photoshoot_id,
    song_id,
    status="queued",
    submitted_at=None,
    created_at=None,
    stop_reason=None,
    video_key=None,
    video_version=0,
    first_finished_at=None,
    started_at=None,
    deadline_at=None,
) -> str:
    job = _uid()
    _run(
        "insert into jobs (id,style_text,photoshoot_id,song_id,song_offset_s,fps,status,"
        "stop_reason,submitted_at,created_at,video_key,video_version,first_finished_at,"
        "started_at,deadline_at)"
        " values (:i,'t',:p,:s,0,30,:st,:sr,:sub,"
        "coalesce(:cr,strftime('%Y-%m-%dT%H:%M:%fZ','now')),:vk,:vv,:ff,:sa,:da)",
        i=job,
        p=photoshoot_id,
        s=song_id,
        st=status,
        sr=stop_reason,
        sub=submitted_at,
        cr=created_at,
        vk=video_key,
        vv=video_version,
        ff=first_finished_at,
        sa=started_at,
        da=deadline_at,
    )
    return job


def add_shot(
    job_id,
    position,
    photo_id=None,
    status="pending",
    round=0,
    failure_reason=None,
    final_attempt_id=None,
    removed=0,
) -> str:
    shot = _uid()
    _run(
        "insert into job_shots (id,job_id,position,room,photo_id,movement_name,movement_prompt,"
        "model,length_s,transition,transition_s,status,failure_reason,round,removed)"
        " values (:i,:j,:p,'living',:ph,'dolly_in','m','google/veo-3.1',3,'cut',0,:st,:fr,:r,:rm)",
        i=shot,
        j=job_id,
        p=position,
        ph=photo_id,
        st=status,
        fr=failure_reason,
        r=round,
        rm=removed,
    )
    if final_attempt_id:
        set_final_attempt(shot, final_attempt_id)
    return shot


def add_attempt(
    shot_id,
    attempt_no,
    round=0,
    status="flagged",
    check_notes=None,
    error=None,
    cost_usd=0.0,
) -> str:
    attempt = _uid()
    _run(
        "insert into attempts (id,job_shot_id,round,attempt_no,prompt,model,requested_s,status,"
        "check_notes,error,cost_usd,started_at)"
        " values (:i,:s,:r,:n,'p','google/veo-3.1',3,:st,:cn,:e,:c,'2026-10-19T09:00:00.000Z')",
        i=attempt,
        s=shot_id,
        r=round,
        n=attempt_no,
        st=status,
        cn=check_notes,
        e=error,
        c=cost_usd,
    )
    return attempt


def set_final_attempt(shot_id, attempt_id) -> None:
    _run("update job_shots set final_attempt_id=:a where id=:i", a=attempt_id, i=shot_id)


def add_provider_call(job_id, cost_usd) -> str:
    call = _uid()
    _run(
        "insert into provider_calls (id,kind,model,job_id,cost_usd,started_at)"
        " values (:i,'clip','m',:j,:c,'2026-10-19T09:00:00.000Z')",
        i=call,
        j=job_id,
        c=cost_usd,
    )
    return call


def rows(sql: str, **params) -> list[dict]:
    with session_scope() as session:
        return [dict(r._mapping) for r in session.execute(text(sql), params)]


def row(table: str, id: str) -> dict:
    return rows(f"select * from {table} where id = :i", i=id)[0]
