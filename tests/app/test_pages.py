import pytest

from tests.support.library_rows import stub_presets  # noqa: F401
from tests.support.stub_data import GOLDEN_HOUR_ID, STUB_JOB_ID

pytestmark = pytest.mark.usefixtures("stub_presets")

PAGES = [
    "/",
    "/new",
    "/jobs",
    f"/jobs/{STUB_JOB_ID}",
    f"/jobs/{STUB_JOB_ID}/edit",
    "/styles/new",
    f"/styles/{GOLDEN_HOUR_ID}/reproductions",
]


@pytest.mark.parametrize("path", PAGES)
def test_page_answers_html(client, path):
    if path in (f"/jobs/{STUB_JOB_ID}", f"/jobs/{STUB_JOB_ID}/edit"):
        from tests.support.queue_rows import add_job, add_shoot, add_song

        shoot_id, _ = add_shoot()
        suffix = "/edit" if path.endswith("/edit") else ""
        path = f"/jobs/{add_job(shoot_id, add_song())}{suffix}"
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_styles_page_lists_presets_and_loads_htmx(client):
    html = client.get("/").text

    assert "Golden hour" in html
    assert "Crisp modern" in html
    assert '<script src="/static/htmx.min.js">' in html


def test_htmx_is_served_locally(client):
    assert client.get("/static/htmx.min.js").status_code == 200


@pytest.mark.parametrize(
    "path", ["/jobs/unknown-id", "/jobs/unknown-id/edit", "/styles/unknown-id/reproductions"]
)
def test_unknown_id_renders_the_page_with_the_message_and_404(client, path):
    response = client.get(path)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert "No " in response.text and "unknown-id" in response.text


def test_stored_job_shows_edit_outcome_and_attempt_count(client):
    from sqlalchemy import text

    from app.db.base import session_scope
    from tests.support.queue_rows import add_attempt, add_job, add_shoot, add_shot, add_song

    shoot_id, photos = add_shoot()
    job_id = add_job(shoot_id, add_song(), status="running")
    first = add_shot(job_id, 1, photos[0], status="checking")
    second = add_shot(job_id, 2, photos[1], status="editing")
    add_attempt(first, 1, "flagged")
    add_attempt(first, 2, "running")
    with session_scope() as session:
        session.execute(text("update job_shots set edit_status='edited' where id=:i"), {"i": first})
        session.execute(
            text(
                "update job_shots set edit_status='crop_only', "
                "edit_note='Changed a window' where id=:i"
            ),
            {"i": second},
        )

    html = client.get(f"/jobs/{job_id}").text

    assert "Photo edited" in html
    assert "Attempts: 2 of 4" in html
    assert "Attempts: 0 of 4" in html
    assert "crop only): Changed a window" in html
    assert "never more than 30" not in html
    assert "Target: under 10 minutes" in html
