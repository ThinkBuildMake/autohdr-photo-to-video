import json

import pytest

from tests.photoshoots.conftest import seed_shoot
from tests.support.library_rows import add_song

pytestmark = pytest.mark.e2e

STYLE_TEXT = "Warm light, slow dolly moves, end on a wide exterior."


class Api:
    """Stubs JSON routes in the browser and records the bodies they receive."""

    def __init__(self, page):
        self.page = page
        self.calls: list[tuple[str, str, dict | None]] = []

    def stub(self, method, path, body, status=200):
        """body may be a list answered in turn (the last repeats); an item may be
        (status, body), and a str body is sent as an HTML page."""
        answers = body if isinstance(body, list) else [body]

        def handle(route, request):
            if request.method != method:
                return route.fallback()
            data = request.post_data
            self.calls.append((method, request.url, json.loads(data) if data else None))
            answer = answers.pop(0) if len(answers) > 1 else answers[0]
            code, answer = answer if isinstance(answer, tuple) else (status, answer)
            if isinstance(answer, str):
                route.fulfill(status=code, content_type="text/html", body=answer)
            else:
                route.fulfill(status=code, content_type="application/json", body=json.dumps(answer))

        self.page.route(f"**{path}", handle)

    def bodies(self, method, path):
        return [b for m, url, b in self.calls if m == method and url.endswith(path)]


@pytest.fixture
def seeded(bucket):
    song_id = add_song(title="Track A", artist="Artist A", licence="BY-NC")
    add_song(title="Track B", artist="Artist B", licence="BY-NC-SA")
    shoot_id, _ = seed_shoot(["uploaded", "uploaded"], "ready", label="Test shoot A")
    return {"song_id": song_id, "shoot_id": shoot_id}


def fill_form(page, seeded, name="Golden hour"):
    page.get_by_label("Style name").fill(name)
    page.get_by_label("Your name").fill("Sam")
    page.get_by_label("Style text").fill(STYLE_TEXT)
    page.get_by_label("Song").select_option(seeded["song_id"])
    page.get_by_label("Frame rate").select_option("24")
    page.get_by_label("Demo photoshoot").select_option(seeded["shoot_id"])


def shot(position, movement, length_s, transition="cut"):
    return {
        "position": position,
        "room": "living",
        "movementName": movement,
        "lengthS": length_s,
        "transition": transition,
        "transitionS": 0.4 if transition == "crossfade" else 0.0,
        "removed": False,
    }


SHOTS = [shot(1, "drone_top_down_descend", 4.0), shot(2, "dolly_in", 6.0, "crossfade")]
CREDIT = "Track A, Artist A, CC BY-NC, https://example.com/music/track-a"
DRAFT = {"id": "job-1", "planStatus": "planning", "status": "draft", "shots": []}
PLANNED = {**DRAFT, "planStatus": "ready", "shots": SHOTS}
READY = {
    **PLANNED,
    "status": "ready",
    "video": {"url": "/stub-media/try.mp4", "durationS": 10.0},
    "songCredit": CREDIT,
}


def finished_try(page, live_server, seeded, api):
    api.stub("POST", "/api/styles", {"style": {"id": "style-1"}}, status=201)
    api.stub("POST", "/api/jobs", {"job": DRAFT}, status=201)
    api.stub("GET", "/api/jobs/job-1", {"job": READY})
    page.goto(live_server + "/styles/new")
    fill_form(page, seeded)
    page.get_by_role("button", name="Try it").click()
    page.get_by_text("Try 1 is ready").wait_for()


def test_finished_try_shows_its_plan_and_video(page, live_server, seeded):
    api = Api(page)
    api.stub("POST", "/api/styles", {"style": {"id": "style-1"}}, status=201)
    api.stub("POST", "/api/jobs", {"job": DRAFT}, status=201)
    api.stub("GET", "/api/jobs/job-1", [{"job": PLANNED}, {"job": READY}])
    api.stub("POST", "/api/jobs/job-1/submit", {"job": {**PLANNED, "status": "queued"}}, 202)
    page.goto(live_server + "/styles/new")
    fill_form(page, seeded)

    page.get_by_role("button", name="Try it").click()

    page.get_by_text("Try 1 is ready").wait_for(timeout=15000)
    assert len(api.bodies("POST", "/api/jobs/job-1/submit")) == 1
    rows = page.locator("#plan-rows tr").all_inner_texts()
    assert [row.split("\t") for row in rows] == [
        ["1", "Living", "Drone top down descend", "4 s", "Cut"],
        ["2", "Living", "Dolly in", "6 s", "Crossfade 0.4 s"],
    ]
    video = page.locator("#try video")
    assert video.is_visible()
    assert video.get_attribute("src") == "/stub-media/try.mp4"
    credit = page.locator("#try-credit")
    assert "Track A, Artist A, CC BY-NC" in credit.inner_text()
    assert "example.com" not in page.locator("main").inner_text()
    assert "stub-media" not in page.locator("main").inner_text()


