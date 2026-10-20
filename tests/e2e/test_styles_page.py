import re
import uuid

import pytest
from playwright.sync_api import expect
from sqlalchemy import text

from app.db.base import session_scope
from app.library.stubs import GOLDEN_HOUR_ID, STUB_SONG_ID, STUB_STYLES
from tests.support.library_rows import stub_presets  # noqa: F401

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("stub_presets")]

GOLDEN_HOUR = STUB_STYLES[0]


def card(page, name):
    return page.locator(".card", has=page.get_by_role("heading", name=name, exact=True))


def add_ready_shoot(label: str) -> str:
    shoot_id = str(uuid.uuid4())
    with session_scope() as session:
        session.execute(
            text("insert into photoshoots (id, label, status) values (:i, :l, 'ready')"),
            {"i": shoot_id, "l": label},
        )
    return shoot_id


def test_styles_page_renders_presets_and_loads_htmx(page, live_server):
    response = page.goto(live_server + "/")

    assert response.status == 200
    assert page.get_by_role("heading", name="Styles").is_visible()
    assert page.get_by_text("Golden hour").first.is_visible()
    assert page.get_by_text("Crisp modern").first.is_visible()
    assert page.evaluate("window.htmx.version").startswith("2.")


def test_preset_cards_show_name_author_text_and_song(page, live_server):
    page.goto(live_server + "/")

    for style in STUB_STYLES:
        preset = card(page, style.name)
        expect(preset).to_contain_text(f"by {style.author_name}")
        expect(preset).to_contain_text(style.style_text)
        expect(preset).to_contain_text("Song: Sunrise Walk by Example Artist, CC BY-NC")
        expect(preset).not_to_contain_text("stub://")


def test_style_with_reference_is_marked(page, live_server):
    page.goto(live_server + "/")

    expect(card(page, "Golden hour")).to_contain_text("Has a reference video")
    expect(card(page, "Crisp modern")).not_to_contain_text("Has a reference video")


@pytest.mark.parametrize(
    "answer",
    [
        lambda route: route.fulfill(
            status=502, content_type="text/html", body="<h1>Bad gateway</h1>"
        ),
        lambda route: route.abort(),
    ],
    ids=["html-502", "network-failure"],
)
def test_reproduction_failure_is_shown(page, live_server, answer):
    add_ready_shoot("9 Elm Road")
    page.route("**/api/jobs", answer)
    page.goto(live_server + "/")
    golden = card(page, "Golden hour")
    golden.get_by_text("Make a reproduction").click()

    golden.get_by_role("button", name="Start the reproduction").click()

    expect(golden.get_by_role("alert")).to_have_text("The reproduction could not start.")


def test_reproduction_starts_with_the_style_text_unchanged(page, live_server):
    other_shoot = add_ready_shoot("9 Elm Road")
    received = []

    def create_job(route):
        received.append(route.request.post_data_json)
        route.fulfill(status=201, json={"job": {"id": "job-1"}})

    page.route("**/api/jobs", create_job)
    page.goto(live_server + "/")
    golden = card(page, "Golden hour")
    golden.get_by_text("Make a reproduction").click()
    golden.get_by_label("Shoot").select_option(label="9 Elm Road")

    golden.get_by_role("button", name="Start the reproduction").click()

    expect(page).to_have_url(re.compile(r"/new\?jobId=job-1$"))
    assert received == [
        {
            "photoshootId": other_shoot,
            "styleText": GOLDEN_HOUR.style_text,
            "songId": STUB_SONG_ID,
            "styleId": GOLDEN_HOUR_ID,
            "purpose": "reproduction",
        }
    ]
