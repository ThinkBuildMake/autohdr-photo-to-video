"""Editor screen (S17) in Chromium, with getJob, getPhotoshoot, editShot and exportJob stubbed."""

import time

import pytest
from playwright.sync_api import expect

from app.errors import AppError
from app.jobs.errors import JobNotFound
from app.jobs.plan_rules import MOVEMENTS
from app.jobs.schemas import ExportPlan, ShotEdit, ShotEditResult
from app.photoshoots.schemas import PhotoshootDetail
from app.shared.enums import JobStatus, ShotStatus
from app.shared.types import Job, JobShot, Photo
from tests.support.queue_rows import add_job, add_shoot, add_shot, add_song

pytestmark = pytest.mark.e2e

JOB_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SHOOT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
PHOTO_IDS = [f"cccccccc-cccc-4ccc-8ccc-cccccccccc0{n}" for n in range(1, 9)]
ROOMS = ["exterior_front", "living", "dining", "kitchen", "detail", "bedroom", "bathroom", "office"]
LENGTHS = [6.0, 7.0, 5.0, 8.0, 6.0, 8.0]
THUMB = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='9'%3E"
    "%3Crect width='16' height='9' fill='%23c9dcd9'/%3E%3C/svg%3E"
)
MOVEMENT_NAMES = [
    "Dolly In",
    "Dolly In (timelapse)",
    "Drone Top Down Descend",
    "Timelapse Variant",
    "Dolly Out",
    "Slider Truck Left to Right",
    "Slider Truck Right to Left",
    "Parallax Orbit",
    "Dolly In + Pan Right",
    "Crane Up",
    "Crane Down",
    "Orbit (Hyperlapse)",
]


def make_shot(n: int) -> JobShot:
    return JobShot(
        id=f"dddddddd-dddd-4ddd-8ddd-dddddddddd0{n}",
        position=n,
        room=ROOMS[n - 1],
        movement_name="dolly_in",
        movement_prompt=f"Prompt for shot {n}.",
        speed="slow",
        photo_edit_prompts=[f"Edit for shot {n}"],
        length_s=LENGTHS[n - 1],
        transition="cut",
        transition_s=0.0,
        photo_id=PHOTO_IDS[n - 1],
        removed=False,
        pending_change="none",
        plan_note="",
        edit_status="edited",
        edit_note=None,
        model="google/veo-3.1",
        used_fallback=False,
        status=ShotStatus.passed,
        status_detail="Passed the check.",
        failure_reason=None,
        attempts=1,
        clip_url=None,
    )


def make_job(status: JobStatus) -> Job:
    return Job(
        id=JOB_ID,
        style_id=None,
        style_name="Golden hour",
        photoshoot_id=SHOOT_ID,
        purpose="video",
        style_text="Slow and warm.",
        plan_status="ready",
        plan_notes=None,
        status=status,
        stop_reason=None,
        submitted_at="2026-10-19T08:00:00.000Z",
        started_at="2026-10-19T08:00:00.000Z",
        finished_at=None,
        elapsed_s=0.0,
        total_cost_usd=0.0,
        waiting_behind=None,
        shots=[make_shot(n) for n in range(1, 7)],
        video=None,
        song_credit="Sunrise Walk by Test Artist, CC BY-NC",
    )


def make_shoot() -> PhotoshootDetail:
    photos = [
        Photo(
            id=photo_id,
            position=n,
            original_name=f"photo-{n}.jpg",
            content_type="image/jpeg",
            size_bytes=1000,
            status="uploaded",
            room=ROOMS[n - 1],
            subject=None,
            thumb_url=THUMB,
        )
        for n, photo_id in enumerate(PHOTO_IDS, start=1)
    ]
    return PhotoshootDetail(id=SHOOT_ID, label="12 Oak Street", status="uploaded", photos=photos)


NEW_CLIP_FIELDS = {"photo_id", "movement_name", "movement_prompt", "speed", "photo_edit_prompts"}
RECUT_FIELDS = {"length_s", "transition", "transition_s"}


