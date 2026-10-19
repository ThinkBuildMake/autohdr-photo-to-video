from sqlalchemy import text

from app.db.base import session_scope
from app.photoshoots import labelling, stubs
from app.providers.errors import ProviderError
from tests.photoshoots.conftest import seed_shoot


def _shoot_status(shoot_id):
    with session_scope() as session:
        return session.execute(
            text("select status from photoshoots where id=:i"), {"i": shoot_id}
        ).scalar_one()


def _photos(shoot_id):
    with session_scope() as session:
        return session.execute(
            text(
                "select id, room, subject, width, height from photos"
                " where photoshoot_id=:i order by position"
            ),
            {"i": shoot_id},
        ).all()


def _labeller(room, subject, seen=None):
    def label(photos, photoshoot_id):
        if seen is not None:
            seen.extend(p["photoId"] for p in photos)
        return [{"photoId": p["photoId"], "room": room, "subject": subject} for p in photos]

    return label


def test_labeller_failure_marks_shoot_label_failed(monkeypatch):
    shoot_id, _ = seed_shoot(["uploaded", "uploaded"])

    def boom(photos, photoshoot_id):
        raise ProviderError("failed", "boom")

    monkeypatch.setattr(stubs, "label_photos", boom)
    labelling.label_photoshoot(shoot_id)
    assert _shoot_status(shoot_id) == "label_failed"
    assert all(row.room is None for row in _photos(shoot_id))


def test_labels_written(monkeypatch):
    shoot_id, ids = seed_shoot(["uploaded", "missing", "uploaded"])
    seen: list[str] = []
    monkeypatch.setattr(stubs, "label_photos", _labeller("kitchen", "kitchen island", seen))
    labelling.label_photoshoot(shoot_id)
    assert _shoot_status(shoot_id) == "ready"
    assert seen == [ids[0], ids[2]]
    rows = _photos(shoot_id)
    for row in (rows[0], rows[2]):
        assert (row.room, row.subject, row.width, row.height) == (
            "kitchen",
            "kitchen island",
            1920,
            1080,
        )
    assert rows[1].room is None


def test_relabel_interrupted_starts_labelling(monkeypatch):
    monkeypatch.setattr(stubs, "label_photos", _labeller("kitchen", "k"))
    busy, _ = seed_shoot(["uploaded"])
    done, _ = seed_shoot(["uploaded"], shoot_status="ready")
    assert labelling.relabel_interrupted() == [busy]
    labelling.wait_idle()
    assert _shoot_status(busy) == "ready"
    assert _photos(busy)[0].room == "kitchen"
    assert _photos(done)[0].room is None


def test_unknown_room_becomes_other(monkeypatch):
    shoot_id, _ = seed_shoot(["uploaded"])
    monkeypatch.setattr(stubs, "label_photos", _labeller("garage", "a garage"))
    labelling.label_photoshoot(shoot_id)
    assert _photos(shoot_id)[0].room == "other"
