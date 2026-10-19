"""FakeProviders for the five chat calls: fixed answers, rows at cost 0, scripted failures."""

import io

import pytest
from PIL import Image
from sqlalchemy import select

from app.db.base import session_scope
from app.db.schema import init_db
from app.photoshoots.models import Photoshoot
from app.providers import fake, interface
from app.providers.errors import ProviderError
from app.providers.models import ProviderCall
from app.shared.enums import Room
from app.shared.types import ClipCheck, EditCheck, PlannedShot


@pytest.fixture(autouse=True)
def _fresh_fake():
    fake.reset()
    init_db()
    with session_scope() as session:
        session.add(Photoshoot(id="ps-1"))
    yield
    fake.reset()


def read_rows() -> list[ProviderCall]:
    with session_scope() as session:
        return list(
            session.scalars(select(ProviderCall).order_by(ProviderCall.started_at, ProviderCall.id))
        )


def jpeg(size=(64, 48)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "gray").save(buffer, "JPEG")
    return buffer.getvalue()


def check_clip():
    return interface.check_clip("clip.mp4", [jpeg()], jpeg(), {"jobShotId": None})


def test_fake_fails_on_demand():
    fake.fail_on("check_clip", 2, "out_of_credit")

    first = check_clip()
    with pytest.raises(ProviderError) as caught:
        check_clip()

    assert isinstance(first, ClipCheck) and first.passed is True
    assert caught.value.kind == "out_of_credit"
    rows = read_rows()
    assert [r.kind for r in rows] == ["check_clip", "check_clip"]
    assert [r.status for r in rows] == ["ok", "error"]
    assert [r.error_kind for r in rows] == [None, "out_of_credit"]
    assert [r.cost_usd for r in rows] == [0, 0]


def test_fake_answers_every_chat_call():
    ids = {"photoshootId": "ps-1"}
    photos = [{"photoId": "a", "jpegBytes": jpeg()}, {"photoId": "b", "jpegBytes": jpeg()}]

    labels = interface.label_photos(photos, "ps-1")
    plan = interface.plan_shots(
        "calm",
        40.0,
        [{"photoId": "a", "room": Room.kitchen}, {"photoId": "b", "room": Room.bedroom}],
        {"push_in": "Push in."},
        [4.0, 6.0, 8.0],
        ids,
    )
    edited = interface.edit_photo(jpeg(), "brighten", ids)
    edit_check = interface.check_edit(jpeg(), edited, ids)

    assert [label["photoId"] for label in labels] == ["a", "b"]
    assert all(isinstance(label["room"], Room) and label["room"] != Room.other for label in labels)
    assert labels[0]["room"] != labels[1]["room"] and labels[0]["subject"]
    shots = plan["shots"]
    assert all(isinstance(shot, PlannedShot) for shot in shots)
    assert [(s.photo_id, s.room, s.movement_name, s.length_s) for s in shots] == [
        ("a", Room.kitchen, "push_in", 4.0),
        ("b", Room.bedroom, "push_in", 4.0),
    ]
    assert plan["notes"] == ""
    with Image.open(io.BytesIO(edited)) as image:
        assert image.format == "JPEG" and image.size[0] * 9 == image.size[1] * 16
    assert isinstance(edit_check, EditCheck) and edit_check.architecture_changed is False
    rows = read_rows()
    assert [r.kind for r in rows] == ["label_photos", "plan_shots", "edit_photo", "check_edit"]
    assert all(r.status == "ok" and r.cost_usd == 0 for r in rows)


def test_reset_clears_scripts():
    fake.fail_on("check_clip", 2, "timeout")
    check_clip()
    fake.reset()

    check_clip()
    assert check_clip().passed is True


@pytest.mark.parametrize("photo", [{"photoId": "a", "room": None}, {"room": "kitchen"}])
def test_bad_photo_input_closes_row_as_provider_error(photo):
    if "photoId" not in photo:
        with pytest.raises(ProviderError) as caught:
            interface.plan_shots("x", 40.0, [photo], {}, [4.0], {})
        assert caught.value.kind == "bad_response"
        rows = read_rows()
        assert [(r.status, r.error_kind) for r in rows] == [("error", "bad_response")]
        assert rows[0].finished_at is not None
        return
    result = interface.plan_shots("x", 40.0, [photo], {}, [4.0], {})
    assert result["shots"][0].room == Room.other
    rows = read_rows()
    assert [r.status for r in rows] == ["ok"] and rows[0].finished_at is not None


def test_label_photos_without_id_closes_row():
    with pytest.raises(ProviderError):
        interface.label_photos([{}], "ps-1")
    rows = read_rows()
    assert [r.status for r in rows] == ["error"] and rows[0].finished_at is not None
