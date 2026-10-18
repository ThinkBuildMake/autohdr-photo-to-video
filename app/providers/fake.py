"""Test double for the providers, selected by FAKE_PROVIDERS=1. S06 and S07 fill it in."""

from typing import Any

from app.shared.types import ClipCheck, ClipResult, EditCheck


class FakeProviders:
    def label_photos(self, photos: list[dict], photoshoot_id: str) -> list[dict]:
        raise NotImplementedError("FakeProviders.label_photos is built in S06.")

    def plan_shots(
        self,
        style_text: str,
        song_duration_s: float,
        photos: list[dict],
        movements: dict[str, str],
        allowed_lengths: list[float],
        ids: dict[str, Any],
    ) -> dict:
        raise NotImplementedError("FakeProviders.plan_shots is built in S06.")

    def edit_photo(self, jpeg_bytes: bytes, prompt: str, ids: dict[str, Any]) -> bytes:
        raise NotImplementedError("FakeProviders.edit_photo is built in S06.")

    def check_edit(
        self, original_jpeg: bytes, edited_jpeg: bytes, ids: dict[str, Any]
    ) -> EditCheck:
        raise NotImplementedError("FakeProviders.check_edit is built in S06.")

    def generate_clip(
        self,
        first_frame_jpeg: bytes,
        prompt: str,
        model: str,
        length_s: float,
        ids: dict[str, Any],
    ) -> ClipResult:
        raise NotImplementedError("FakeProviders.generate_clip is built in S07.")

    def check_clip(
        self,
        clip_path: str,
        frames: list[bytes],
        source_jpeg: bytes,
        ids: dict[str, Any],
    ) -> ClipCheck:
        raise NotImplementedError("FakeProviders.check_clip is built in S06.")

    def allowed_lengths(self, model: str) -> list[float]:
        raise NotImplementedError("FakeProviders.allowed_lengths is built in S07.")

    def recover_calls(self) -> None:
        return None