class EditorWorld:
    """The four stubbed operations behind the editor, recording what the page sends.

    edit_shot answers like the real route on a job with nothing removed in its last video."""

    def __init__(self, base_url: str, status: JobStatus):
        self.url = f"{base_url}/jobs/{JOB_ID}/edit"
        self.job = make_job(status)
        self.edits: list[tuple[int, dict]] = []
        self.marks: dict[int, str] = {}
        self.reply_delays: dict[str, float] = {}
        self.answered: list[str] = []
        self.edit_error: AppError | None = None
        self.warning = None
        self.fail_next = 0
        self.exports: list[str] = []
        self.export_error: AppError | None = None

    def get_job(self, job_id: str) -> Job:
        if job_id != JOB_ID:
            raise JobNotFound(job_id)
        return self.job

    def get_photoshoot(self, photoshoot_id: str) -> PhotoshootDetail:
        return make_shoot()

    def edit_shot(self, job_id: str, position: int, body: ShotEdit) -> ShotEditResult:
        self.edits.append((position, body.model_dump(by_alias=True, exclude_none=True)))
        if self.fail_next:
            self.fail_next -= 1
            error = self.edit_error
            self.edit_error = None
            self._reply("edit", body)
            raise error or AppError(400, "invalid_edit", "Rejected.")
        if self.edit_error:
            raise self.edit_error
        changes = body.model_dump(exclude_none=True)
        index = next(i for i, s in enumerate(self.job.shots) if s.position == position)
        shot = self.job.shots[index]
        if NEW_CLIP_FIELDS & changes.keys():
            self.marks[position] = "new_clip"
        elif RECUT_FIELDS & changes.keys() and self.marks.get(position) != "new_clip":
            self.marks[position] = "recut_only"
        removed = changes.get("removed", shot.removed)
        pending = "none" if removed else self.marks.get(position, "none")
        shot = shot.model_copy(update={**changes, "pending_change": pending})
        self.job.shots[index] = shot
        plan = ExportPlan(new_clips=0, recut_only=0, removed=0)
        self._reply("edit", body)
        return ShotEditResult(shot=shot, export_plan=plan, warning=self.warning)

    def export_job(self, job_id: str) -> Job:
        self.exports.append(job_id)
        if self.export_error:
            raise self.export_error
        self._reply("export", None)
        return self.job.model_copy(update={"status": JobStatus.queued})

    def _reply(self, kind: str, body: ShotEdit | None) -> None:
        """Hold the answer as slow network would, after the change is stored."""
        fields = body.model_dump(by_alias=True, exclude_none=True) if body else {kind: True}
        time.sleep(max((self.reply_delays.get(f, 0) for f in fields), default=0))
        self.answered.append(kind)


@pytest.fixture
def world_factory(monkeypatch, live_server):
    def build(status: JobStatus = JobStatus.ready) -> EditorWorld:
        world = EditorWorld(live_server, status)
        monkeypatch.setattr("app.jobs.queue.get_job", world.get_job)
        monkeypatch.setattr("app.photoshoots.service.get_photoshoot", world.get_photoshoot)
        monkeypatch.setattr("app.photoshoots.service.list_photos", lambda _: make_shoot().photos)
        monkeypatch.setattr("app.jobs.edits.edit_shot", world.edit_shot)
        monkeypatch.setattr("app.jobs.edits.export_job", world.export_job)
        return world

    return build


@pytest.fixture
def world(world_factory) -> EditorWorld:
    return world_factory()


def open_shot(page, n: int):
    page.locator(".tl").nth(n - 1).click()
    form = page.locator("form.shot-form:visible")
    expect(form).to_have_attribute("data-position", str(n))
    return form


def tile_change(page, n: int):
    return page.locator(".tl").nth(n - 1).locator(".tl-change")


def test_timeline_shows_six_shots_over_a_40_s_song_bar(page, world):
    page.goto(world.url)

    blocks = page.locator(".song-track .seg")
    expect(blocks).to_have_count(6)
    boxes = [blocks.nth(i).bounding_box() for i in range(6)]
    track = page.locator(".song-track").bounding_box()
    assert [b["x"] for b in boxes] == sorted(b["x"] for b in boxes)
    for box, length in zip(boxes, LENGTHS, strict=True):
        assert abs(box["width"] - track["width"] * length / 40) < 2
    expect(page.locator(".song-total")).to_have_text("0:40")
    expect(page.locator(".tl strong")).to_have_text([f"Shot {n}" for n in range(1, 7)])


