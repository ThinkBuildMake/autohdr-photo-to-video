import sqlite3
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db.base import get_engine, session_scope
from app.db.schema import TABLES, init_db

NINE = {
    "songs",
    "styles",
    "photoshoots",
    "photos",
    "jobs",
    "job_shots",
    "attempts",
    "provider_calls",
    "cut_checks",
}

NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"  # SQLite stores it without the outer parentheses

# table -> {column: (type, notnull, default)}; default None = no default.
COLUMNS = {
    "songs": {
        "id": ("TEXT", 1, None),
        "title": ("TEXT", 1, None),
        "artist": ("TEXT", 1, None),
        "licence_code": ("TEXT", 1, None),
        "source_url": ("TEXT", 1, None),
        "file_key": ("TEXT", 1, None),
        "duration_s": ("REAL", 1, None),
        "created_at": ("TEXT", 1, NOW),
    },
    "styles": {
        "id": ("TEXT", 1, None),
        "name": ("TEXT", 1, None),
        "author_name": ("TEXT", 1, None),
        "style_text": ("TEXT", 1, None),
        "song_id": ("TEXT", 1, None),
        "song_offset_s": ("REAL", 1, "0"),
        "fps": ("INTEGER", 1, "30"),
        "demo_photoshoot_id": ("TEXT", 0, None),
        "reference_job_id": ("TEXT", 0, None),
        "created_at": ("TEXT", 1, NOW),
        "updated_at": ("TEXT", 1, NOW),
    },
    "photoshoots": {
        "id": ("TEXT", 1, None),
        "label": ("TEXT", 0, None),
        "status": ("TEXT", 1, "'awaiting_upload'"),
        "created_at": ("TEXT", 1, NOW),
    },
    "photos": {
        "id": ("TEXT", 1, None),
        "photoshoot_id": ("TEXT", 1, None),
        "position": ("INTEGER", 1, None),
        "original_name": ("TEXT", 1, None),
        "content_type": ("TEXT", 1, None),
        "size_bytes": ("INTEGER", 1, None),
        "file_key": ("TEXT", 1, None),
        "status": ("TEXT", 1, "'awaiting_upload'"),
        "width": ("INTEGER", 0, None),
        "height": ("INTEGER", 0, None),
        "room": ("TEXT", 0, None),
        "subject": ("TEXT", 0, None),
    },
    "jobs": {
        "id": ("TEXT", 1, None),
        "style_id": ("TEXT", 0, None),
        "style_text": ("TEXT", 1, None),
        "photoshoot_id": ("TEXT", 1, None),
        "plan_status": ("TEXT", 1, "'planning'"),
        "plan_notes": ("TEXT", 0, None),
        "purpose": ("TEXT", 1, "'video'"),
        "status": ("TEXT", 1, "'draft'"),
        "stop_reason": ("TEXT", 0, None),
        "song_id": ("TEXT", 1, None),
        "song_offset_s": ("REAL", 1, None),
        "created_at": ("TEXT", 1, NOW),
        "first_submitted_at": ("TEXT", 0, None),
        "submitted_at": ("TEXT", 0, None),
        "started_at": ("TEXT", 0, None),
        "deadline_at": ("TEXT", 0, None),
        "finished_at": ("TEXT", 0, None),
        "first_finished_at": ("TEXT", 0, None),
        "fps": ("INTEGER", 1, None),
        "video_key": ("TEXT", 0, None),
        "video_version": ("INTEGER", 1, "0"),
        "video_duration_s": ("REAL", 0, None),
        "video_width": ("INTEGER", 0, None),
        "video_height": ("INTEGER", 0, None),
        "video_fps": ("REAL", 0, None),
        "total_cost_usd": ("REAL", 1, "0"),
    },
    "job_shots": {
        "id": ("TEXT", 1, None),
        "job_id": ("TEXT", 1, None),
        "removed": ("INTEGER", 1, "0"),
        "needs_new_clip": ("INTEGER", 1, "0"),
        "edited_at": ("TEXT", 0, None),
        "clip_inputs": ("TEXT", 0, None),
        "position": ("INTEGER", 1, None),
        "room": ("TEXT", 1, None),
        "photo_id": ("TEXT", 0, None),
        "photo_edit_prompts": ("TEXT", 1, "'[]'"),
        "movement_name": ("TEXT", 1, None),
        "movement_prompt": ("TEXT", 1, None),
        "speed": ("TEXT", 1, "'slow'"),
        "model": ("TEXT", 1, None),
        "length_s": ("REAL", 1, None),
        "transition": ("TEXT", 1, "'cut'"),
        "transition_s": ("REAL", 1, "0"),
        "plan_note": ("TEXT", 0, None),
        "status": ("TEXT", 1, "'pending'"),
        "status_detail": ("TEXT", 0, None),
        "failure_reason": ("TEXT", 0, None),
        "round": ("INTEGER", 1, "0"),
        "cropped_key": ("TEXT", 0, None),
        "edited_key": ("TEXT", 0, None),
        "edit_status": ("TEXT", 0, None),
        "edit_note": ("TEXT", 0, None),
        "model_used": ("TEXT", 0, None),
        "final_attempt_id": ("TEXT", 0, None),
        "updated_at": ("TEXT", 1, NOW),
    },
    "attempts": {
        "id": ("TEXT", 1, None),
        "job_shot_id": ("TEXT", 1, None),
        "round": ("INTEGER", 1, None),
        "attempt_no": ("INTEGER", 1, None),
        "prompt": ("TEXT", 1, None),
        "model": ("TEXT", 1, None),
        "requested_s": ("REAL", 1, None),
        "status": ("TEXT", 1, "'running'"),
        "clip_key": ("TEXT", 0, None),
        "check_ai_score": ("REAL", 0, None),
        "check_match_score": ("REAL", 0, None),
        "check_notes": ("TEXT", 0, None),
        "error": ("TEXT", 0, None),
        "cost_usd": ("REAL", 1, "0"),
        "started_at": ("TEXT", 1, None),
        "finished_at": ("TEXT", 0, None),
    },
    "provider_calls": {
        "id": ("TEXT", 1, None),
        "kind": ("TEXT", 1, None),
        "model": ("TEXT", 1, None),
        "job_id": ("TEXT", 0, None),
        "job_shot_id": ("TEXT", 0, None),
        "attempt_id": ("TEXT", 0, None),
        "photoshoot_id": ("TEXT", 0, None),
        "provider_request_id": ("TEXT", 0, None),
        "status": ("TEXT", 1, "'running'"),
        "error_kind": ("TEXT", 0, None),
        "error_message": ("TEXT", 0, None),
        "output_seconds": ("REAL", 0, None),
        "cost_usd": ("REAL", 1, "0"),
        "cost_source": ("TEXT", 1, "'reported'"),
        "started_at": ("TEXT", 1, None),
        "finished_at": ("TEXT", 0, None),
    },
    "cut_checks": {
        "job_id": ("TEXT", 1, None),
        "position": ("INTEGER", 1, None),
        "expected_s": ("REAL", 1, None),
        "detected_s": ("REAL", 0, None),
        "error_s": ("REAL", 0, None),
        "transition": ("TEXT", 1, None),
        "checked_at": ("TEXT", 1, NOW),
    },
}


def uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db():
    init_db()
    return get_engine()


def raw(sql: str, **params):
    """Run one statement in its own short transaction."""
    with session_scope() as s:
        return s.execute(text(sql), params)


def add_song(song_id=None, licence="BY-NC"):
    song_id = song_id or uid()
    raw(
        "insert into songs (id,title,artist,licence_code,source_url,file_key,duration_s)"
        " values (:i,'t','a',:l,'u','k',60)",
        i=song_id,
        l=licence,
    )
    return song_id


def add_style(song_id, name="s", fps=30, style_text="text"):
    sid = uid()
    raw(
        "insert into styles (id,name,author_name,style_text,song_id,fps)"
        " values (:i,:n,'me',:t,:s,:f)",
        i=sid,
        n=name,
        t=style_text,
        s=song_id,
        f=fps,
    )
    return sid


def add_photoshoot():
    pid = uid()
    raw("insert into photoshoots (id) values (:i)", i=pid)
    return pid


def add_photo(shoot, position=1, size=1000, ctype="image/jpeg"):
    pid = uid()
    raw(
        "insert into photos (id,photoshoot_id,position,original_name,content_type,"
        "size_bytes,file_key)"
        " values (:i,:s,:p,'a.jpg',:c,:z,'k')",
        i=pid,
        s=shoot,
        p=position,
        c=ctype,
        z=size,
    )
    return pid


