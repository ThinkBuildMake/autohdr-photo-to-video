import base64
import io

import pytest
from PIL import Image

from app.providers import editor
from app.providers.errors import ProviderError

PRESERVE = "preserve all architectural and interior details"
ENHANCE = "google/gemini-nano-banana-2.1"
FALLBACK = "google/gemini-3.1-flash-image"


def image_answer(fmt="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), "orange").save(buffer, fmt)
    url = f"data:image/{fmt.lower()};base64,{base64.b64encode(buffer.getvalue()).decode()}"
    return {
        "id": "gen-img",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": "", "images": [{"image_url": {"url": url}}]},
            }
        ],
        "usage": {"cost": 0.04},
    }


def text_only(chat_answer):
    return chat_answer("I cannot do that.")


def test_photo_is_edited(openrouter, synthetic_jpeg, rows):
    openrouter.answer(json=image_answer("PNG"))

    result = editor.edit_photo(
        synthetic_jpeg("tan", "kitchen"), f"warm late-afternoon light, {PRESERVE}", {"jobId": None}
    )

    with Image.open(io.BytesIO(result)) as image:
        assert image.format == "JPEG"
    body = openrouter.body()
    assert body["modalities"] == ["image", "text"]
    assert body["model"] == ENHANCE
    parts = body["messages"][0]["content"]
    assert [p["type"] for p in parts] == ["text", "image_url"]
    (row,) = rows()
    assert (row.kind, row.model, row.status) == ("edit_photo", ENHANCE, "ok")


def test_jpeg_answer_is_returned_as_is(openrouter, synthetic_jpeg):
    openrouter.answer(json=image_answer("JPEG"))
    result = editor.edit_photo(synthetic_jpeg(), PRESERVE, {})
    with Image.open(io.BytesIO(result)) as image:
        assert image.format == "JPEG"


def test_preserve_sentence_is_always_sent(openrouter, synthetic_jpeg):
    openrouter.answer(json=image_answer())
    openrouter.answer(json=image_answer())
    openrouter.answer(json=image_answer())

    editor.edit_photo(synthetic_jpeg(), "make it a close-up of the island", {})
    editor.edit_photo(synthetic_jpeg(), f"make it brighter, {PRESERVE}", {})
    editor.edit_photo(synthetic_jpeg(), f"make it brighter, {PRESERVE.upper()}.", {})

    texts = [openrouter.body(i)["messages"][0]["content"][0]["text"] for i in range(3)]
    assert texts[0] == f"make it a close-up of the island, {PRESERVE}"
    assert texts[1] == f"make it brighter, {PRESERVE}"
    assert texts[2].lower().count(PRESERVE) == 1


def test_no_image_is_bad_response_and_fallback(openrouter, chat_answer, synthetic_jpeg, rows):
    openrouter.answer(json=text_only(chat_answer))
    openrouter.answer(json=text_only(chat_answer))

    with pytest.raises(ProviderError) as caught:
        editor.edit_photo(synthetic_jpeg(), "brighter", {})

    assert caught.value.kind == "bad_response"
    assert [openrouter.body(i)["model"] for i in range(2)] == [ENHANCE, FALLBACK]
    first, second = rows()
    assert (first.model, first.status, first.error_kind) == (ENHANCE, "error", "bad_response")
    assert (second.model, second.status) == (FALLBACK, "error")


def test_fallback_answer_is_used(openrouter, chat_answer, synthetic_jpeg, rows):
    openrouter.answer(status=500, json={"error": {"code": 500, "message": "boom"}})
    openrouter.answer(json=image_answer())

    result = editor.edit_photo(synthetic_jpeg(), "brighter", {})

    assert result
    assert [r.status for r in rows()] == ["error", "ok"]


@pytest.mark.parametrize(
    ("status", "body", "headers", "kind"),
    [
        (402, {"error": {"code": 402, "message": "no credit"}}, None, "out_of_credit"),
        (429, {"error": {"code": 429, "message": "slow"}}, {"Retry-After": "3"}, "rate_limited"),
        (403, {"error": {"code": 403, "metadata": {"reasons": ["x"]}}}, None, "refused"),
    ],
)
def test_no_fallback_after_these_errors(
    openrouter, synthetic_jpeg, rows, status, body, headers, kind
):
    openrouter.answer(status=status, json=body, headers=headers)

    with pytest.raises(ProviderError) as caught:
        editor.edit_photo(synthetic_jpeg(), "brighter", {})

    assert caught.value.kind == kind
    assert len(openrouter.requests) == 1
    assert len(rows()) == 1


