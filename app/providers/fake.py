"""Test double for the providers, selected by FAKE_PROVIDERS=1. S06 and S07 fill it in."""

import io
import threading
from collections import Counter
from collections.abc import Callable
from typing import Any

from PIL import Image

from app.config import get_settings
from app.providers import calls
from app.providers.errors import ProviderError
from app.shared.enums import ProviderErrorKind, Room
from app.shared.types import ClipCheck, ClipResult, EditCheck, PlannedShot

# Module-level because interface.py makes a new FakeProviders for every call.
_lock = threading.Lock()
_calls: Counter[str] = Counter()
_scripts: dict[tuple[str, int], Any] = {}
_edited_jpeg: bytes | None = None
_ROOMS = [room for room in Room if room != Room.other]


class _Failure:
    def __init__(self, error: ProviderErrorKind | str):
        self.error = error


def fail_on(kind: str, call_no: int, error: ProviderErrorKind | str) -> None:
    """Make the call_no-th call of this kind (counting from 1) raise ProviderError(error)."""
    ProviderErrorKind(error)
    with _lock:
        _scripts[(kind, call_no)] = _Failure(error)


def answer_on(kind: str, call_no: int, result: Any) -> None:
    """Make the call_no-th call of this kind return result instead of the fixed answer."""
    with _lock:
        _scripts[(kind, call_no)] = result


def reset() -> None:
    with _lock:
        _calls.clear()
        _scripts.clear()


def _run(kind: str, model: str, ids: dict[str, Any], make_result: Callable[[], Any]) -> Any:
    with _lock:
        _calls[kind] += 1
        scripted = _scripts.get((kind, _calls[kind]))
    call_id = calls.start_call(kind, model, ids)
    if isinstance(scripted, _Failure):
        error = ProviderError(scripted.error, f"fake {kind} error")
        calls.finish_error(call_id, error)
        raise error
    try:
        result = scripted if scripted is not None else make_result()
    except Exception as exc:
        error = ProviderError("bad_response", f"fake {kind} error ({type(exc).__name__})")
        calls.finish_error(call_id, error)
        raise error from None
    calls.finish_ok(call_id, 0.0, "reported")
    return result


def _fixed_jpeg() -> bytes:
    global _edited_jpeg
    with _lock:
        if _edited_jpeg is None:
            buffer = io.BytesIO()
            Image.new("RGB", (160, 90), (128, 128, 128)).save(buffer, "JPEG")
            _edited_jpeg = buffer.getvalue()
        return _edited_jpeg


class FakeProviders:
    def label_photos(self, photos: list[dict], photoshoot_id: str) -> list[dict]:
        def make() -> list[dict]:
            return [
                {
                    "photoId": photo["photoId"],
                    "room": _ROOMS[index % len(_ROOMS)],
                    "subject": f"fake subject {index + 1}",
                }
                for index, photo in enumerate(photos)
            ]

        return _run(
            "label_photos",
            get_settings().QUALITY_CHECK_MODEL,
            {"photoshootId": photoshoot_id},
            make,
        )

    def plan_shots(
        self,
        style_text: str,
        song_duration_s: float,
        photos: list[dict],
        movements: dict[str, str],
        allowed_lengths: list[float],
        ids: dict[str, Any],
    ) -> dict:
        settings = get_settings()
        movement_name = next(iter(movements), "dolly_in")
        length_s = min((length for length in allowed_lengths if length >= 4), default=4.0)

        def make() -> dict:
            shots = [
                PlannedShot(
                    position=index + 1,
                    room=photo.get("room") or Room.other,
                    photo_id=photo["photoId"],
                    photo_edit_prompts=[],
                    movement_name=movement_name,
                    movement_prompt=movements.get(movement_name, ""),
                    speed="medium",
                    model=settings.VIDEO_MODEL,
                    length_s=length_s,
                    transition="cut",
                    transition_s=0.0,
                    plan_note="fake plan",
                )
                for index, photo in enumerate(photos)
            ]
            return {"shots": shots, "notes": ""}

        return _run("plan_shots", settings.PLANNER_MODEL, ids, make)

    def edit_photo(
        self, jpeg_bytes: bytes, prompt: str, ids: dict[str, Any], model: str | None = None
    ) -> bytes:
        return _run(
            "edit_photo",
            model if model is not None else get_settings().ENHANCE_MODEL,
            ids,
            lambda: _fixed_jpeg(),
        )

    def check_edit(
        self, original_jpeg: bytes, edited_jpeg: bytes, ids: dict[str, Any]
    ) -> EditCheck:
        return _run(
            "check_edit",
            get_settings().QUALITY_CHECK_MODEL,
            ids,
            lambda: EditCheck(
                added_objects=[],
                removed_objects=[],
                changed_objects=[],
                architecture_changed=False,
                notes="fake check passed",
            ),
        )

    def generate_clip(
        self,
        first_frame_jpeg: bytes,
        prompt: str,
        model: str,
        length_s: float,
        ids: dict[str, Any],
    ) -> ClipResult:
        from app.providers import fake_video

        return fake_video.generate_clip(first_frame_jpeg, prompt, model, length_s, ids)

    def check_clip(
        self,
        clip_path: str,
        frames: list[bytes],
        source_jpeg: bytes,
        ids: dict[str, Any],
    ) -> ClipCheck:
        return _run(
            "check_clip",
            get_settings().QUALITY_CHECK_MODEL,
            ids,
            lambda: ClipCheck(
                ai_score=0.1,
                match_score=0.9,
                people_count=0,
                added_objects=[],
                removed_objects=[],
                changed_objects=[],
                passed=True,
                notes="fake check passed",
            ),
        )

    def allowed_lengths(self, model: str) -> list[float]:
        from app.providers import fake_video

        return fake_video.allowed_lengths(model)

    def recover_calls(self) -> None:
        return None