def test_movement_list_is_the_12_names(page, world):
    page.goto(world.url)
    form = open_shot(page, 3)

    options = form.get_by_label("Camera movement").locator("option")

    assert options.all_inner_texts() == MOVEMENT_NAMES


def test_shot_card_offers_every_field(page, world):
    page.goto(world.url)

    form = open_shot(page, 2)

    expect(form.get_by_label("Swap the room (photo)")).to_have_value(PHOTO_IDS[1])
    expect(form.get_by_label("Camera movement")).to_have_value("dolly_in")
    expect(form.get_by_label("Speed")).to_have_value("slow")
    expect(form.get_by_label("Movement prompt")).to_have_value("Prompt for shot 2.")
    expect(form.get_by_label("Photo edit")).to_have_value("Edit for shot 2")
    expect(form.get_by_label("Length")).to_have_value("7")
    expect(form.get_by_label("Transition in")).to_have_value("cut")


def test_busy_job_cannot_be_edited(page, world_factory):
    world = world_factory(JobStatus.running)

    page.goto(world.url)

    expect(page.get_by_text("Re-exporting:", exact=False)).to_be_visible()
    controls = page.locator("form.shot-form :is(input, select, textarea, button)")
    assert controls.count() > 0
    for i in range(controls.count()):
        expect(controls.nth(i)).to_be_disabled()
    expect(page.get_by_role("button", name="Re-export video")).to_be_disabled()


def test_running_reexport_shows_how_many_shots_are_being_made(page, world_factory):
    world = world_factory(JobStatus.running)
    for i in (0, 2):
        world.job.shots[i] = world.job.shots[i].model_copy(update={"status": ShotStatus.generating})

    page.goto(world.url)

    expect(
        page.get_by_text("Re-exporting: making 2 changed shots, then re-cutting the video")
    ).to_be_visible()
    expect(
        page.get_by_text("Shots you did not change are reused. About 2 minutes.")
    ).to_be_visible()


def test_running_recut_only_reexport_says_it_is_recutting(page, world_factory):
    world = world_factory(JobStatus.running)

    page.goto(world.url)

    expect(page.get_by_text("Re-exporting: re-cutting the video", exact=False)).to_be_visible()
    expect(page.get_by_text("making 0")).to_have_count(0)


def test_swapped_photo_does_not_show_the_old_first_frame(page, world):
    page.goto(world.url)
    form = open_shot(page, 2)

    form.get_by_label("Swap the room (photo)").select_option(PHOTO_IDS[6])

    expect(tile_change(page, 2)).to_have_text("will be made again")
    frame = page.locator(".ed-grid:visible .frame-preview")
    expect(frame.locator(".first-frame")).to_be_hidden()
    expect(frame.get_by_text("New first frame is made on re-export")).to_be_visible()


def test_swapping_a_photo_saves_it_and_marks_the_shot_remade(page, world):
    page.goto(world.url)
    form = open_shot(page, 2)

    form.get_by_label("Swap the room (photo)").select_option(PHOTO_IDS[6])

    expect(tile_change(page, 2)).to_have_text("will be made again")
    assert world.edits == [(2, {"photoId": PHOTO_IDS[6]})]


def test_an_edit_touches_only_its_shot(page, world):
    page.goto(world.url)
    form = open_shot(page, 2)

    form.get_by_label("Swap the room (photo)").select_option(PHOTO_IDS[6])

    expect(tile_change(page, 2)).to_have_text("will be made again")
    for n in (1, 3, 4, 5, 6):
        expect(tile_change(page, n)).to_have_text("unchanged")


def test_changing_movement_sends_its_starter_prompt(page, world):
    page.goto(world.url)
    form = open_shot(page, 3)

    form.get_by_label("Camera movement").select_option(label="Crane Up")

    expect(tile_change(page, 3)).to_have_text("will be made again")
    expect(form.get_by_label("Movement prompt")).to_have_value(MOVEMENTS["crane_up"])
    crane_up = {"movementName": "crane_up", "movementPrompt": MOVEMENTS["crane_up"]}
    assert world.edits == [(3, crane_up)]