def test_no_fallback_after_timeout(openrouter, synthetic_jpeg):
    openrouter.answer(raise_timeout=True)
    with pytest.raises(ProviderError) as caught:
        editor.edit_photo(synthetic_jpeg(), "brighter", {})
    assert caught.value.kind == "timeout"
    assert len(openrouter.requests) == 1


def test_content_filter_is_refused_without_fallback(openrouter, chat_answer, synthetic_jpeg):
    openrouter.answer(json=chat_answer("", finish_reason="content_filter"))
    with pytest.raises(ProviderError) as caught:
        editor.edit_photo(synthetic_jpeg(), "brighter", {})
    assert caught.value.kind == "refused"
    assert len(openrouter.requests) == 1


def test_same_fallback_model_is_not_called_twice(
    openrouter, chat_answer, synthetic_jpeg, monkeypatch
):
    from app.config import reset_settings

    monkeypatch.setenv("ENHANCE_MODEL_FALLBACK", ENHANCE)
    reset_settings()
    openrouter.answer(json=text_only(chat_answer))
    with pytest.raises(ProviderError):
        editor.edit_photo(synthetic_jpeg(), "brighter", {})
    assert len(openrouter.requests) == 1


@pytest.mark.live
def test_live_edit_photo(live, synthetic_jpeg):
    result = editor.edit_photo(
        synthetic_jpeg("tan", "kitchen island and stools"),
        "warm late-afternoon light",
        {"photoshootId": "ps-1"},
    )
    with Image.open(io.BytesIO(result)) as image:
        assert image.format == "JPEG"


@pytest.mark.parametrize("model", [ENHANCE, FALLBACK])
def test_explicit_model_dispatch_and_audit(openrouter, synthetic_jpeg, rows, model):
    from app.providers import interface

    openrouter.answer(json=image_answer())
    result = interface.edit_photo(synthetic_jpeg(), "brighter", {"photoshootId": "ps-1"}, model)

    assert Image.open(io.BytesIO(result)).format == "JPEG"
    assert [openrouter.body(i)["model"] for i in range(len(openrouter.requests))] == [model]
    (row,) = rows()
    assert (row.model, row.status, row.photoshoot_id, row.cost_usd) == (model, "ok", "ps-1", 0.04)


def test_explicit_model_does_not_fallback(openrouter, synthetic_jpeg, rows):
    from app.providers import interface

    openrouter.answer(status=500, json={"error": {"code": 500, "message": "boom"}})
    with pytest.raises(ProviderError) as caught:
        interface.edit_photo(synthetic_jpeg(), "brighter", {}, ENHANCE)

    assert caught.value.kind == "failed"
    assert len(openrouter.requests) == 1
    (row,) = rows()
    assert (row.model, row.status) == (ENHANCE, "error")


def test_fake_explicit_model_is_audited(openrouter, synthetic_jpeg, rows, monkeypatch):
    from app.config import reset_settings
    from app.providers import interface

    monkeypatch.setenv("FAKE_PROVIDERS", "1")
    reset_settings()
    result = interface.edit_photo(synthetic_jpeg(), "brighter", {}, FALLBACK)
    assert Image.open(io.BytesIO(result)).format == "JPEG"
    (row,) = rows()
    assert (row.model, row.status, row.cost_usd) == (FALLBACK, "ok", 0.0)
    assert openrouter.requests == []


def test_interface_default_preserves_fallback(openrouter, synthetic_jpeg, rows):
    from app.providers import interface

    openrouter.answer(status=500, json={"error": {"code": 500, "message": "boom"}})
    openrouter.answer(json=image_answer())
    result = interface.edit_photo(synthetic_jpeg(), "brighter", {})

    assert Image.open(io.BytesIO(result)).format == "JPEG"
    assert [openrouter.body(i)["model"] for i in range(2)] == [ENHANCE, FALLBACK]
    assert [(row.model, row.status) for row in rows()] == [(ENHANCE, "error"), (FALLBACK, "ok")]
