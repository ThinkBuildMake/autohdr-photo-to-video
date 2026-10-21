"""Authoring through real routes and pipeline; only external HTTP/storage simulated."""

import pytest
from playwright.sync_api import expect

from tests.support.fixtures import client as api_client_fixture
from tests.support.style_flow import style_world

api_client = api_client_fixture

pytestmark = pytest.mark.e2e


def test_two_demo_tries_and_reference(page, live_server, api_client, bucket, tmp_path, monkeypatch):
    with style_world(tmp_path, monkeypatch) as world:
        page.route("https://test-bucket.s3.amazonaws.com/**", world.serve_media)
        page.route("https://test-bucket.s3.us-east-1.amazonaws.com/**", world.serve_media)
        page.goto(live_server + "/styles/new")
        page.get_by_label("Style name").fill("Author's style")
        page.get_by_label("Your name").fill("Sam")
        page.get_by_label("Song").select_option(world.song_id)
        page.get_by_label("Demo photoshoot").select_option(world.shoots[0])
        page.get_by_label("Style text").fill("Slow rooms.")
        page.get_by_role("button", name="Try it").click()
        first = world.wait_for_job(api_client, 1)
        expect(page.locator("#plan-rows tr")).to_have_count(1, timeout=15000)
        expect(page.locator("#try video")).to_be_hidden()
        print("Plan before video:", page.locator("#plan-rows").inner_text())
        world.wait_for_submission(first)
        world.finish(first)
        expect(page.get_by_text("Try 1 is ready")).to_be_visible(timeout=15000)
        page.locator("#try video").evaluate("v => { v.muted = true; return v.play(); }")
        page.wait_for_function("document.querySelector('#try video').currentTime > 0.1")
        print("Try 1 playing at:", page.locator("#try video").evaluate("v => v.currentTime"))
        assert page.get_by_label("Your name").get_attribute("readonly") is not None
        expect(page.get_by_label("Demo photoshoot")).to_be_disabled()
        page.get_by_label("Style text").fill("Slow rooms. End wide.")
        page.get_by_role("button", name="Try it").click()
        second = world.wait_for_job(api_client, 2)
        assert second != first
        world.wait_for_submission(second)
        world.finish(second)
        expect(page.get_by_text("Try 2 is ready")).to_be_visible(timeout=15000)
        expect(page.get_by_text("Try 1 is kept in Jobs.")).to_be_visible()
        page.get_by_role("button", name="Use as the reference video").click()
        expect(page.get_by_text("is now the style's reference video")).to_be_visible()
        style = api_client.get("/api/styles").json()["styles"][0]
        detail = api_client.get(f"/api/styles/{style['id']}").json()["style"]
        print("Distinct tries:", first, second, "saved text:", detail["styleText"])
        print("Reference job:", detail["referenceJobId"])
        assert detail["referenceJobId"] == second
        assert detail["styleText"] == "Slow rooms. End wide."
        assert api_client.get(f"/api/jobs/{first}").json()["job"]["styleText"] == "Slow rooms."
        response = page.goto(live_server + "/")
        assert response.status == 200
        expect(page.get_by_text("Has a reference video")).to_be_visible()
        print("Styles card: Has a reference video")


def test_edit_existing_style_preserves_identity(
    page, live_server, api_client, bucket, tmp_path, monkeypatch
):
    with style_world(tmp_path, monkeypatch) as world:
        style = api_client.post(
            "/api/styles",
            json={
                "name": "Saved",
                "authorName": "Sam",
                "styleText": "Slow rooms.",
                "songId": world.song_id,
                "fps": 24,
                "demoPhotoshootId": world.shoots[0],
            },
        ).json()["style"]
        page.goto(live_server + f"/styles/new?styleId={style['id']}")
        expect(page.get_by_label("Style name")).to_have_value("Saved")
        expect(page.get_by_label("Style text")).to_have_value("Slow rooms.")
        expect(page.get_by_label("Frame rate")).to_have_value("24")
        expect(page.get_by_label("Demo photoshoot")).to_be_disabled()
        page.get_by_label("Style text").fill("Revised rooms.")
        page.get_by_role("button", name="Save style", exact=True).click()
        page.wait_for_url(live_server + "/")
        expect(page.get_by_role("heading", name="Styles", exact=True)).to_be_visible()
        saved = api_client.get(f"/api/styles/{style['id']}").json()["style"]
        assert saved["styleText"] == "Revised rooms."
        assert saved["authorName"] == "Sam"
        assert api_client.get("/api/jobs").json()["jobs"] == []
