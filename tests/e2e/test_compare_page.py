import json

import pytest

from app.library.stubs import GOLDEN_HOUR_ID, STUB_REFERENCE_JOB_ID
from tests.support.library_rows import stub_presets  # noqa: F401

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("stub_presets")]

REPRO_ID = "repro-1"
CREDIT = "Track A, Artist A, CC BY-NC, https://example.com/music/track-a"
JOBS = [
    {"id": "other", "styleName": "Crisp modern", "photoshootLabel": "Condo",
     "purpose": "reproduction", "status": "ready", "submittedAt": None, "elapsedS": 1.0},
    {"id": REPRO_ID, "styleName": "Golden hour", "photoshootLabel": "4-bed house",
     "purpose": "reproduction", "status": "ready", "submittedAt": None, "elapsedS": 1.0},
    {"id": STUB_REFERENCE_JOB_ID, "styleName": "Golden hour", "photoshootLabel": "Lake house",
     "purpose": "video", "status": "ready", "submittedAt": None, "elapsedS": 1.0},
]  # fmt: skip
MOVES = ["drone_top_down_descend", "dolly_in", "slider_truck_left_to_right", "dolly_in",
         "parallax_orbit", "crane_up", "dolly_out"]  # fmt: skip


def timing(length_s, error_s):
    return {"lengthS": length_s, "cutErrorS": error_s}


SHOTS = [
    {
        "position": n,
        "movementName": MOVES[n - 1],
        "transition": "cut",
        "reference": timing(6.0, 0.02),
        "reproduction": timing(6.5, 0.06 if n == 3 else 0.01) if n <= 6 else None,
        "flagged": n == 3,
    }
    for n in range(1, 8)
]
COMPARISON = {
    "reference": {"jobId": STUB_REFERENCE_JOB_ID, "videoUrl": "/stub-media/reference.mp4",
                  "photoshootLabel": "Lake house"},
    "reproduction": {"jobId": REPRO_ID, "videoUrl": "/stub-media/repro.mp4",
                     "photoshootLabel": "4-bed house"},
    "song": {"sameSong": True, "credit": CREDIT},
    "sameText": True,
    "summary": {
        "reference": {"shotCount": 7, "totalS": 42.0, "medianShotS": 6.0,
                      "movements": {"dolly_in": 2, "crane_up": 1, "dolly_out": 4},
                      "transitions": {"cut": 5, "crossfade": 2}},
        "reproduction": {"shotCount": 6, "totalS": 39.0, "medianShotS": 6.5,
                         "movements": {"dolly_in": 2, "crane_up": 1, "dolly_out": 3},
                         "transitions": {"cut": 4, "crossfade": 2}},
    },
    "shots": SHOTS,
    "maxCutErrorS": 0.06,
}  # fmt: skip
PAGE = f"/styles/{GOLDEN_HOUR_ID}/reproductions"


def open_page(page, live_server, body, status=200, jobs=JOBS, query=""):
    seen = []
    content_type = "application/json" if isinstance(body, dict) else "text/html"
    text = json.dumps(body) if isinstance(body, dict) else body

    def reproduction(route, request):
        seen.append(request.url)
        route.fulfill(status=status, content_type=content_type, body=text)

    page.route("**/api/jobs", lambda route: route.fulfill(json={"jobs": jobs}))
    page.route(f"**/api/styles/{GOLDEN_HOUR_ID}/reproductions/*", reproduction)
    page.goto(live_server + PAGE + query)
    return seen


def repro(job_id, label, status="ready"):
    return {**JOBS[1], "id": job_id, "photoshootLabel": label, "status": status}


def with_changes(shots=None, **reference_summary):
    summary = {**COMPARISON["summary"]}
    summary["reference"] = {**summary["reference"], **reference_summary}
    return {**COMPARISON, "summary": summary, "shots": shots or SHOTS}


def test_two_players_and_play_both(page, live_server):
    seen = open_page(page, live_server, COMPARISON)

    page.get_by_role("heading", name="How the two videos compare").wait_for()
    assert seen[0].endswith(f"/reproductions/{REPRO_ID}")
    sources = page.locator("video").evaluate_all("vs => vs.map(v => v.getAttribute('src'))")
    assert sources == ["/stub-media/reference.mp4", "/stub-media/repro.mp4"]
    assert page.get_by_role("button", name="Play both").is_visible()
    assert page.get_by_text("Reference video · Lake house").is_visible()
    assert page.get_by_text("Reproduction · 4-bed house").first.is_visible()
    assert "Track A, Artist A, CC BY-NC" in page.locator("#song").inner_text()
    assert "example.com" not in page.locator("main").inner_text()
    assert "stub-media" not in page.locator("main").inner_text()


