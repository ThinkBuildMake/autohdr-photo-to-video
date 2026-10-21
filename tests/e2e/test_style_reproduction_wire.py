"""Reproduce a saved style on another shoot and compare, through real routes and media."""

import pytest
from playwright.sync_api import expect

from tests.support.fixtures import client as api_client_fixture
from tests.support.style_flow import style_world

api_client = api_client_fixture

pytestmark = pytest.mark.e2e

TEXT = "Slow rooms. End wide."


def post(client, path, body):
    response = client.post(path, json=body)
    assert response.status_code in (200, 201), response.text
    return response.json()


def reproduce_on_second_shoot(page, live_server, client, world):
    style = post(
        client,
        "/api/styles",
        {
            "name": "Flow style",
            "authorName": "Sam",
            "styleText": TEXT,
            "songId": world.song_id,
            "demoPhotoshootId": world.shoots[0],
            "fps": 30,
        },
    )["style"]
    job = post(
        client,
        "/api/jobs",
        {
            "photoshootId": world.shoots[0],
            "styleId": style["id"],
            "styleText": TEXT,
            "songId": world.song_id,
            "purpose": "video",
        },
    )["job"]["id"]
    world.finish(job)
    post(client, f"/api/styles/{style['id']}/reference", {"jobId": job})
    page.goto(live_server + "/")
    card = page.locator(".card", has=page.get_by_role("heading", name="Flow style", exact=True))
    card.get_by_text("Make a reproduction").click()
    card.locator("select").select_option(world.shoots[1])
    card.get_by_role("button", name="Start the reproduction").click()
    reproduction = world.wait_for_job(client, 2)
    world.finish(reproduction)
    return style["id"], job, reproduction


def test_reproduction_is_compared_and_both_videos_play_together(
    page, live_server, api_client, bucket, tmp_path, monkeypatch
):
    with style_world(tmp_path, monkeypatch) as world:
        page.route("https://test-bucket.s3.amazonaws.com/**", world.serve_media)
        page.route("https://test-bucket.s3.us-east-1.amazonaws.com/**", world.serve_media)
        style_id, reference, reproduction = reproduce_on_second_shoot(
            page, live_server, api_client, world
        )
        stored = api_client.get(f"/api/jobs/{reproduction}").json()["job"]
        assert stored["styleText"] == TEXT and stored["purpose"] == "reproduction"

        page.goto(live_server + f"/styles/{style_id}/reproductions?jobId={reproduction}")

        expect(page.locator("#facts")).to_contain_text("Same song: yes · Same style text: yes")
        expect(page.locator("#song")).to_contain_text("Song:")
        expect(page.locator("#reference-title")).to_contain_text("Demo house")
        expect(page.locator("#reproduction-title")).to_contain_text("Second house")
        expect(page.locator("#summary tr").first).to_contain_text("Shots")
        assert page.locator("#shots tr").count() == 1
        videos = page.locator("#comparison video")
        page.wait_for_function(
            "[...document.querySelectorAll('#comparison video')].every(v => v.readyState >= 3)"
        )
        videos.evaluate_all("vs => vs.forEach(v => { v.muted = true; })")
        page.get_by_role("button", name="Play both together").click()
        page.wait_for_function(
            "[...document.querySelectorAll('#comparison video')].every(v => v.currentTime > 0.2)"
        )
        times = videos.evaluate_all("vs => vs.map(v => v.currentTime)")
        print("Playing together at:", times)
        assert abs(times[0] - times[1]) < 0.3
        videos.nth(0).evaluate("v => v.pause()")
        page.wait_for_function(
            "[...document.querySelectorAll('#comparison video')].every(v => v.paused)"
        )
        videos.nth(1).evaluate("v => { v.currentTime = 1.5; }")
        page.wait_for_function(
            "Math.abs(document.querySelector('#reference-video').currentTime - 1.5) < 0.1"
        )
        page.get_by_role("button", name="Play both together").click()
        page.wait_for_function(
            "[...document.querySelectorAll('#comparison video')].every("
            "v => !v.paused && v.currentTime > 0.1 && v.currentTime < 1)"
        )
        assert reference != reproduction


def test_a_rejected_play_is_shown(page, live_server, api_client, bucket, tmp_path, monkeypatch):
    with style_world(tmp_path, monkeypatch) as world:
        page.route("https://test-bucket.s3.amazonaws.com/**", world.serve_media)
        page.route("https://test-bucket.s3.us-east-1.amazonaws.com/**", world.serve_media)
        style_id, _, reproduction = reproduce_on_second_shoot(page, live_server, api_client, world)
        page.goto(live_server + f"/styles/{style_id}/reproductions?jobId={reproduction}")
        expect(page.locator("#comparison")).to_be_visible()
        page.evaluate(
            "() => { HTMLMediaElement.prototype.play = "
            "() => Promise.reject(new Error('blocked')); }"
        )

        page.get_by_role("button", name="Play both together").click()

        expect(page.locator("#message")).to_contain_text("Playback could not start: blocked")