def add_job(shoot, song, status="draft", stop_reason=None):
    jid = uid()
    raw(
        "insert into jobs (id,style_text,photoshoot_id,song_id,song_offset_s,fps,status,"
        "stop_reason)"
        " values (:i,'t',:p,:s,0,30,:st,:sr)",
        i=jid,
        p=shoot,
        s=song,
        st=status,
        sr=stop_reason,
    )
    return jid


def add_shot(job, position=1, **over):
    values = {
        "length_s": 3,
        "transition": "cut",
        "transition_s": 0,
        "status": "pending",
        "failure_reason": None,
        **over,
    }
    sid = uid()
    raw(
        "insert into job_shots (id,job_id,position,room,movement_name,movement_prompt,model,"
        "length_s,transition,transition_s,status,failure_reason)"
        " values (:i,:j,:p,'living','dolly_in','m','v',:l,:t,:ts,:st,:fr)",
        i=sid,
        j=job,
        p=position,
        l=values["length_s"],
        t=values["transition"],
        ts=values["transition_s"],
        st=values["status"],
        fr=values["failure_reason"],
    )
    return sid


def add_attempt(shot, round_=0, attempt_no=1):
    aid = uid()
    raw(
        "insert into attempts (id,job_shot_id,round,attempt_no,prompt,model,requested_s,started_at)"
        " values (:i,:s,:r,:n,'p','m',3,'2026-01-01T00:00:00Z')",
        i=aid,
        s=shot,
        r=round_,
        n=attempt_no,
    )
    return aid


@pytest.fixture
def base(db):
    song = add_song()
    shoot = add_photoshoot()
    return {"song": song, "shoot": shoot}


def table_names(engine):
    with engine.connect() as c:
        rows = c.execute(
            text("select name from sqlite_master where type='table' and name not like 'sqlite_%'")
        )
        return {r[0] for r in rows}


def test_init_db_creates_exactly_the_nine_tables(db):
    assert table_names(db) == NINE
    assert set(TABLES) == NINE and len(TABLES) == 9


def test_init_db_twice_is_harmless(db):
    init_db()
    init_db()
    assert table_names(db) == NINE


def test_init_db_adds_clip_inputs_to_an_older_job_shots_table(db):
    raw("ALTER TABLE job_shots DROP COLUMN clip_inputs")

    init_db()

    with db.connect() as c:
        names = {r[1] for r in c.execute(text("pragma table_info(job_shots)"))}
    assert "clip_inputs" in names


def test_file_is_created_in_missing_parent_directory(tmp_path, monkeypatch):
    from app.config import reset_settings
    from app.db.base import reset_engine

    reset_engine()
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "deep" / "er" / "x.db"))
    reset_settings()
    init_db()
    assert (tmp_path / "deep" / "er" / "x.db").exists()


@pytest.mark.parametrize("table", sorted(NINE))
def test_columns_not_null_and_defaults_match_architecture(db, table):
    with db.connect() as c:
        info = c.execute(text(f"pragma table_info({table})")).all()
    got = {r[1]: (r[2].upper(), r[3], r[4]) for r in info}
    assert got == COLUMNS[table]