def test_transition_change_sends_a_crossfade_length(page, world):
    page.goto(world.url)
    form = open_shot(page, 4)

    form.get_by_label("Transition in").select_option("crossfade")

    expect(tile_change(page, 4)).to_have_text("only re-cut")
    assert world.edits == [(4, {"transition": "crossfade", "transitionS": 0.4})]


def test_length_change_only_recuts(page, world):
    page.goto(world.url)
    form = open_shot(page, 1)

    form.get_by_label("Length").fill("3.5")
    form.get_by_label("Length").blur()

    expect(tile_change(page, 1)).to_have_text("only re-cut")
    assert world.edits == [(1, {"lengthS": 3.5})]


@pytest.fixture
def real_job(live_server, bucket):
    """A ready job of six 3 s shots in the database, edited through the real Jobs routes."""
    shoot_id, photos = add_shoot(n_photos=6)
    job_id = add_job(shoot_id, add_song(), status="ready", submitted_at="2026-10-19T08:00:00.000Z")
    for position, photo_id in enumerate(photos, start=1):
        add_shot(job_id, position, photo_id, status="passed")
    return f"{live_server}/jobs/{job_id}/edit"


def test_removing_a_shot_closes_the_song_bar_gap(page, real_job):
    page.goto(real_job)
    form = open_shot(page, 5)

    form.get_by_role("button", name="Remove this room from the video").click()

    expect(tile_change(page, 5)).to_have_text("removed")
    blocks = page.locator(".song-track .seg")
    expect(blocks.nth(4)).to_be_hidden()
    shot4, shot6 = blocks.nth(3).bounding_box(), blocks.nth(5).bounding_box()
    assert abs(shot6["x"] - (shot4["x"] + shot4["width"])) < 1
    expect(page.locator(".song-total")).to_have_text("0:15")


def test_the_last_kept_shot_cannot_be_removed(page, real_job):
    page.goto(real_job)
    for n in range(1, 6):
        form = open_shot(page, n)
        form.get_by_role("button", name="Remove this room from the video").click()
        expect(tile_change(page, n)).to_have_text("removed")

    form = open_shot(page, 6)

    expect(form.get_by_role("button", name="Remove this room from the video")).to_be_disabled()
    expect(form.locator(".remove-why")).to_be_visible()


def test_putting_a_shot_back_shows_unchanged(page, real_job):
    page.goto(real_job)
    form = open_shot(page, 5)
    form.get_by_role("button", name="Remove this room from the video").click()
    expect(tile_change(page, 5)).to_have_text("removed")

    form.get_by_role("button", name="Put this room back").click()

    expect(tile_change(page, 5)).to_have_text("unchanged")
    expect(page.locator(".song-total")).to_have_text("0:18")


def test_bad_edit_message_appears_next_to_length(page, world):
    world.edit_error = AppError(400, "invalid_edit", "Length 9 s is longer than the 8 s clip.")
    page.goto(world.url)
    form = open_shot(page, 1)

    form.get_by_label("Length").fill("9")
    form.get_by_label("Length").blur()

    expect(form.locator('.field-error[data-for="lengthS"]')).to_have_text(
        "Length 9 s is longer than the 8 s clip."
    )
    expect(tile_change(page, 1)).to_have_text("unchanged")


def test_reexport_calls_export_and_opens_the_job_page(page, world):
    page.goto(world.url)
    open_shot(page, 2).get_by_label("Swap the room (photo)").select_option(PHOTO_IDS[6])
    expect(tile_change(page, 2)).to_have_text("will be made again")
    length = open_shot(page, 1).get_by_label("Length")
    length.fill("3.5")
    length.blur()
    expect(tile_change(page, 1)).to_have_text("only re-cut")
    expect(page.locator(".export-note")).to_have_text(
        "1 shot will be made again, 1 only re-cut; the rest are reused"
        " and the video is re-cut to the song."
    )

    page.get_by_role("button", name="Re-export video").click()

    expect(page).to_have_url(world.url.removesuffix("/edit"))
    assert world.exports == [JOB_ID]


def test_reexport_error_is_shown_by_the_button(page, world):
    world.export_error = AppError(409, "nothing_to_export", "Nothing changed since the last video.")
    page.goto(world.url)

    page.get_by_role("button", name="Re-export video").click()

    expect(page.locator(".export-note")).to_have_text("Nothing changed since the last video.")
    expect(page).to_have_url(world.url)


