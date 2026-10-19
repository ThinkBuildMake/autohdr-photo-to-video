"""The real providers, through OpenRouter. S06 builds the chat calls, S07 the video call."""

from typing import Any

from app.shared.types import ClipCheck, ClipResult, EditCheck


class OpenRouterProviders:
    def label_photos(self, photos: list[dict], photoshoot_id: str) -> list[dict]:
        from app.providers.labels import label_photos

        return label_photos(photos, photoshoot_id)

    def plan_shots(
        self,
        style_text: str,
        song_duration_s: float,
        photos: list[dict],
        movements: dict[str, str],
        allowed_lengths: list[float],
        ids: dict[str, Any],
    ) -> dict:
        from app.providers.planner import plan_shots

        return plan_shots(style_text, song_duration_s, photos, movements, allowed_lengths, ids)

    def edit_photo(self, jpeg_bytes: bytes, prompt: str, ids: dict[str, Any]) -> bytes:
        from app.providers.editor import edit_photo

        return edit_photo(jpeg_bytes, prompt, ids)

    def check_edit(
        self, original_jpeg: bytes, edited_jpeg: bytes, ids: dict[str, Any]
    ) -> EditCheck:
        from app.providers.checks import check_edit

        return check_edit(original_jpeg, edited_jpeg, ids)

    def generate_clip(
        self,
        first_frame_jpeg: bytes,
        prompt: str,
        model: str,
        length_s: float,
        ids: dict[str, Any],
    ) -> ClipResult:
        raise NotImplementedError("generate_clip is built in S07.")

    def check_clip(
        self,
        clip_path: str,
        frames: list[bytes],
        source_jpeg: bytes,
        ids: dict[str, Any],
    ) -> ClipCheck:
        from app.providers.checks import check_clip

        return check_clip(clip_path, frames, source_jpeg, ids)

    def allowed_lengths(self, model: str) -> list[float]:
        raise NotImplementedError("allowed_lengths is built in S07.")

    def recover_calls(self) -> None:
        return None
