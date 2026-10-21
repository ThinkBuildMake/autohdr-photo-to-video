import pytest
from sqlalchemy import text

from app.db.base import session_scope
from app.library import service
from app.library.schemas import StyleCreate, StyleUpdate
from tests.support.library_rows import add_job_row, add_song


def _create(song_id, name="Golden hour"):
    return service.create_style(
        StyleCreate(name=name, author_name="Sam", style_text="Slow and warm.", song_id=song_id)
    )


def test_set_reference_job_is_returned_by_get_style(client):
    song_id = add_song()
    style = _create(song_id)
    job_id = add_job_row(song_id)

    service.set_reference_job(style.id, job_id)

    assert service.get_style(style.id).reference_job_id == job_id
    summaries = client.get("/api/styles").json()["styles"]
    assert summaries[0]["hasReference"] is True
    assert client.get(f"/api/styles/{style.id}").json()["referenceVideoUrl"] is None


def test_set_reference_job_on_unknown_style_is_refused(client):
    with pytest.raises(service.StyleNotFound):
        service.set_reference_job("nope", "job")


def test_set_reference_job_with_unknown_job_is_404(client):
    style = _create(add_song())

    with pytest.raises(Exception) as caught:
        service.set_reference_job(style.id, "no-such-job")

    assert caught.value.code == "job_not_found"


def test_get_style_has_no_video_field(client):
    style = _create(add_song())

    dumped = service.get_style(style.id).model_dump(by_alias=True)

    offending = [k for k in dumped if "video" in k.lower() or "frame" in k.lower()]
    assert offending == []
    assert "storyboard" not in dumped


def test_updating_a_style_leaves_existing_jobs_unchanged(client):
    first = add_song()
    second = add_song(title="Track B", source_url="https://example.com/music/track-b")
    style = _create(first)
    job_id = add_job_row(first, style_id=style.id, style_text="Old text")

    service.update_style(style.id, StyleUpdate(style_text="New text", fps=24, song_id=second))

    with session_scope() as session:
        row = session.execute(
            text("select style_text, song_id, song_offset_s, fps from jobs where id = :i"),
            {"i": job_id},
        ).one()
    assert tuple(row) == ("Old text", first, 0, 30)
    assert service.get_style(style.id).style_text == "New text"


@pytest.mark.parametrize(
    "update, cleared",
    [
        ({"style_text": "New sentence."}, True),
        ({"style_text": "Slow and warm."}, False),
        ({"name": "Renamed"}, False),
        ({"song_id": "other"}, True),
        ({"song_id": "same"}, False),
        ({"fps": 24}, True),
        ({"fps": 30}, False),
    ],
)
def test_only_changed_text_song_or_fps_clears_reference(client, update, cleared):
    song = add_song()
    if update.get("song_id") == "other":
        update = {"song_id": add_song(title="Track B")}
    elif update.get("song_id") == "same":
        update = {"song_id": song}
    style = _create(song)
    job = add_job_row(song, style_id=style.id, style_text=style.style_text)
    service.set_reference_job(style.id, job)

    updated = service.update_style(style.id, StyleUpdate(**update))

    assert updated.reference_job_id == (None if cleared else job)
    with session_scope() as session:
        assert (
            session.execute(
                text("select style_text from jobs where id=:id"), {"id": job}
            ).scalar_one()
            == "Slow and warm."
        )


def test_rejected_update_keeps_reference_and_text(client):
    song = add_song()
    style = _create(song)
    other = _create(song, name="Taken")
    job = add_job_row(song, style_id=style.id)
    service.set_reference_job(style.id, job)

    with pytest.raises(Exception) as caught:
        service.update_style(style.id, StyleUpdate(name=other.name, style_text="Changed"))

    assert caught.value.code == "name_taken"
    saved = service.get_style(style.id)
    assert (saved.style_text, saved.reference_job_id) == (style.style_text, job)