def test_reexport_waits_for_a_save_in_flight(page, world):
    world.reply_delays = {"lengthS": 0.5}
    page.goto(world.url)
    length = open_shot(page, 1).get_by_label("Length")
    length.fill("3.5")
    length.blur()

    page.get_by_role("button", name="Re-export video").click()

    expect(page).to_have_url(world.url.removesuffix("/edit"))
    assert world.answered == ["edit", "export"]


def test_reexport_sends_one_request_and_is_disabled_meanwhile(page, world):
    world.reply_delays = {"export": 0.5}
    page.goto(world.url)
    button = page.get_by_role("button", name="Re-export video")

    button.dblclick()

    expect(button).to_be_disabled()
    expect(page).to_have_url(world.url.removesuffix("/edit"))
    assert world.exports == [JOB_ID]


def test_reexport_waits_and_stops_when_a_save_fails(page, world):
    world.edit_error = AppError(400, "invalid_edit", "Length 9 s is longer than the 8 s clip.")
    page.goto(world.url)
    length = open_shot(page, 1).get_by_label("Length")
    length.fill("9")
    length.blur()

    page.get_by_role("button", name="Re-export video").click()

    expect(page.locator(".export-note")).to_have_text(
        "Some changes were not saved. Fix the fields marked in red, then re-export."
    )
    assert world.exports == []
    expect(page.get_by_role("button", name="Re-export video")).to_be_enabled()


def test_a_late_reply_does_not_overwrite_a_newer_edit(page, world):
    world.reply_delays = {"lengthS": 0.6}
    page.goto(world.url)
    form = open_shot(page, 5)
    form.get_by_label("Length").fill("3.5")
    form.get_by_label("Length").blur()

    form.get_by_role("button", name="Remove this room from the video").click()

    while len(world.answered) < 2:
        page.wait_for_timeout(50)
    expect(tile_change(page, 5)).to_have_text("removed")
    expect(form.get_by_role("button", name="Put this room back")).to_be_visible()
    expect(page.locator(".song-track .seg").nth(4)).to_be_hidden()
    expect(page.locator(".song-total")).to_have_text("0:34")
    assert world.edits == [(5, {"lengthS": 3.5}), (5, {"removed": True})]


def test_total_pads_seconds_before_a_fraction(page, world):
    page.goto(world.url)
    length = open_shot(page, 1).get_by_label("Length")

    length.fill("31.5")
    length.blur()

    expect(page.locator(".song-total")).to_have_text("1:05.5")


def test_save_that_cannot_reach_the_server_says_so(page, world):
    page.route("**/api/jobs/*/shots/*", lambda route: route.abort())
    page.goto(world.url)
    length = open_shot(page, 1).get_by_label("Length")

    length.fill("3.5")
    length.blur()

    expect(page.locator('form.shot-form:visible .field-error[data-for="lengthS"]')).to_have_text(
        "Could not reach the server; the change was not saved."
    )


def test_reexport_that_cannot_reach_the_server_says_so(page, world):
    page.route("**/api/jobs/*/export", lambda route: route.abort())
    page.goto(world.url)

    page.get_by_role("button", name="Re-export video").click()

    expect(page.locator(".export-note")).to_have_text(
        "Could not reach the server; the video was not re-exported."
    )
    expect(page.get_by_role("button", name="Re-export video")).to_be_enabled()


def test_rejected_movement_change_restores_the_saved_movement_and_prompt(page, world):
    world.edit_error = AppError(400, "invalid_edit", "Shot 3: no.")
    page.goto(world.url)
    form = open_shot(page, 3)

    form.get_by_label("Camera movement").select_option(label="Crane Up")

    expect(form.get_by_label("Camera movement")).to_have_value("dolly_in")
    expect(form.locator('.field-error[data-for="movementName"]')).to_be_empty()
    expect(form.get_by_label("Movement prompt")).to_have_value("Prompt for shot 3.")


