import pytest

from app.config import get_settings
from app.pipeline import prepare
from app.providers.errors import ProviderError
from app.shared.enums import ProviderErrorKind
from tests.pipeline import shot_world
from tests.pipeline.clip_world import make_shot
from tests.pipeline.shot_world import changed_check, clean_check

JOB = "J"
SHOOT = "S"


def first_frame(shot, tmp_path):
    return prepare.first_frame(JOB, SHOOT, shot, 0, tmp_path)


def crop_of(shot) -> bytes:
    return f"crop(photo:{shot.photo_id})".encode()


def edits(world):
    return [(e["jpeg"], e["prompt"], e["model"]) for e in world.named("edit_photo")]


def photo_record(world, shot):
    (record,) = world.named("set_shot_photo", shot.id)
    return record


def test_edits_run_in_order(monkeypatch, tmp_path):
    world = shot_world.install(monkeypatch)
    shot = make_shot(1, photo_edit_prompts=["Brighten the room", "Straighten the verticals"])
    model = get_settings().ENHANCE_MODEL

    first_frame(shot, tmp_path)

    crop = crop_of(shot)
    assert edits(world) == [
        (crop, "Brighten the room", model),
        (crop + b"+Brighten the room", "Straighten the verticals", model),
    ]


def test_changed_room_retries_the_chain_once(monkeypatch, tmp_path):
    world = shot_world.install(monkeypatch)
    shot = make_shot(1, photo_edit_prompts=["Brighten the room"])
    world.edit_checks[shot.id] = [changed_check("a window changed"), clean_check()]

    frame = first_frame(shot, tmp_path)

    assert frame == crop_of(shot) + b"+Brighten the room"
    assert len(world.named("edit_photo")) == 2
    record = photo_record(world, shot)
    assert record["edit_status"] == "edited"
    assert record["edited_key"] == "jobs/J/shots/1/r0/edited.jpg"
    assert record["cropped_key"] == "jobs/J/shots/1/r0/cropped.jpg"
    assert record["edit_note"] is None
    assert [p["key"] for p in world.named("put")] == [
        "jobs/J/shots/1/r0/cropped.jpg",
        "jobs/J/shots/1/r0/edited.jpg",
    ]


def test_two_changed_rooms_fall_back_to_the_crop(monkeypatch, tmp_path):
    world = shot_world.install(monkeypatch)
    shot = make_shot(1, photo_edit_prompts=["Brighten the room"])
    world.edit_checks[shot.id] = [changed_check("a window changed")] * 5

    frame = first_frame(shot, tmp_path)

    assert frame == crop_of(shot)
    assert len(world.named("edit_photo")) == 2
    record = photo_record(world, shot)
    assert record["edit_status"] == "crop_only"
    assert record["edited_key"] is None
    assert "a window changed" in record["edit_note"]


def test_failing_image_model_moves_to_its_fallback(monkeypatch, tmp_path):
    world = shot_world.install(monkeypatch)
    shot = make_shot(2, photo_edit_prompts=["Brighten the room", "Straighten the verticals"])
    settings = get_settings()
    world.edit_errors[(shot.id, settings.ENHANCE_MODEL)] = "refused"

    frame = first_frame(shot, tmp_path)

    crop = crop_of(shot)
    assert edits(world) == [
        (crop, "Brighten the room", settings.ENHANCE_MODEL),
        (crop, "Brighten the room", settings.ENHANCE_MODEL_FALLBACK),
        (crop + b"+Brighten the room", "Straighten the verticals", settings.ENHANCE_MODEL_FALLBACK),
    ]
    assert frame == crop + b"+Brighten the room+Straighten the verticals"
    assert photo_record(world, shot)["edit_status"] == "edited"


def test_failing_fallback_image_model_uses_the_crop(monkeypatch, tmp_path):
    world = shot_world.install(monkeypatch)
    shot = make_shot(2, photo_edit_prompts=["Brighten the room"])
    settings = get_settings()
    world.edit_errors[(shot.id, settings.ENHANCE_MODEL)] = "refused"
    world.edit_errors[(shot.id, settings.ENHANCE_MODEL_FALLBACK)] = "failed"

    frame = first_frame(shot, tmp_path)

    assert frame == crop_of(shot)
    record = photo_record(world, shot)
    assert record["edit_status"] == "crop_only"
    assert record["edit_note"]


def test_check_error_falls_back_to_the_crop(monkeypatch, tmp_path):
    world = shot_world.install(monkeypatch)
    shot = make_shot(1, photo_edit_prompts=["Brighten the room"])
    world.edit_checks[shot.id] = ["bad_response", clean_check()]

    frame = first_frame(shot, tmp_path)

    assert frame == crop_of(shot)
    assert len(world.named("edit_photo")) == 1
    assert len(world.named("check_edit")) == 1
    record = photo_record(world, shot)
    assert record["edit_status"] == "crop_only"
    assert record["edited_key"] is None
    assert record["edit_note"]


@pytest.mark.parametrize("step", ["edit", "check"])
def test_out_of_credit_stops_the_edit_step(monkeypatch, tmp_path, step):
    world = shot_world.install(monkeypatch)
    shot = make_shot(1, photo_edit_prompts=["Brighten the room"])
    settings = get_settings()
    if step == "edit":
        world.edit_errors[(shot.id, settings.ENHANCE_MODEL)] = "out_of_credit"
    else:
        world.edit_checks[shot.id] = ["out_of_credit"]

    with pytest.raises(ProviderError) as raised:
        first_frame(shot, tmp_path)

    assert raised.value.kind == ProviderErrorKind.out_of_credit
    assert [e["model"] for e in world.named("edit_photo")] == [settings.ENHANCE_MODEL]
    assert world.named("set_shot_photo") == []


def test_edit_check_compares_the_crop_with_the_edit(monkeypatch, tmp_path):
    world = shot_world.install(monkeypatch)
    shot = make_shot(1, photo_edit_prompts=["Brighten the room", "Straighten the verticals"])

    first_frame(shot, tmp_path)

    crop = crop_of(shot)
    (check,) = world.named("check_edit", shot.id)
    assert check["original"] == crop
    assert check["edited"] == crop + b"+Brighten the room+Straighten the verticals"


def test_shot_without_edits_uses_the_crop(monkeypatch, tmp_path):
    world = shot_world.install(monkeypatch)
    shot = make_shot(3)

    frame = first_frame(shot, tmp_path)

    assert frame == crop_of(shot)
    assert world.named("edit_photo") == []
    assert photo_record(world, shot)["edit_status"] == "crop_only"
