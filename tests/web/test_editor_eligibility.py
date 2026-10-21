"""Real editor page reads and eligibility, without a browser."""

import pytest
from sqlalchemy import text

from app.db.base import session_scope
from tests.support import fixtures
from tests.support.queue_rows import add_job, add_shoot, add_shot, add_song

web_client = fixtures.client


@pytest.mark.parametrize(
    "status", ["ready", "ready_with_failures", "queued", "running", "draft", "stopped"]
)
def test_only_finished_jobs_enable_editor(web_client, bucket, status):
    shoot, photos = add_shoot()
    job = add_job(
        shoot,
        add_song(),
        status=status,
        stop_reason="worker_restarted" if status == "stopped" else None,
    )
    add_shot(job, 1, photos[0])

    response = web_client.get(f"/jobs/{job}/edit")

    assert response.status_code == 200
    disabled = '<fieldset class="ed-controls" disabled>' in response.text
    assert disabled == (status not in ("ready", "ready_with_failures"))
    if status in ("draft", "stopped"):
        assert "This video is not ready to edit" in response.text


def test_editor_only_offers_uploaded_photos_and_shows_stored_previews(web_client, bucket):
    shoot, photos = add_shoot(n_photos=4)
    job = add_job(shoot, add_song(), status="ready")
    shot = add_shot(job, 1, photos[0])
    with session_scope() as session:
        for photo, status in zip(
            photos[1:], ["awaiting_upload", "missing", "too_large"], strict=True
        ):
            session.execute(
                text("update photos set status=:s where id=:i"), {"s": status, "i": photo}
            )
        session.execute(
            text(
                "update job_shots set cropped_key='actual/crop.jpg', "
                "edit_status='crop_only' where id=:i"
            ),
            {"i": shot},
        )

    response = web_client.get(f"/jobs/{job}/edit")

    assert f'<option value="{photos[0]}"' in response.text
    for photo in photos[1:]:
        assert f'<option value="{photo}"' not in response.text
    assert 'class="original-photo"' in response.text
    assert 'class="first-frame"' in response.text
    assert "actual/crop.jpg" in response.text
    assert "Cropped first frame" in response.text


def test_missing_previews_are_explicit(web_client, bucket):
    shoot, _ = add_shoot()
    job = add_job(shoot, add_song(), status="ready")
    add_shot(job, 1, None)

    response = web_client.get(f"/jobs/{job}/edit")

    assert "Original photo unavailable" in response.text
    assert "First frame unavailable" in response.text