def test_revised_text_updates_the_style_and_makes_a_new_try(page, live_server, seeded):
    api = Api(page)
    finished_try(page, live_server, seeded, api)
    api.stub("PUT", "/api/styles/style-1", {"style": {"id": "style-1"}})

    page.get_by_label("Style text").fill(STYLE_TEXT + " End on a Dolly Out.")
    page.get_by_role("button", name="Try it").click()

    page.get_by_text("Try 2 is ready").wait_for()
    assert api.bodies("PUT", "/api/styles/style-1") == [
        {
            "name": "Golden hour",
            "styleText": STYLE_TEXT + " End on a Dolly Out.",
            "songId": seeded["song_id"],
            "fps": 24,
        }
    ]
    jobs = api.bodies("POST", "/api/jobs")
    assert len(jobs) == 2
    assert jobs[1]["styleText"] == STYLE_TEXT + " End on a Dolly Out."
    assert len(api.bodies("POST", "/api/styles")) == 1


def test_use_as_reference_sends_the_try(page, live_server, seeded):
    api = Api(page)
    finished_try(page, live_server, seeded, api)
    api.stub("POST", "/api/styles/style-1/reference", {"style": {"id": "style-1"}})

    page.get_by_role("button", name="Use as the reference video").click()

    page.get_by_text("is now the style's reference video").wait_for()
    assert api.bodies("POST", "/api/styles/style-1/reference") == [{"jobId": "job-1"}]


def test_reference_note_clears_when_a_changed_text_cannot_start_a_try(page, live_server, seeded):
    api = Api(page)
    finished_try(page, live_server, seeded, api)
    api.stub("POST", "/api/styles/style-1/reference", {"style": {"id": "style-1"}})
    page.get_by_role("button", name="Use as the reference video").click()
    page.get_by_text("is now the style's reference video").wait_for()
    api.stub("PUT", "/api/styles/style-1", {"style": {"id": "style-1"}})
    api.stub("POST", "/api/jobs", {"error": "boom", "message": "No try."}, status=500)

    page.get_by_label("Style text").fill(STYLE_TEXT + " End on a Dolly Out.")
    page.get_by_role("button", name="Try it").click()

    page.locator("#error").wait_for()
    assert page.locator("#reference-note").inner_text() == ""


def test_try_it_sends_the_style_and_the_try(page, live_server, seeded):
    api = Api(page)
    api.stub("POST", "/api/styles", {"style": {"id": "style-1"}}, status=201)
    api.stub("POST", "/api/jobs", {"job": DRAFT}, status=201)
    api.stub("GET", "/api/jobs/job-1", {"job": DRAFT})
    page.goto(live_server + "/styles/new")
    fill_form(page, seeded)

    page.get_by_role("button", name="Try it on the demo shoot").click()

    page.get_by_text("Try 1: writing the shot plan").wait_for()
    assert page.locator("#try").is_hidden()
    assert page.locator("#error").is_hidden()
    assert api.bodies("POST", "/api/styles") == [
        {
            "name": "Golden hour",
            "authorName": "Sam",
            "styleText": STYLE_TEXT,
            "songId": seeded["song_id"],
            "fps": 24,
            "demoPhotoshootId": seeded["shoot_id"],
        }
    ]
    assert api.bodies("POST", "/api/jobs") == [
        {
            "photoshootId": seeded["shoot_id"],
            "styleText": STYLE_TEXT,
            "songId": seeded["song_id"],
            "styleId": "style-1",
            "purpose": "video",
        }
    ]


def test_page_has_no_video_upload_control(page, live_server, seeded):
    page.goto(live_server + "/styles/new")

    assert page.get_by_label("Style text").evaluate("el => el.tagName") == "TEXTAREA"
    assert page.locator("input[type=file]").count() == 0
    assert page.locator("[accept*=video], video[src], input[name*=video i]").count() == 0


