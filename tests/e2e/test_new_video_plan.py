"""Styles and New video against the real plan, with OpenRouter mocked and the bucket local."""

import json
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
import pytest
from playwright.sync_api import expect

from app.config import reset_settings
from app.files.service import get, head_object
from app.jobs import planning
from app.jobs.plan_rules import MOVEMENTS
from app.main import create_app
from app.photoshoots import labelling
from app.providers import chat, video_api
from tests.e2e.test_new_video_photos import _form_file, drop_jpegs
from tests.photoshoots.conftest import jpeg_bytes, put_bytes
from tests.providers.chat.conftest import BASE, TEST_KEY, _chat_answer
from tests.providers.video.conftest import MODEL_LIST
from tests.support.fixtures import DEMO_PASSPHRASE, serve

pytestmark = pytest.mark.e2e

S3 = "https://test-bucket.s3.us-east-1.amazonaws.com/**"
POOL_NOTE = "There is no pool photo."
WALK = "Walk through every room."


def _photo_ids(texts: list[str]) -> list[str]:
    ids = []
    for text in texts:
        if text.startswith("photoId: "):
            ids.append(text.split(";", 1)[0].removeprefix("photoId: ").strip())
    return ids


def _shot(photo_id: str, movement: str, note: str) -> dict:
    return {
        "room": "living",
        "photoId": photo_id,
        "photoEditPrompts": [],
        "movementName": movement,
        "movementPrompt": MOVEMENTS[movement],
        "speed": "slow",
        "model": "google/veo-3.1",
        "lengthS": 4,
        "transition": "cut",
        "transitionS": 0,
        "planNote": note,
    }


