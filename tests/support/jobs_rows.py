"""Rows and fixtures the Jobs planning tests need: shoots, draft jobs, a scripted planner."""

import uuid

import pytest
from sqlalchemy import text

from app.db.base import session_scope
from app.db.schema import init_db
from app.jobs import planning, stubs
from app.jobs.plan_rules import MOVEMENTS

ROOMS = ["exterior_front", "living", "kitchen", "bedroom", "bathroom", "exterior_back"]
VEO = "google/veo-3.1"


def add_ready_shoot(n_photos=6, status="ready") -> tuple[str, list[str]]:
    """Raw-insert a photoshoot with uploaded photos; returns (photoshoot_id, photo_ids)."""
    init_db()
    photoshoot_id = str(uuid.uuid4())
    photo_ids = [str(uuid.uuid4()) for _ in range(n_photos)]
    with session_scope() as session:
        session.execute(
            text("insert into photoshoots (id, label, status) values (:i, 'Test shoot', :s)"),
            {"i": photoshoot_id, "s": status},
        )
        for position, photo_id in enumerate(photo_ids, start=1):
            session.execute(
                text(
                    "insert into photos (id, photoshoot_id, position, original_name,"
                    " content_type, size_bytes, file_key, status, room)"
                    " values (:i, :p, :n, :name, 'image/jpeg', 1000, :k, 'uploaded', :r)"
                ),
                {
                    "i": photo_id,
                    "p": photoshoot_id,
                    "n": position,
                    "name": f"photo-{position}.jpg",
                    "k": f"photos/{photo_id}.jpg",
                    "r": ROOMS[(position - 1) % len(ROOMS)],
                },
            )
    return photoshoot_id, photo_ids


def add_draft_job(
    photoshoot_id,
    song_id,
    style_id=None,
    style_text="Slow Dolly In through each room",
    plan_status="planning",
    fps=30,
    song_offset_s=0,
) -> str:
    init_db()
    job_id = str(uuid.uuid4())
    with session_scope() as session:
        session.execute(
            text(
                "insert into jobs (id, style_id, style_text, photoshoot_id, song_id,"
                " song_offset_s, fps, plan_status, status)"
                " values (:i, :st, :t, :p, :s, :o, :f, :ps, 'draft')"
            ),
            {
                "i": job_id,
                "st": style_id,
                "t": style_text,
                "p": photoshoot_id,
                "s": song_id,
                "o": song_offset_s,
                "f": fps,
                "ps": plan_status,
            },
        )
    return job_id


def planned_shot(position, photo_id, **changes) -> dict:
    """A valid camelCase PlannedShot; keyword changes override fields (camelCase keys)."""
    shot = {
        "position": position,
        "room": ROOMS[(position - 1) % len(ROOMS)],
        "photoId": photo_id,
        "photoEditPrompts": [],
        "movementName": "dolly_in",
        "movementPrompt": MOVEMENTS["dolly_in"],
        "speed": "slow",
        "model": VEO,
        "lengthS": 4.0,
        "transition": "cut",
        "transitionS": 0.0,
        "planNote": f"Shot {position} note.",
    }
    shot.update(changes)
    return shot


class ScriptedPlanner:
    """Stands in for stubs.plan_shots: answers a queue of {shots, notes}, records each call."""

    def __init__(self):
        self.answers: list = []
        self.calls: list[dict] = []

    def queue(self, shots, notes=""):
        self.answers.append({"shots": shots, "notes": notes})

    def __call__(
        self, style_text, song_duration_s, photos, movements, allowed_lengths, ids
    ) -> dict:
        self.calls.append(
            {
                "style_text": style_text,
                "song_duration_s": song_duration_s,
                "photos": photos,
                "movements": movements,
                "allowed_lengths": allowed_lengths,
                "ids": ids,
            }
        )
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def scripted_planner(monkeypatch):
    planner = ScriptedPlanner()
    monkeypatch.setattr(stubs, "plan_shots", planner)
    return planner


@pytest.fixture
def planning_idle():
    yield
    planning.wait_idle()
