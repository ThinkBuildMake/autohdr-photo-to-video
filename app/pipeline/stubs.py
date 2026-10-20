"""Stand-ins S12 borrows until S22 removes them (S28's are in clip_stubs).

get_photo stands in for Photoshoots (the photo's file type) plus Files.get; edit_photo and
check_edit for Providers, with edit_photo taking the image model so the Pipeline can rerun the
chain on ENHANCE_MODEL_FALLBACK; set_shot_photo for Jobs; shot_round for the shot's round, which
the JobShot type does not carry.
"""

import io

from PIL import Image

from app.shared.types import EditCheck


def get_photo(photoshoot_id: str, photo_id: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), "gray").save(buffer, "JPEG")
    return buffer.getvalue()


def edit_photo(jpeg_bytes: bytes, prompt: str, ids: dict[str, str], model: str) -> bytes:
    return jpeg_bytes


def check_edit(original_jpeg: bytes, edited_jpeg: bytes, ids: dict[str, str]) -> EditCheck:
    return EditCheck(
        added_objects=[],
        removed_objects=[],
        changed_objects=[],
        architecture_changed=False,
        notes="",
    )


def set_shot_photo(
    job_shot_id: str,
    cropped_key: str | None,
    edited_key: str | None,
    edit_status: str,
    edit_note: str | None,
) -> None:
    return None


def shot_round(job_shot_id: str) -> int:
    return 0
