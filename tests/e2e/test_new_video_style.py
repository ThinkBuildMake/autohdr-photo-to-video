import io
import re
import wave

import pytest
from playwright.sync_api import expect

from app.config import reset_settings
from app.files.client import reset_client
from app.library.stubs import GOLDEN_HOUR_ID, STUB_SONG_ID, STUB_STYLES
from app.main import create_app
from tests.support.bucket import BUCKET, MOTO_ENDPOINT, REGION, SECRET
from tests.support.fixtures import DEMO_PASSPHRASE, serve
from tests.support.library_rows import add_song, stub_presets  # noqa: F401

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("stub_presets")]

GOLDEN_HOUR = STUB_STYLES[0]
DOLLY_OUT = " End on a Dolly Out."


@pytest.fixture
def form(page, live_server):
    add_song(title="Another Track")
    page.goto(f"{live_server}/new?styleId={GOLDEN_HOUR_ID}")
    return page


def silent_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\0\0" * 16000)
    return buffer.getvalue()


def test_use_this_style_fills_the_form(page, live_server):
    add_song(title="Another Track")
    page.goto(live_server + "/")
    golden = page.locator(".card", has=page.get_by_role("heading", name="Golden hour"))

    golden.get_by_role("link", name="Use this style").click()

    expect(page).to_have_url(re.compile(rf"/new\?styleId={GOLDEN_HOUR_ID}$"))
    expect(page.get_by_label("Style text")).to_have_value(GOLDEN_HOUR.style_text)
    expect(page.get_by_label("Song", exact=True)).to_have_value(STUB_SONG_ID)


def test_style_text_can_be_edited(form):
    field = form.get_by_label("Style text")
    field.evaluate("el => { el.focus(); el.setSelectionRange(el.value.length, el.value.length); }")

    field.press_sequentially(DOLLY_OUT)

    expect(field).to_have_value(GOLDEN_HOUR.style_text + DOLLY_OUT)


def test_save_as_my_style_sends_name_text_and_song(form):
    received = []

    def create_style(route):
        received.append(route.request.post_data_json)
        route.fulfill(status=201, json={"style": {"id": "s-1", "name": "My golden hour"}})

    form.route("**/api/styles", create_style)
    form.get_by_label("Style text").fill(GOLDEN_HOUR.style_text + DOLLY_OUT)
    form.get_by_label("Style name").fill("My golden hour")

    form.get_by_role("button", name="Save as my style").click()

    expect(form.get_by_text("Saved as My golden hour")).to_be_visible()
    assert len(received) == 1
    assert received[0]["name"] == "My golden hour"
    assert received[0]["styleText"] == GOLDEN_HOUR.style_text + DOLLY_OUT
    assert received[0]["songId"] == STUB_SONG_ID


def test_song_picker_shows_title_artist_and_licence_only(form):
    options = form.get_by_label("Song", exact=True).locator("option")

    expect(options).to_have_text(
        ["Another Track by Artist A, CC BY-NC", "Sunrise Walk by Example Artist, CC BY-NC"]
    )
    html = form.locator("#song").inner_html()
    assert "stub://" not in html
    assert "example.com" not in html
    assert "https://" not in form.locator("#song").inner_text()


def test_song_preview_plays(page, monkeypatch):
    monkeypatch.setenv("BUCKET_NAME", BUCKET)
    monkeypatch.setenv("BUCKET_ACCESS_KEY_ID", SECRET)
    monkeypatch.setenv("BUCKET_SECRET_ACCESS_KEY", SECRET)
    monkeypatch.setenv("BUCKET_REGION", REGION)
    monkeypatch.setenv("BUCKET_ENDPOINT", MOTO_ENDPOINT)
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    reset_settings()
    reset_client()
    other_id = add_song(title="Another Track")

    def stay_local(route):
        if route.request.url.startswith(("http://127.0.0.1", "http://localhost")):
            route.continue_()
            return
        route.abort()

    page.route("**/*", stay_local)
    page.route(
        "https://test-bucket.s3.us-east-1.amazonaws.com/**",
        lambda route: route.fulfill(status=200, content_type="audio/wav", body=silent_wav()),
    )

    with serve(create_app()) as base_url:
        page.goto(f"{base_url}/new?styleId={GOLDEN_HOUR_ID}")
        song = page.get_by_label("Song", exact=True)
        expect(song.locator("option:checked")).to_have_text(
            "Sunrise Walk by Example Artist, CC BY-NC"
        )

        with page.expect_request("**/songs/stub.mp3**") as first_play:
            page.get_by_role("button", name="Play the song").click()
        first_url = first_play.value.url
        assert first_url.startswith("https://")
        assert "songs/stub.mp3" in first_url
        assert "/stub-media/" not in first_url
        expect(page.locator("#song-preview")).to_have_attribute("src", first_url)
        page.wait_for_function("() => !document.querySelector('#song-preview').paused")

        song.select_option(other_id)
        expect(song.locator("option:checked")).to_have_text("Another Track by Artist A, CC BY-NC")
        with page.expect_request(f"**/songs/{other_id}.mp3**") as second_play:
            page.get_by_role("button", name="Play the song").click()
        second_url = second_play.value.url
        assert second_url.startswith("https://")
        assert f"songs/{other_id}.mp3" in second_url
        assert second_url != first_url
        expect(page.locator("#song-preview")).to_have_attribute("src", second_url)
        page.wait_for_function("() => !document.querySelector('#song-preview').paused")