def index_info(engine, table):
    """name -> (unique, partial, [columns])"""
    out = {}
    with engine.connect() as c:
        for r in c.execute(text(f"pragma index_list({table})")).all():
            name, unique, partial = r[1], bool(r[2]), bool(r[4])
            cols = [x[2] for x in c.execute(text(f"pragma index_info({name})")).all()]
            out[name] = (unique, partial, cols)
    return out


def unique_column_sets(engine, table):
    return [cols for (u, _p, cols) in index_info(engine, table).values() if u]


def test_named_indexes_exist(db):
    jobs = index_info(db, "jobs")
    assert jobs["uq_jobs_one_running"] == (True, True, ["status"])
    assert jobs["ix_jobs_status_submitted_at"] == (False, False, ["status", "submitted_at"])
    assert "ix_jobs_created_at" in jobs
    assert index_info(db, "provider_calls")["ix_provider_calls_job_id"] == (
        False,
        False,
        ["job_id"],
    )
    with db.connect() as c:
        sql = c.execute(
            text("select sql from sqlite_master where name='ix_jobs_created_at'")
        ).scalar()
        part = c.execute(
            text("select sql from sqlite_master where name='uq_jobs_one_running'")
        ).scalar()
    assert "created_at DESC" in sql
    assert "WHERE status = 'running'" in part


@pytest.mark.parametrize(
    "table,cols",
    [
        ("photos", ["photoshoot_id", "position"]),
        ("job_shots", ["job_id", "position"]),
        ("attempts", ["job_shot_id", "round", "attempt_no"]),
        ("styles", ["name"]),
    ],
)
def test_unique_keys(db, table, cols):
    assert cols in unique_column_sets(db, table)


def test_cut_checks_primary_key_is_job_id_position(db):
    with db.connect() as c:
        info = c.execute(text("pragma table_info(cut_checks)")).all()
    pk = [r[1] for r in sorted((r for r in info if r[5]), key=lambda r: r[5])]
    assert pk == ["job_id", "position"]


def test_connection_pragmas(db):
    with session_scope() as s:
        assert s.execute(text("pragma foreign_keys")).scalar() == 1
        assert s.execute(text("pragma journal_mode")).scalar() == "wal"
        assert s.execute(text("pragma busy_timeout")).scalar() >= 5000


def test_database_path_comes_from_settings(db):
    assert get_engine().url.database == get_settings().DATABASE_PATH


# ---- check constraints: one violating insert each ----------------------------------------


def v_song_licence(b):
    add_song(licence="CC-BY-ND")


def v_style_fps(b):
    add_style(b["song"], fps=25)


def v_style_text_empty(b):
    add_style(b["song"], style_text="")


def v_style_text_long(b):
    add_style(b["song"], style_text="x" * 4001)


def v_style_name_dupe(b):
    add_style(b["song"], name="dupe")
    add_style(b["song"], name="dupe")


def v_photo_size(b):
    add_photo(b["shoot"], size=26214401)


def v_photo_type(b):
    add_photo(b["shoot"], ctype="video/mp4")


def v_photo_position_dupe(b):
    add_photo(b["shoot"], position=1)
    add_photo(b["shoot"], position=1)


def v_job_status(b):
    add_job(b["shoot"], b["song"], status="bogus")


def v_job_stopped_without_reason(b):
    add_job(b["shoot"], b["song"], status="stopped")


def v_shot_position_dupe(b):
    j = add_job(b["shoot"], b["song"])
    add_shot(j, 1)
    add_shot(j, 1)


def v_shot_status(b):
    add_shot(add_job(b["shoot"], b["song"]), status="bogus")


def v_shot_failed_without_reason(b):
    add_shot(add_job(b["shoot"], b["song"]), status="failed")


def v_shot_length(b):
    add_shot(add_job(b["shoot"], b["song"]), length_s=0)


def v_shot_transition_negative(b):
    add_shot(add_job(b["shoot"], b["song"]), transition_s=-1)


