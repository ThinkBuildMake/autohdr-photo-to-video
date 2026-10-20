import pytest

from app.shared.enums import JobStatus
from tests.support.job_screens import JOB_A, JOB_B, job, list_item, stub_jobs  # noqa: F401

pytestmark = pytest.mark.e2e


@pytest.fixture
def two_jobs(stub_jobs):  # noqa: F811
    stub_jobs.items = [
        list_item(
            JOB_B,
            style_name="Crisp modern",
            photoshoot_label="9 Elm Road",
            status=JobStatus.running,
            submitted_at="2026-10-19T17:10:00Z",
            elapsed_s=125.0,
        ),
        list_item(
            JOB_A,
            style_name="Golden hour",
            photoshoot_label="12 Oak Street",
            status=JobStatus.ready,
            submitted_at="2026-10-19T17:00:00Z",
            elapsed_s=300.0,
        ),
    ]
    stub_jobs.add(job(JOB_A))
    return stub_jobs


def test_jobs_are_listed_newest_first(page, live_server, two_jobs):
    page.goto(live_server + "/jobs")

    rows = page.locator("table.jobs tbody tr")
    assert rows.count() == 2
    running, ready = rows.nth(0), rows.nth(1)
    for cell in ("9 Elm Road", "Crisp modern", "2 min 5 s"):
        assert cell in running.inner_text()
    for cell in ("12 Oak Street", "Golden hour", "5 min"):
        assert cell in ready.inner_text()
    assert running.locator(".chip").inner_text() == "Making"
    assert ready.locator(".chip").inner_text() == "Ready"


def test_opening_a_ready_job_shows_its_page(page, live_server, two_jobs):
    page.goto(live_server + "/jobs")

    page.locator("table.jobs tbody tr").nth(1).get_by_role("link", name="Open").click()

    page.wait_for_url(f"{live_server}/jobs/{JOB_A}")
    assert page.get_by_role("heading", name="Your video").is_visible()