def test_both_plans_line_up(page, live_server):
    open_page(page, live_server, COMPARISON)

    page.get_by_role("heading", name="How the two videos compare").wait_for()
    summary = [r.split("\t") for r in page.locator("#summary tr").all_inner_texts()]
    assert summary == [
        ["Shots", "7", "6"],
        ["Length", "0:42", "0:39"],
        ["Typical shot", "6 s", "6.5 s"],
        ["Movements", "Dolly in ×2, Crane up, Dolly out ×4", "Dolly in ×2, Crane up, Dolly out ×3"],
        ["Transitions", "Cut ×5, Crossfade ×2", "Cut ×4, Crossfade ×2"],
    ]
    rows = [r.split("\t") for r in page.locator("#shots tr").all_inner_texts()]
    assert [r[0] for r in rows] == ["1", "2", "3", "4", "5", "6", "7"]
    assert rows[0][1:4] == ["Drone top down descend · Cut", "6 s", "6.5 s"]
    assert rows[6][1:4] == ["Dolly out · Cut", "6 s", "–"]


def test_flagged_shot_and_worst_cut_error(page, live_server):
    open_page(page, live_server, COMPARISON)

    page.get_by_role("heading", name="Shot by shot").wait_for()
    flags = [r.split("\t")[-1] for r in page.locator("#shots tr").all_inner_texts()]
    assert flags == ["", "", "Flagged", "", "", "", ""]
    assert "0.06 s" in page.locator("#worst-cut").inner_text()


def test_no_reference_yet(page, live_server):
    body = {"error": "no_reference", "message": "Server wording."}
    open_page(page, live_server, body, status=409)

    message = page.get_by_text("This style has no reference video yet")
    message.wait_for()
    assert "Server wording" not in page.locator("main").inner_text()
    assert page.locator("video:visible").count() == 0


def test_early_cut_beyond_the_limit_is_marked_over(page, live_server):
    early = {**SHOTS[0], "reference": timing(6.0, -0.3)}
    open_page(page, live_server, with_changes(shots=[early, *SHOTS[1:]]))

    page.get_by_role("heading", name="Shot by shot").wait_for()
    first = page.locator("#shots tr").first.inner_text().split("\t")
    assert first[4] == "-0.3 s over / 0.01 s"


def test_length_rounds_the_total_before_splitting_minutes(page, live_server):
    open_page(page, live_server, with_changes(totalS=59.5))

    page.get_by_role("heading", name="How the two videos compare").wait_for()
    length = page.locator("#summary tr").nth(1).inner_text().split("\t")
    assert length == ["Length", "1:00", "0:39"]


def test_job_id_in_the_url_picks_that_reproduction(page, live_server):
    jobs = [repro("repro-2", "Condo"), *JOBS]
    seen = open_page(page, live_server, COMPARISON, jobs=jobs, query=f"?jobId={REPRO_ID}")

    page.get_by_role("heading", name="Shot by shot").wait_for()
    assert seen[0].endswith(f"/reproductions/{REPRO_ID}")
    assert page.get_by_role("link", name="4-bed house").get_attribute("class") == "btn sm"
    assert page.get_by_role("link", name="Condo").get_attribute("class") == "btn alt sm"


def test_default_pick_is_the_newest_finished_reproduction(page, live_server):
    jobs = [repro("repro-new", "Condo", status="running"), *JOBS]
    seen = open_page(page, live_server, COMPARISON, jobs=jobs)

    page.get_by_role("heading", name="Shot by shot").wait_for()
    assert seen[0].endswith(f"/reproductions/{REPRO_ID}")


def test_default_pick_falls_back_to_the_newest_when_none_finished(page, live_server):
    jobs = [repro("repro-new", "Condo", status="running"), repro("repro-old", "Barn", "queued")]
    seen = open_page(page, live_server, COMPARISON, jobs=jobs)

    page.get_by_role("heading", name="Shot by shot").wait_for()
    assert seen[0].endswith("/reproductions/repro-new")


def test_non_json_error_page_shows_a_readable_message(page, live_server):
    open_page(page, live_server, "<html>Bad gateway</html>", status=502)

    page.get_by_text("The server answered 502").wait_for()
    assert "Unexpected token" not in page.locator("main").inner_text()