def v_shot_crossfade_without_length(b):
    add_shot(add_job(b["shoot"], b["song"]), transition="crossfade", transition_s=0)


def v_attempt_no_high(b):
    add_attempt(add_shot(add_job(b["shoot"], b["song"])), attempt_no=5)


def v_attempt_no_low(b):
    add_attempt(add_shot(add_job(b["shoot"], b["song"])), attempt_no=0)


def v_attempt_dupe(b):
    s = add_shot(add_job(b["shoot"], b["song"]))
    add_attempt(s, 0, 1)
    add_attempt(s, 0, 1)


def v_cut_check_dupe(b):
    j = add_job(b["shoot"], b["song"])
    for _ in range(2):
        raw(
            "insert into cut_checks (job_id,position,expected_s,transition)"
            " values (:j,1,1.0,'cut')",
            j=j,
        )


VIOLATIONS = [
    v_song_licence,
    v_style_fps,
    v_style_text_empty,
    v_style_text_long,
    v_style_name_dupe,
    v_photo_size,
    v_photo_type,
    v_photo_position_dupe,
    v_job_status,
    v_job_stopped_without_reason,
    v_shot_position_dupe,
    v_shot_status,
    v_shot_failed_without_reason,
    v_shot_length,
    v_shot_transition_negative,
    v_shot_crossfade_without_length,
    v_attempt_no_high,
    v_attempt_no_low,
    v_attempt_dupe,
    v_cut_check_dupe,
]


@pytest.mark.parametrize("violation", VIOLATIONS, ids=lambda f: f.__name__)
def test_constraint_refuses_violating_insert(base, violation):
    with pytest.raises(IntegrityError):
        violation(base)


def test_valid_rows_are_accepted(base):
    add_style(base["song"])
    add_photo(base["shoot"], size=26214400, ctype="image/png")
    job = add_job(base["shoot"], base["song"], status="stopped", stop_reason="out_of_credit")
    shot = add_shot(job, transition="crossfade", transition_s=0.5)
    for n in range(1, 5):
        add_attempt(shot, 0, n)
    with session_scope() as s:
        row = s.execute(text("select created_at from jobs where id=:i"), {"i": job}).scalar()
    assert row.endswith("Z") and "T" in row


def test_enum_values_match_architecture():
    from app.shared.enums import MovementName, Room

    assert len(MovementName) == 12
    assert len(Room) == 12
    assert all(m.value == m.name and m.value.islower() for m in MovementName)


# ---- criterion 4: one running job ---------------------------------------------------------


def test_only_one_job_may_run(base):
    add_job(base["shoot"], base["song"], status="running")
    with pytest.raises(IntegrityError):
        add_job(base["shoot"], base["song"], status="running")


def test_updating_a_queued_job_to_running_is_refused(base):
    add_job(base["shoot"], base["song"], status="running")
    queued = add_job(base["shoot"], base["song"], status="queued")
    with pytest.raises(IntegrityError):
        raw("update jobs set status='running' where id=:i", i=queued)


def test_queued_job_is_accepted_beside_a_running_one(base):
    add_job(base["shoot"], base["song"], status="running")
    add_job(base["shoot"], base["song"], status="queued")
    add_job(base["shoot"], base["song"], status="queued")


def test_running_slot_frees_when_the_job_finishes(base):
    first = add_job(base["shoot"], base["song"], status="running")
    raw("update jobs set status='ready' where id=:i", i=first)
    add_job(base["shoot"], base["song"], status="running")


# ---- criterion 14: foreign keys are on ----------------------------------------------------


def test_job_shot_with_unknown_job_is_refused(db):
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        add_shot("no-such-job")


def test_pragmas_hold_on_a_plain_sqlite_connection_to_the_same_file(db):
    # sanity: the file itself is in WAL mode, so other connections see it
    con = sqlite3.connect(get_settings().DATABASE_PATH)
    try:
        assert con.execute("pragma journal_mode").fetchone()[0] == "wal"
    finally:
        con.close()