def test_chosen_song_shows_its_licence_and_credit(page, live_server, seeded):
    page.goto(live_server + "/styles/new")

    page.get_by_label("Song").select_option(seeded["song_id"])

    credit = page.locator("#song-credit")
    assert "CC BY-NC" in credit.inner_text()
    assert "Track A, Artist A" in credit.inner_text()
    assert "example.com" not in credit.inner_text()
    assert credit.get_by_role("link", name="source").get_attribute("href").endswith("track-a")


def test_double_click_on_try_it_sends_one_style_and_one_try(page, live_server, seeded):
    api = Api(page)
    api.stub("POST", "/api/styles", {"style": {"id": "style-1"}}, status=201)
    api.stub("POST", "/api/jobs", {"job": DRAFT}, status=201)
    api.stub("GET", "/api/jobs/job-1", {"job": READY})
    page.goto(live_server + "/styles/new")
    fill_form(page, seeded)

    page.get_by_role("button", name="Try it").dblclick()

    page.get_by_text("Try 1 is ready").wait_for()
    assert len(api.bodies("POST", "/api/styles")) == 1
    assert len(api.bodies("POST", "/api/jobs")) == 1
    assert page.locator("#error").is_hidden()


def test_double_click_on_a_revision_sends_one_update_and_one_try(page, live_server, seeded):
    api = Api(page)
    finished_try(page, live_server, seeded, api)
    api.stub("PUT", "/api/styles/style-1", {"style": {"id": "style-1"}})
    page.get_by_label("Style text").fill(STYLE_TEXT + " Faster.")

    page.get_by_role("button", name="Try it").dblclick()

    page.get_by_text("Try 2 is ready").wait_for()
    assert len(api.bodies("PUT", "/api/styles/style-1")) == 1
    assert len(api.bodies("POST", "/api/jobs")) == 2
    assert page.get_by_role("button", name="Try it").is_enabled()


def test_reference_button_stays_off_for_a_try_with_failed_shots(page, live_server, seeded):
    api = Api(page)
    api.stub("POST", "/api/styles", {"style": {"id": "style-1"}}, status=201)
    api.stub("POST", "/api/jobs", {"job": DRAFT}, status=201)
    api.stub("GET", "/api/jobs/job-1", {"job": {**READY, "status": "ready_with_failures"}})
    page.goto(live_server + "/styles/new")
    fill_form(page, seeded)

    page.get_by_role("button", name="Try it").click()

    page.get_by_text("Try 1 is ready, with shots that did not work").wait_for()
    assert page.get_by_role("button", name="Use as the reference video").is_disabled()


def test_reference_button_is_off_once_a_revision_starts(page, live_server, seeded):
    api = Api(page)
    finished_try(page, live_server, seeded, api)
    api.stub("PUT", "/api/styles/style-1", {"style": {"id": "style-1"}})
    error = {"error": "photoshoot_not_ready", "message": "The shoot is still uploading."}
    api.stub("POST", "/api/jobs", error, status=409)
    page.get_by_label("Style text").fill(STYLE_TEXT + " Faster.")

    page.get_by_role("button", name="Try it").click()

    page.get_by_text("The shoot is still uploading.").wait_for()
    assert page.get_by_role("button", name="Use as the reference video").is_disabled()


def test_one_failed_poll_does_not_stop_following_the_try(page, live_server, seeded):
    api = Api(page)
    api.stub("POST", "/api/styles", {"style": {"id": "style-1"}}, status=201)
    api.stub("POST", "/api/jobs", {"job": DRAFT}, status=201)
    oops = {"error": "internal", "message": "Database busy."}
    api.stub("GET", "/api/jobs/job-1", [(500, oops), {"job": READY}])
    page.goto(live_server + "/styles/new")
    fill_form(page, seeded)

    page.get_by_role("button", name="Try it").click()

    page.get_by_text("Database busy.").wait_for()
    page.get_by_text("Try 1 is ready").wait_for(timeout=15000)
    assert page.locator("#error").is_hidden()