def test_a_failed_movement_save_does_not_restore_over_a_newer_choice(page, world):
    world.fail_next = 1
    world.edit_error = AppError(400, "invalid_edit", "Shot 3: no.")
    world.reply_delays = {"movementName": 0.6}
    page.goto(world.url)
    form = open_shot(page, 3)

    page.set_default_timeout(8000)
    movement = form.get_by_label("Camera movement")
    movement.select_option(label="Crane Up")
    movement.select_option(label="Dolly Out")
    for _ in range(40):
        if len(world.answered) >= 2:
            break
        page.wait_for_timeout(50)
    else:
        raise AssertionError(f"saves did not finish: {world.edits!r} {world.answered!r}")

    expect(form.get_by_label("Camera movement")).to_have_value("dolly_out")
    expect(form.get_by_label("Movement prompt")).to_have_value(MOVEMENTS["dolly_out"])
    expect(form.locator('.field-error[data-for="movementName"]')).to_be_empty()
    assert world.job.shots[2].movement_name == "dolly_out"
    page.get_by_role("button", name="Re-export video").click()
    expect(page).to_have_url(world.url.removesuffix("/edit"))
    assert world.exports == [JOB_ID]


def test_a_failed_movement_save_does_not_restore_a_queued_prompt(page, world):
    world.fail_next = 1
    world.edit_error = AppError(400, "invalid_edit", "Shot 3: no.")
    world.reply_delays = {"movementName": 0.6}
    page.goto(world.url)
    page.set_default_timeout(8000)
    form = open_shot(page, 3)
    prompt = form.get_by_label("Movement prompt")

    form.get_by_label("Camera movement").select_option(label="Crane Up")
    prompt.fill("Custom prompt for the crane.")
    prompt.blur()
    wait_for_answers(page, world, 2)

    expect(form.get_by_label("Camera movement")).to_have_value("dolly_in")
    expect(prompt).to_have_value("Custom prompt for the crane.")
    expect(form.locator('.field-error[data-for="movementName"]')).to_be_empty()
    expect(form.locator('.field-error[data-for="movementPrompt"]')).to_be_empty()
    assert world.job.shots[2].movement_name == "dolly_in"
    assert world.job.shots[2].movement_prompt == "Custom prompt for the crane."
    expect(tile_change(page, 3)).to_have_text("will be made again")
    page.get_by_role("button", name="Re-export video").click()
    expect(page).to_have_url(world.url.removesuffix("/edit"))
    assert world.exports == [JOB_ID]


def wait_for_answers(page, world, n: int):
    for _ in range(40):
        if len(world.answered) >= n:
            return
        page.wait_for_timeout(50)
    raise AssertionError(f"saves did not finish: {world.edits!r} {world.answered!r}")


def test_a_failed_save_does_not_reset_a_queued_remove(page, world):
    world.fail_next = 1
    world.edit_error = AppError(400, "invalid_edit", "Length 9 s is longer than the 8 s clip.")
    world.reply_delays = {"lengthS": 0.6}
    page.goto(world.url)
    page.set_default_timeout(8000)
    form = open_shot(page, 5)
    length = form.get_by_label("Length")

    length.fill("9")
    length.blur()
    form.get_by_role("button", name="Remove this room from the video").click()
    wait_for_answers(page, world, 2)

    expect(form.get_by_role("button", name="Put this room back")).to_be_visible()
    form.get_by_role("button", name="Put this room back").click()
    wait_for_answers(page, world, 3)
    assert world.edits[-1] == (5, {"removed": False})


def test_a_restored_movement_does_not_block_reexport(page, world):
    world.edit_error = AppError(400, "invalid_edit", "Shot 3: no.")
    page.goto(world.url)
    form = open_shot(page, 3)

    form.get_by_label("Camera movement").select_option(label="Crane Up")

    expect(form.get_by_label("Camera movement")).to_have_value("dolly_in")
    expect(form.get_by_label("Movement prompt")).to_have_value("Prompt for shot 3.")
    expect(form.locator('.field-error[data-for="movementName"]')).to_be_empty()
    open_shot(page, 1)
    page.get_by_role("button", name="Re-export video").click()
    expect(page).to_have_url(world.url.removesuffix("/edit"))
    assert world.exports == [JOB_ID]


def test_a_thrown_save_does_not_stop_later_saves(page, world):
    calls = {"n": 0}

    def handle(route):
        calls["n"] += 1
        if calls["n"] == 1:
            route.fulfill(status=200, content_type="application/json", body="null")
        else:
            route.continue_()

    page.route("**/api/jobs/*/shots/*", handle)
    page.goto(world.url)
    form = open_shot(page, 1)
    length = form.get_by_label("Length")

    length.fill("3.5")
    length.blur()
    form.get_by_label("Speed").select_option("fast")

    expect(tile_change(page, 1)).to_have_text("will be made again")
    assert (1, {"speed": "fast"}) in world.edits


