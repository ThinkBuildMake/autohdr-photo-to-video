import pytest

from app.jobs.stubs import STUB_JOB_ID
from app.library.stubs import GOLDEN_HOUR_ID
from tests.support.library_rows import stub_presets  # noqa: F401

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
