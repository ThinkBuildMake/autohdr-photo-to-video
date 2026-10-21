"""editPhoto: one photo and one edit prompt go to the image model, one JPEG comes back."""

import io
from typing import Any

from PIL import Image, UnidentifiedImageError

from app.config import get_settings
from app.providers import chat as chat_client
from app.providers.errors import ProviderError

PRESERVE = "preserve all architectural and interior details"

_NO_FALLBACK = frozenset({"rate_limited", "out_of_credit", "refused", "timeout"})


def _with_preserve(prompt: str) -> str:
    text = prompt.strip()
    if text.lower().rstrip(" .,;:!?\n").endswith(PRESERVE):
        return text
    return f"{text.rstrip(' ,;:')}, {PRESERVE}"


def _to_jpeg(data: bytes, call_id: str) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format == "JPEG":
                return data
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, "JPEG", quality=95)
            return buffer.getvalue()
    except (UnidentifiedImageError, OSError):
        raise chat_client.bad_response(call_id, "The returned image could not be read.") from None


def _edit_with(model: str, text: str, jpeg_bytes: bytes, ids: dict[str, Any]) -> bytes:
    content = [chat_client.text_part(text), chat_client.image_part(jpeg_bytes)]
    answer = chat_client.chat(
        "edit_photo",
        model,
        [{"role": "user", "content": content}],
        ids,
        timeout_s=120,
        modalities=["image", "text"],
    )
    if not answer.images:
        raise chat_client.bad_response(answer.call_id, "The answer had no image.")
    return _to_jpeg(answer.images[0], answer.call_id)


def edit_photo(
    jpeg_bytes: bytes, prompt: str, ids: dict[str, Any], model: str | None = None
) -> bytes:
    settings = get_settings()
    text = _with_preserve(prompt)
    if model is not None:
        return _edit_with(model, text, jpeg_bytes, ids)
    try:
        return _edit_with(settings.ENHANCE_MODEL, text, jpeg_bytes, ids)
    except ProviderError as error:
        fallback = settings.ENHANCE_MODEL_FALLBACK
        if error.kind in _NO_FALLBACK or not fallback or fallback == settings.ENHANCE_MODEL:
            raise
    return _edit_with(fallback, text, jpeg_bytes, ids)
