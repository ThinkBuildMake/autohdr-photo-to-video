"""The scripted world a shot is prepared in: S12's stand-ins replaced on top of clip_world's."""

from pathlib import Path

from app.media import service as media
from app.pipeline import clip_stubs, stubs
from app.shared.types import EditCheck
from tests.pipeline import clip_world
from tests.pipeline.clip_world import _as_error


def clean_check() -> EditCheck:
    return EditCheck(
        added_objects=[],
        removed_objects=[],
        changed_objects=[],
        architecture_changed=False,
        notes="nothing changed",
    )


def changed_check(notes: str = "a window changed") -> EditCheck:
    return clean_check().model_copy(
        update={"changed_objects": ["window"], "architecture_changed": True, "notes": notes}
    )


def install(monkeypatch):
    world = clip_world.install(monkeypatch)
    world.edit_checks = {}  # shot id -> [EditCheck | error kind], in call order
    world.edit_errors = {}  # (shot id, model) -> error kind
    world.on_photo = None  # called with the photo id inside get_photo, from the shot's thread

    def get_photo(photoshoot_id, photo_id):
        world.record("get_photo", photo=photo_id)
        if world.on_photo:
            world.on_photo(photo_id)
        return f"photo:{photo_id}".encode()

    def crop16x9(image_bytes):
        return b"crop(" + image_bytes + b")"

    def edit_photo(jpeg_bytes, prompt, ids, model):
        shot = ids["jobShotId"]
        world.record("edit_photo", shot=shot, jpeg=jpeg_bytes, prompt=prompt, model=model)
        kind = world.edit_errors.get((shot, model))
        if kind:
            raise _as_error(kind)
        return jpeg_bytes + b"+" + prompt.encode()

    def check_edit(original_jpeg, edited_jpeg, ids):
        shot = ids["jobShotId"]
        world.record("check_edit", shot=shot, original=original_jpeg, edited=edited_jpeg)
        step = world._next(world.edit_checks, shot, clean_check())
        if isinstance(step, str):
            raise _as_error(step)
        return step

    def set_shot_photo(job_shot_id, cropped_key, edited_key, edit_status, edit_note):
        world.record(
            "set_shot_photo",
            shot=job_shot_id,
            cropped_key=cropped_key,
            edited_key=edited_key,
            edit_status=edit_status,
            edit_note=edit_note,
        )

    def put(key, path):
        world.record("put", key=key, path=path)
        clip_stubs.BUCKET[key] = Path(path).read_bytes()

    monkeypatch.setattr(clip_stubs, "put", put)
    monkeypatch.setattr(stubs, "get_photo", get_photo)
    monkeypatch.setattr(media, "crop16x9", crop16x9)
    monkeypatch.setattr(stubs, "edit_photo", edit_photo)
    monkeypatch.setattr(stubs, "check_edit", check_edit)
    monkeypatch.setattr(stubs, "set_shot_photo", set_shot_photo)
    monkeypatch.setattr(stubs, "shot_round", lambda job_shot_id: 0)
    return world