def test_length_reply_preserves_an_unsent_prompt_then_saves_and_reexports(page, world):
    world.reply_delays = {"lengthS": 0.6}
    page.goto(world.url)
    form = open_shot(page, 3)
    length = form.get_by_label("Length")
    prompt = form.get_by_label("Movement prompt")

    length.fill("3.5")
    length.blur()
    prompt.fill("New prompt typed while length saves.")
    expect(tile_change(page, 3)).to_have_text("only re-cut")
    expect(prompt).to_have_value("New prompt typed while length saves.")
    assert world.edits == [(3, {"lengthS": 3.5})]

    prompt.blur()
    expect(tile_change(page, 3)).to_have_text("will be made again")
    assert world.job.shots[2].movement_prompt == "New prompt typed while length saves."
    assert world.edits[-1] == (3, {"movementPrompt": "New prompt typed while length saves."})
    page.get_by_role("button", name="Re-export video").click()
    expect(page).to_have_url(world.url.removesuffix("/edit"))
    assert world.exports == [JOB_ID]


@pytest.mark.parametrize("field", ["lengthS", "movementName"])
def test_saved_edit_during_model_outage_reconciles_and_allows_export(page, world, field):
    world.warning = (
        "Your edit was saved, but video model limits could not be checked. "
        "Check the shot lengths before exporting."
    )
    page.goto(world.url)
    form = open_shot(page, 1)
    if field == "lengthS":
        form.get_by_label("Length").fill("3.5")
        form.get_by_label("Length").blur()
        expect(page.locator(".tl").first.locator(".tl-len")).to_have_text("3.5 s")
        expect(tile_change(page, 1)).to_have_text("only re-cut")
        expect(page.locator(".song-total")).to_have_text("0:37.5")
        assert world.job.shots[0].length_s == 3.5
    else:
        form.get_by_label("Camera movement").select_option(label="Crane Up")
        expect(tile_change(page, 1)).to_have_text("will be made again")
        expect(form.get_by_label("Camera movement")).to_have_value("crane_up")
        expect(form.get_by_label("Movement prompt")).to_have_value(MOVEMENTS["crane_up"])
        assert world.job.shots[0].movement_name == "crane_up"
    expect(form.locator(".save-warning")).to_have_text(world.warning)
    for error in form.locator(".field-error").all():
        expect(error).to_be_empty()
    page.get_by_role("button", name="Re-export video").click()
    expect(page).to_have_url(world.url.removesuffix("/edit"))
    assert world.exports == [JOB_ID]


@pytest.mark.parametrize("status", [JobStatus.draft, JobStatus.stopped])
def test_unfinished_job_has_a_clear_disabled_editor(page, world_factory, status):
    world = world_factory(status)

    page.goto(world.url)

    expect(page.get_by_text("This video is not ready to edit")).to_be_visible()
    expect(page.get_by_role("button", name="Re-export video")).to_be_disabled()
    expect(open_shot(page, 1).get_by_label("Camera movement")).to_be_disabled()


@pytest.mark.parametrize("state", ["edited", "crop_only", None])
def test_original_and_stored_first_frame_are_paired_truthfully(page, world, state):
    shot = world.job.shots[0]
    shot.photo_url = THUMB
    shot.first_frame_url = THUMB if state else None
    shot.edit_status = state

    page.goto(world.url)

    pair = page.locator('.ed-grid[data-position="1"] .preview-pair')
    expect(pair.locator(".original-photo")).to_have_attribute("src", THUMB)
    if state:
        expect(pair.locator(".first-frame")).to_have_attribute("src", THUMB)
        expect(pair.locator(".first-frame")).to_be_visible()
        caption = "Cropped first frame" if state == "crop_only" else "Edited first frame"
        expect(pair.locator(".frame-preview figcaption")).to_have_text(caption)
    else:
        expect(pair.locator(".first-frame")).to_be_hidden()
        expect(pair.get_by_text("First frame unavailable")).to_be_visible()