def test_revision_during_submit_does_not_paint_the_old_try(page, live_server, seeded):
    api = Api(page)
    api.stub("POST", "/api/styles", {"style": {"id": "style-1"}}, status=201)
    api.stub(
        "POST",
        "/api/jobs",
        [{"job": DRAFT}, {"job": {**DRAFT, "id": "job-2"}}],
        status=201,
    )
    api.stub("GET", "/api/jobs/job-1", {"job": PLANNED})
    api.stub("GET", "/api/jobs/job-2", {"job": {**DRAFT, "id": "job-2"}})
    api.stub("PUT", "/api/styles/style-1", {"style": {"id": "style-1"}})
    held = []

    def hold_submit(route):
        held.append(route)

    page.route("**/api/jobs/job-1/submit", hold_submit)
    page.goto(live_server + "/styles/new")
    fill_form(page, seeded)
    page.get_by_role("button", name="Try it").click()
    page.locator("#try").wait_for(state="visible")
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(100)
    assert held, "the first try never submitted"

    page.get_by_label("Style text").fill(STYLE_TEXT + " End on a Dolly Out.")
    page.get_by_role("button", name="Try it").click()
    page.get_by_text("Try 2: writing the shot plan").wait_for()
    assert page.locator("#try").is_hidden()

    queued = {**PLANNED, "status": "queued"}
    with page.expect_response("**/api/jobs/job-1/submit"):
        held[0].fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"job": queued}),
        )
    page.wait_for_timeout(400)
    assert "writing the shot plan" in page.locator("#try-status").inner_text()
    assert "waiting to make the video" not in page.locator("#try-status").inner_text()
    assert page.locator("#try").is_hidden()


def test_failed_style_update_keeps_the_ready_try(page, live_server, seeded):
    api = Api(page)
    finished_try(page, live_server, seeded, api)
    assert page.get_by_role("button", name="Use as the reference video").is_enabled()
    api.stub(
        "PUT",
        "/api/styles/style-1",
        (500, {"error": "internal", "message": "Could not save the style."}),
    )
    page.get_by_label("Style text").fill(STYLE_TEXT + " More gold.")

    page.get_by_role("button", name="Try it").click()

    page.get_by_text("Could not save the style.").wait_for()
    assert page.get_by_role("button", name="Use as the reference video").is_enabled()
    assert page.locator("#try-status").inner_text() == "Try 1 is ready."
    assert page.locator("#try").is_visible()
    assert len(api.bodies("POST", "/api/jobs")) == 1
    api.stub("POST", "/api/styles/style-1/reference", {"style": {"id": "style-1"}})
    page.get_by_role("button", name="Use as the reference video").click()
    page.get_by_text("is now the style's reference video").wait_for()
    assert api.bodies("POST", "/api/styles/style-1/reference") == [{"jobId": "job-1"}]


def test_failed_style_update_keeps_polling_the_try(page, live_server, seeded):
    api = Api(page)
    api.stub("POST", "/api/styles", {"style": {"id": "style-1"}}, status=201)
    api.stub("POST", "/api/jobs", {"job": DRAFT}, status=201)
    running = {**PLANNED, "status": "running"}
    api.stub("GET", "/api/jobs/job-1", [{"job": running}, {"job": READY}])
    api.stub(
        "PUT",
        "/api/styles/style-1",
        (500, {"error": "internal", "message": "Could not save the style."}),
    )
    page.goto(live_server + "/styles/new")
    fill_form(page, seeded)
    page.get_by_role("button", name="Try it").click()
    page.get_by_text("Try 1: making the video").wait_for()
    page.get_by_label("Style text").fill(STYLE_TEXT + " More gold.")

    page.get_by_role("button", name="Try it").click()

    page.get_by_text("Could not save the style.").wait_for()
    page.get_by_text("Try 1 is ready").wait_for(timeout=15000)
    assert page.get_by_role("button", name="Use as the reference video").is_enabled()
    assert len(api.bodies("GET", "/api/jobs/job-1")) >= 2
    assert page.locator("#error").inner_text() == "Could not save the style."


def test_non_json_error_page_shows_a_readable_message(page, live_server, seeded):
    api = Api(page)
    api.stub("POST", "/api/styles", "<html>Bad gateway</html>", status=502)
    page.goto(live_server + "/styles/new")
    fill_form(page, seeded)

    page.get_by_role("button", name="Try it").click()

    page.get_by_text("The server answered 502").wait_for()


def test_save_style_does_not_queue_a_try(page, live_server, seeded):
    api = Api(page)
    api.stub("POST", "/api/styles", {"style": {"id": "style-1"}}, status=201)
    page.goto(live_server + "/styles/new")
    fill_form(page, seeded)

    page.get_by_role("button", name="Save style", exact=True).click()

    page.wait_for_url(live_server + "/")
    page.get_by_role("heading", name="Styles", exact=True).wait_for()
    assert len(api.bodies("POST", "/api/styles")) == 1
    assert api.bodies("POST", "/api/jobs") == []
