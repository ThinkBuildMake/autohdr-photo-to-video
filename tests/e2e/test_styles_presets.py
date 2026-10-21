import httpx
import pytest
from playwright.sync_api import expect

from tests.support.fixtures import DEMO_AUTH
from tests.support.library_rows import stub_presets  # noqa: F401
from tests.support.stub_data import STUB_DEMO_PHOTOSHOOT_ID, STUB_SONG_ID, STUB_STYLES

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("stub_presets")]

PRESET_NAMES = ("Golden hour walk", "Crisp modern walk")


def test_two_presets_created_through_the_api_show_on_styles(page, live_server):
    for style, name in zip(STUB_STYLES, PRESET_NAMES, strict=True):
        created = httpx.post(
            f"{live_server}/api/styles",
            json={
                "name": name,
                "authorName": "AutoHDR",
                "styleText": style.style_text,
                "songId": STUB_SONG_ID,
                "demoPhotoshootId": STUB_DEMO_PHOTOSHOOT_ID,
            },
            auth=DEMO_AUTH,
        )
        assert created.status_code == 201

    page.goto(live_server + "/")

    shown = []
    for style, name in zip(STUB_STYLES, PRESET_NAMES, strict=True):
        card = page.locator(".card", has=page.get_by_role("heading", name=name, exact=True))
        expect(card).to_contain_text(style.style_text)
        expect(card).to_contain_text("by AutoHDR")
        expect(card).to_contain_text("Song: Sunrise Walk")
        shown.append(card.inner_text())
    print("\n---\n".join(shown))