class PlanAnswers:
    """Chat stand-in. Labels photos, then one shot per photo unless a test says otherwise."""

    def __init__(self):
        self.blank_plans = 0
        self.leave_one_photo = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/videos/models"):
            return httpx.Response(200, json=MODEL_LIST)
        body = json.loads(request.content)
        texts = [
            part.get("text", "")
            for part in body["messages"][0]["content"]
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        joined = "\n".join(texts)
        photo_ids = _photo_ids(texts)
        if "You label real-estate photos" in joined:
            labels = [
                {"photoId": photo_id, "room": "living", "subject": f"subject {index + 1}"}
                for index, photo_id in enumerate(photo_ids)
            ]
            return httpx.Response(200, json=_chat_answer(json.dumps({"labels": labels})))
        if self.blank_plans:
            self.blank_plans -= 1
            return httpx.Response(200, json=_chat_answer(json.dumps({"notes": "no shots"})))
        if self.leave_one_photo and len(photo_ids) > 1:
            photo_ids = photo_ids[:-1]
        notes = POOL_NOTE if "pool" in joined else ""
        last = len(photo_ids) - 1
        shots = []
        for index, photo_id in enumerate(photo_ids):
            movement = "dolly_out" if "Dolly Out" in joined and index == last else "dolly_in"
            shots.append(_shot(photo_id, movement, f"From the text: shot {index + 1}"))
        return httpx.Response(200, json=_chat_answer(json.dumps({"shots": shots, "notes": notes})))


def _bucket_route(route):
    if route.request.method == "POST":
        key, data, _filename = _form_file(route)
        put_bytes(key, data or b"")
        route.fulfill(status=204, headers={"Access-Control-Allow-Origin": "*"})
        return
    key = unquote(urlparse(route.request.url).path).lstrip("/")
    if head_object(key) is None:
        route.fulfill(status=404)
        return
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "object"
        get(key, str(path))
        body = path.read_bytes()
    route.fulfill(
        status=200,
        content_type="image/jpeg",
        body=body,
        headers={"Access-Control-Allow-Origin": "*"},
    )


def _stay_local(route):
    if route.request.url.startswith(("http://127.0.0.1", "http://localhost")):
        route.continue_()
        return
    route.abort()


@pytest.fixture
def planned(page, _isolated_environment, bucket, stub_presets, monkeypatch):
    page.set_default_timeout(20_000)
    expect.set_options(timeout=20_000)
    monkeypatch.setenv("FAKE_PROVIDERS", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", TEST_KEY)
    monkeypatch.setenv("OPENROUTER_BASE_URL", BASE)
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    reset_settings()
    chat.reset_pricing()
    video_api.reset_cache()
    answers = PlanAnswers()
    transport = httpx.MockTransport(answers.handler)
    monkeypatch.setattr(chat, "TRANSPORT", transport)
    monkeypatch.setattr(video_api, "TRANSPORT", transport)
    page.route("**/*", _stay_local)
    page.route(S3, _bucket_route)
    with serve(create_app()) as base_url:
        page.goto(base_url + "/new")
        page.base_url = base_url
        page.answers = answers
        yield page
    labelling.wait_idle(timeout=120)
    planning.wait_idle(timeout=30)
    chat.reset_pricing()
    video_api.reset_cache()


def cards(page):
    return page.locator("#shots .shot-card")


def drop_three(page):
    picture = jpeg_bytes()
    drop_jpegs(page, [(f"photo-{index}.jpg", picture) for index in range(1, 4)])
    expect(page.locator("#photo-grid .tile")).to_have_count(3)


def plan(page, style_text: str) -> str:
    page.get_by_label("Style text").fill(style_text)
    drop_three(page)
    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/api/jobs")
    ) as created:
        page.get_by_role("button", name="Next: write the shot plan").click()
    return created.value.json()["job"]["id"]


def _shot_line(card) -> str:
    return (
        f"movement={card.get_by_label('Camera movement').input_value()} "
        f"length={card.get_by_label('Length').input_value()} "
        f"note={card.locator('.plan-note').inner_text()} "
        f"photo={card.locator('select[name=photo]').input_value()}"
    )


def test_plan_cards_come_from_the_real_job(planned):
    plan(planned, WALK)

    expect(cards(planned)).to_have_count(3)
    photo_ids = []
    lines = []
    for index in range(3):
        card = cards(planned).nth(index)
        expect(card.get_by_label("Camera movement")).to_have_value("dolly_in")
        expect(card.get_by_label("Length")).to_have_value("4")
        expect(card.locator(".plan-note")).to_have_text(f"From the text: shot {index + 1}")
        photo_ids.append(card.locator("select[name=photo]").input_value())
        lines.append(_shot_line(card))

    assert len(set(photo_ids)) == 3
    assert all(photo_ids)
    print("\n".join(lines))


def test_last_shot_is_dolly_out(planned):
    plan(planned, "Walk the rooms. End on a Dolly Out.")

    last = cards(planned).last.get_by_label("Camera movement")
    expect(last).to_have_value("dolly_out")
    print(last.input_value())


def test_saved_edits_survive_reload(planned):
    job_id = plan(planned, WALK)
    expect(cards(planned)).to_have_count(3)
    cards(planned).first.get_by_label("Camera movement").select_option("crane_up")
    cards(planned).nth(1).get_by_role("button", name="Remove shot").click()

    planned.get_by_role("button", name="Save the plan").click()

    expect(planned.get_by_text("Plan saved")).to_be_visible()
    planned.goto(f"{planned.base_url}/new?jobId={job_id}")
    expect(cards(planned).first.get_by_label("Camera movement")).to_have_value("crane_up")
    expect(cards(planned)).to_have_count(2)
    print(
        f"movement={cards(planned).first.get_by_label('Camera movement').input_value()} "
        f"cards={cards(planned).count()}"
    )


def test_pool_request_is_named_in_the_banner(planned):
    plan(planned, "Show the pool from the yard.")

    note = planned.locator("#plan-notes .note")
    expect(note).to_have_text(POOL_NOTE)
    print(note.inner_text())


def test_save_as_my_style_lists_the_new_style(planned):
    text = "Warm light on the lawn, slower than the preset."
    planned.get_by_label("Style text").fill(text)
    planned.get_by_label("Style name").fill("My golden hour")

    planned.get_by_role("button", name="Save as my style").click()

    expect(planned.get_by_text("Saved as My golden hour")).to_be_visible()
    planned.goto(planned.base_url + "/")
    card = planned.locator(
        ".card", has=planned.get_by_role("heading", name="My golden hour", exact=True)
    )
    expect(card).to_contain_text(text)
    print(card.inner_text())


def test_failed_plan_offers_try_again(planned):
    planned.answers.blank_plans = 2
    plan(planned, WALK)

    failed = planned.locator("#plan-failed")
    expect(failed).to_be_visible()
    expect(failed).to_contain_text("Try again")
    print(failed.inner_text())


def test_added_crane_up_shot_is_kept(planned):
    planned.answers.leave_one_photo = True
    job_id = plan(planned, WALK)
    expect(cards(planned)).to_have_count(2)
    photo_select = cards(planned).first.locator("select[name=photo]")
    options = photo_select.locator("option").evaluate_all(
        "els => els.map((el) => el.value).filter(Boolean)"
    )
    used = {
        cards(planned).nth(index).locator("select[name=photo]").input_value() for index in range(2)
    }
    unused = next(value for value in options if value not in used)

    planned.get_by_role("button", name="Add a shot").click()
    cards(planned).last.get_by_label("Camera movement").select_option("crane_up")
    cards(planned).last.locator("select[name=photo]").select_option(unused)
    planned.get_by_role("button", name="Save the plan").click()

    expect(planned.get_by_text("Plan saved")).to_be_visible()
    planned.goto(f"{planned.base_url}/new?jobId={job_id}")
    last = cards(planned).last
    expect(last.get_by_label("Camera movement")).to_have_value("crane_up")
    expect(last.locator("select[name=photo]")).to_have_value(unused)
    print(f"movement={last.get_by_label('Camera movement').input_value()} photo={unused}")


@pytest.mark.parametrize("button", ["Back", "Change the style text and re-plan"])
def test_plan_navigation_replans_existing_upload(planned, button):
    job_id = plan(planned, WALK)
    expect(cards(planned)).to_have_count(3)
    shoot_id = planned.request.get(f"{planned.base_url}/api/jobs/{job_id}").json()["job"][
        "photoshootId"
    ]
    original_song = planned.locator("#song").input_value()
    requests = []
    planned.on("request", lambda request: requests.append((request.method, request.url)))
    planned.get_by_role("button", name=button, exact=True).click()
    expect(planned.get_by_label("Style text")).to_have_value(WALK)
    expect(planned.locator("#song")).to_have_value(original_song)
    expect(planned.locator("#photo-grid .tile")).to_have_count(3)
    revised = "End on a Dolly Out."
    planned.get_by_label("Style text").fill(revised)
    song = planned.locator("#song option").last.get_attribute("value")
    planned.get_by_label("Song", exact=True).select_option(song)
    with planned.expect_response(
        lambda response: (
            response.request.method == "POST" and response.url.endswith(f"/api/jobs/{job_id}/plan")
        )
    ) as replanned:
        planned.get_by_role("button", name="Next: write the shot plan").click()
    assert replanned.value.request.post_data_json == {"styleText": revised, "songId": song}
    expect(cards(planned).last.get_by_label("Camera movement")).to_have_value("dolly_out")
    job = planned.request.get(f"{planned.base_url}/api/jobs/{job_id}").json()["job"]
    assert job["photoshootId"] == shoot_id
    assert not any(
        method == "POST" and url.endswith(("/api/photoshoots", "/api/jobs"))
        for method, url in requests
    )
    print(f"replanned draft={job_id} shoot={shoot_id} style={revised} song={song}")


def test_cut_times_follow_lengths_and_removal(planned):
    plan(planned, WALK)
    expect(planned.locator(".cut-time")).to_have_text(["cut at 0:04", "cut at 0:08", "cut at 0:12"])
    cards(planned).first.get_by_label("Length").fill("2.5")
    cards(planned).first.get_by_label("Length").press("Tab")
    expect(planned.locator(".cut-time")).to_have_text(
        ["cut at 0:02.5", "cut at 0:06.5", "cut at 0:10.5"]
    )
    cards(planned).nth(1).get_by_role("button", name="Remove shot").click()
    expect(planned.locator(".cut-time")).to_have_text(["cut at 0:02.5", "cut at 0:06.5"])
    print(planned.locator(".cut-time").all_text_contents())


def test_submit_stays_disabled_until_navigation(planned):
    job_id = plan(planned, WALK)
    expect(cards(planned)).to_have_count(3)
    submissions = []

    def submit(route):
        submissions.append(route.request.url)
        route.fulfill(status=200, json={})

    planned.route(f"**/api/jobs/{job_id}/submit", submit)
    # Evaluating while a navigation is held open hangs, so the old document
    # records its own controls (and tries a second click) as it unloads.
    planned.evaluate(
        """() => addEventListener("pagehide", () => {
            const makeVideo = document.querySelector("#make-video");
            makeVideo.dispatchEvent(new MouseEvent("click", {bubbles: true}));
            sessionStorage.setItem("controls", JSON.stringify({
                makeVideoDisabled: makeVideo.disabled,
                backDisabled: document.querySelector("#back").disabled,
            }));
        })"""
    )
    planned.get_by_role("button", name="Make my video").click()
    planned.wait_for_url(f"**/jobs/{job_id}", timeout=20_000)
    controls = planned.evaluate("JSON.parse(sessionStorage.getItem('controls'))")
    assert controls == {"makeVideoDisabled": True, "backDisabled": True}
    assert len(submissions) == 1
    print("one submit; Make my video and Back disabled during navigation")


@pytest.mark.parametrize("failure", ["shots", "submit"])
def test_failed_submission_preserves_edits_and_restores_controls(planned, failure):
    job_id = plan(planned, WALK)
    expect(cards(planned)).to_have_count(3)
    cards(planned).first.get_by_label("Camera movement").select_option("crane_up")
    submissions = []
    planned.on(
        "request",
        lambda request: (
            submissions.append(request.url) if request.url.endswith("/submit") else None
        ),
    )
    planned.route(
        f"**/api/jobs/{job_id}/{failure}",
        lambda route: route.fulfill(status=503, json={"message": "Please retry"}),
    )
    planned.get_by_role("button", name="Make my video").click()
    expect(planned.locator("#page-error")).to_have_text("Please retry")
    expect(planned.locator("#make-video")).to_be_enabled()
    expect(planned.locator("#back")).to_be_enabled()
    expect(cards(planned).first.get_by_label("Camera movement")).to_have_value("crane_up")
    assert len(submissions) == (1 if failure == "submit" else 0)
    print(f"{failure} failed: edits retained and controls enabled")
