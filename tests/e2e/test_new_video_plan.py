import re

import pytest
from playwright.sync_api import expect

from app.jobs.plan_rules import MOVEMENTS
from app.library.stubs import GOLDEN_HOUR_ID, STUB_SONG_ID, STUB_STYLES
from tests.e2e.stubs import JOB_ID, SHOOT_ID, JobStub, ShootStub, drop_files, job, jpeg, photo
from tests.support.library_rows import stub_presets  # noqa: F401

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("stub_presets")]

PHOTOS = [photo(1, "living"), photo(2, "kitchen"), photo(3, "bedroom")]
POOL_NOTE = "the text asks for a pool; no pool photo"


def open_plan(page, live_server, *answers):
    ShootStub(page, PHOTOS)
    jobs = JobStub(page, *answers)
    page.goto(f"{live_server}/new?jobId={JOB_ID}")
    return jobs


def cards(page):
    return page.locator(".shot-card")


def test_plan_cards_appear_when_ready(page, live_server):
    ShootStub(page, PHOTOS)
    jobs = JobStub(page, job("planning"), job("ready"))
    page.goto(f"{live_server}/new?styleId={GOLDEN_HOUR_ID}")
    drop_files(page, [jpeg("photo-1.jpg"), jpeg("photo-2.jpg"), jpeg("photo-3.jpg")])
    expect(page.locator("#photo-grid .tile")).to_have_count(3)

    page.get_by_role("button", name="Next: write the shot plan").click()

    expect(cards(page)).to_have_count(6)
    assert jobs.created == [
        {
            "photoshootId": SHOOT_ID,
            "styleText": STUB_STYLES[0].style_text,
            "songId": STUB_SONG_ID,
            "styleId": GOLDEN_HOUR_ID,
        }
    ]
    for n in range(6):
        card = cards(page).nth(n)
        expect(card.locator("img.shot-photo")).to_have_attribute(
            "src", f"/stub-media/thumb-{n % 3 + 1}.svg"
        )
        expect(card.get_by_label("Camera movement")).to_have_value("dolly_in")
        expect(card.get_by_label("Speed")).to_have_value("slow")
        expect(card.get_by_label("Length")).to_have_value("4")
        expect(card.get_by_label("Transition in")).to_have_value("cut")
        expect(card.locator(".plan-note")).to_have_text(f"From the text: shot {n + 1}")


def test_changed_shot_is_saved(page, live_server):
    jobs = open_plan(page, live_server, job("ready"))
    cards(page).nth(2).get_by_label("Camera movement").select_option(label="Crane Up")

    page.get_by_role("button", name="Save the plan").click()

    expect(page.get_by_text("Plan saved")).to_be_visible()
    third = jobs.saved[0][2]
    assert third["position"] == 3
    assert third["movementName"] == "crane_up"
    assert third["movementPrompt"] == MOVEMENTS["crane_up"]


def test_removed_shot_is_saved(page, live_server):
    jobs = open_plan(page, live_server, job("ready"))
    cards(page).nth(3).get_by_role("button", name="Remove shot").click()

    page.get_by_role("button", name="Save the plan").click()

    expect(page.get_by_text("Plan saved")).to_be_visible()
    assert len(jobs.saved[0]) == 5
    assert "shot-4" not in [s.get("id") for s in jobs.saved[0]]


def test_added_shot_is_saved(page, live_server):
    jobs = open_plan(page, live_server, job("ready"))
    page.get_by_role("button", name="Add a shot").click()
    cards(page).nth(6).get_by_label("Camera movement").select_option(label="Dolly Out")

    page.get_by_role("button", name="Save the plan").click()

    expect(page.get_by_text("Plan saved")).to_be_visible()
    assert len(jobs.saved[0]) == 7
    assert jobs.saved[0][-1]["movementName"] == "dolly_out"
    assert jobs.saved[0][-1]["position"] == 7


def test_plan_note_banner_above_cards(page, live_server):
    open_plan(page, live_server, job("ready", plan_notes=POOL_NOTE))

    banner = page.locator("#plan-notes")

    expect(banner).to_contain_text(POOL_NOTE)
    expect(cards(page)).to_have_count(6)
    assert banner.bounding_box()["y"] < cards(page).first.bounding_box()["y"]


def test_make_my_video_submits_and_opens_the_job(page, live_server):
    jobs = open_plan(page, live_server, job("ready"))
    expect(cards(page)).to_have_count(6)

    page.get_by_role("button", name="Make my video").click()

    expect(page).to_have_url(re.compile(rf"/jobs/{JOB_ID}$"))
    assert jobs.submitted == 1


def test_make_my_video_saves_the_plan_before_submitting(page, live_server):
    jobs = open_plan(page, live_server, job("ready"))
    cards(page).nth(0).get_by_label("Camera movement").select_option(label="Crane Up")

    page.get_by_role("button", name="Make my video").click()

    expect(page).to_have_url(re.compile(rf"/jobs/{JOB_ID}$"))
    assert jobs.calls == ["save", "submit"]
    assert jobs.saved[0][0]["movementName"] == "crane_up"


def test_failed_save_shows_the_error_and_does_not_submit(page, live_server):
    jobs = open_plan(page, live_server, job("ready"))
    jobs.save_error = "Shot 2: the length must be above 0."
    expect(cards(page)).to_have_count(6)

    page.get_by_role("button", name="Make my video").click()

    expect(page.locator("#page-error")).to_have_text("Shot 2: the length must be above 0.")
    assert jobs.calls == ["save"]
    expect(page.get_by_role("button", name="Make my video")).to_be_enabled()


def test_double_click_on_next_makes_one_draft(page, live_server):
    ShootStub(page, PHOTOS)
    jobs = JobStub(page, job("planning"), job("ready"))
    page.goto(f"{live_server}/new?styleId={GOLDEN_HOUR_ID}")
    drop_files(page, [jpeg("photo-1.jpg"), jpeg("photo-2.jpg"), jpeg("photo-3.jpg")])
    expect(page.locator("#photo-grid .tile")).to_have_count(3)

    page.get_by_role("button", name="Next: write the shot plan").dblclick()

    expect(cards(page)).to_have_count(6)
    assert len(jobs.created) == 1


def test_failed_plan_offers_try_again(page, live_server):
    reason = "The planner's plan broke the rules twice: shot 2 is longer than 8 s."
    jobs = open_plan(page, live_server, job("failed", plan_notes=reason))

    failed = page.locator("#plan-failed")
    expect(failed).to_contain_text(reason)
    failed.get_by_role("button", name="Try again").click()

    expect(page.locator("#plan-wait")).to_be_visible()
    assert jobs.replanned == 1


def test_pages_run_without_script_errors_in_chromium(page, live_server, browser_name):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(live_server + "/")
    page.goto(f"{live_server}/new?styleId={GOLDEN_HOUR_ID}")

    open_plan(page, live_server, job("ready"))
    expect(cards(page)).to_have_count(6)

    assert browser_name == "chromium"
    assert errors == []
