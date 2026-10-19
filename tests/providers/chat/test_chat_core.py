import json
import logging
import time

import httpx
import pytest

from app.config import reset_settings
from app.db.base import session_scope
from app.providers import labels
from app.providers.errors import ProviderError
from app.providers.models import ProviderCall

KEY = "sk-or-v1-TESTKEY-not-real"


@pytest.fixture
def photos(synthetic_jpeg):
    return [{"photoId": "p1", "jpegBytes": synthetic_jpeg("tan", "kitchen")}]


GOOD = json.dumps({"labels": [{"photoId": "p1", "room": "kitchen", "subject": "island"}]})


def run(photos):
    return labels.label_photos(photos, "ps-1")


@pytest.mark.parametrize(
    ("kwargs", "kind", "retry_after"),
    [
        (
            {
                "status": 429,
                "json": {"error": {"message": "slow"}},
                "headers": {"Retry-After": "7"},
            },
            "rate_limited",
            7.0,
        ),
        ({"status": 402, "json": {"error": {"message": "credits"}}}, "out_of_credit", None),
        (
            {
                "status": 403,
                "json": {"error": {"code": 403, "metadata": {"reasons": ["violence"]}}},
            },
            "refused",
            None,
        ),
        ("filter", "refused", None),
        ({"status": 500, "json": {"error": {"message": "boom"}}}, "failed", None),
        ({"raise_timeout": True}, "timeout", None),
    ],
)
def test_errors_map_to_kinds(openrouter, chat_answer, photos, kwargs, kind, retry_after):
    if kwargs == "filter":
        openrouter.answer(json=chat_answer("", finish_reason="content_filter"))
    else:
        openrouter.answer(**kwargs)

    with pytest.raises(ProviderError) as caught:
        run(photos)

    assert caught.value.kind == kind
    assert caught.value.retry_after_s == retry_after


def test_200_body_with_error_object_is_failed(openrouter, photos):
    openrouter.answer(json={"error": {"code": 502, "message": "upstream"}})
    with pytest.raises(ProviderError) as caught:
        run(photos)
    assert caught.value.kind == "failed"
    assert caught.value.message.startswith("HTTP 502: upstream")


def test_prose_is_bad_response(openrouter, chat_answer, photos):
    openrouter.answer(json=chat_answer("Here are your labels: kitchen."))
    with pytest.raises(ProviderError) as caught:
        run(photos)
    assert caught.value.kind == "bad_response"


def test_every_call_leaves_one_row(openrouter, chat_answer, photos, rows):
    openrouter.answer(json=chat_answer(GOOD, usage={"cost": 0.0021}))
    openrouter.answer(status=500, json={"error": {"message": "boom"}})
    run(photos)
    with pytest.raises(ProviderError):
        run(photos)

    all_rows = rows()
    assert len(all_rows) == 2
    by_status = {row.status: row for row in all_rows}
    ok, bad = by_status["ok"], by_status["error"]
    for row in all_rows:
        assert (row.kind, row.model) == ("label_photos", "google/gemini-3.8-flash")
        assert row.cost_source == "reported" and row.finished_at
    assert ok.cost_usd == pytest.approx(0.0021)
    assert bad.cost_usd == 0 and bad.error_kind == "failed"


def test_timeout_and_bad_response_still_leave_a_closed_row(openrouter, chat_answer, photos, rows):
    openrouter.answer(raise_timeout=True)
    openrouter.answer(json=chat_answer("prose"))
    for _ in range(2):
        with pytest.raises(ProviderError):
            run(photos)

    all_rows = rows()
    assert {row.error_kind for row in all_rows} == {"timeout", "bad_response"}
    assert all(row.status == "error" and row.finished_at for row in all_rows)


def test_byok_records_list_price(openrouter, chat_answer, photos, rows, monkeypatch):
    monkeypatch.setenv("BYOK_MODELS", "google/veo-3.1, google/gemini-3.8-flash")
    reset_settings()
    usage = {"cost": 0, "prompt_tokens": 1000, "completion_tokens": 200}
    openrouter.answer(json=chat_answer(GOOD, usage=usage))
    run(photos)

    (row,) = rows()
    assert row.cost_source == "list_price"
    assert row.cost_usd == pytest.approx(1000 * 0.000000825 + 200 * 0.000004125)
    assert row.cost_usd > 0


def test_usage_is_byok_flag_gives_list_price(openrouter, chat_answer, photos, rows, monkeypatch):
    monkeypatch.setenv("QUALITY_CHECK_MODEL", "test/byok-chat")
    reset_settings()
    usage = {"cost": 0, "is_byok": True, "prompt_tokens": 1000, "completion_tokens": 100}
    openrouter.answer(json=chat_answer(GOOD, usage=usage))
    run(photos)

    (row,) = rows()
    assert row.cost_source == "list_price"
    assert row.cost_usd == pytest.approx(1000 * 0.000001 + 100 * 0.000002)


def test_billed_refusal_keeps_reported_cost(openrouter, chat_answer, photos, rows):
    openrouter.answer(json=chat_answer("", finish_reason="content_filter", usage={"cost": 0.05}))
    with pytest.raises(ProviderError) as caught:
        run(photos)

    (row,) = rows()
    assert caught.value.kind == "refused"
    assert (row.status, row.error_kind) == ("error", "refused")
    assert row.cost_usd == pytest.approx(0.05) and row.cost_source == "reported"


def test_billed_refusal_under_byok_records_list_price(
    openrouter, chat_answer, photos, rows, monkeypatch
):
    monkeypatch.setenv("BYOK_MODELS", "google/gemini-3.8-flash")
    reset_settings()
    usage = {"cost": 0, "prompt_tokens": 1000, "completion_tokens": 0}
    openrouter.answer(json=chat_answer("", finish_reason="content_filter", usage=usage))
    with pytest.raises(ProviderError):
        run(photos)

    (row,) = rows()
    assert row.status == "error" and row.cost_source == "list_price"
    assert row.cost_usd > 0


def test_key_never_leaks(openrouter, photos, rows, caplog):
    def echo(request: httpx.Request) -> httpx.Response:
        openrouter.requests.append(request)
        message = f"bad auth {request.headers['Authorization']}"
        return httpx.Response(500, json={"error": {"message": message}})

    import app.providers.chat as chat_module

    chat_module.TRANSPORT = httpx.MockTransport(echo)  # restored by the fixture's monkeypatch
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ProviderError) as caught:
        run(photos)

    assert KEY not in str(caught.value) and KEY not in caught.value.message
    (row,) = rows()
    assert KEY not in (row.error_message or "")
    assert KEY not in caplog.text
    assert openrouter.requests[0].headers["Authorization"] == f"Bearer {KEY}"
    assert "***" in row.error_message


def test_nothing_blocked_on_cost(openrouter, chat_answer, photos):
    with session_scope() as session:
        for index in range(5):
            session.add(
                ProviderCall(
                    id=f"old-{index}",
                    kind="generate_clip",
                    model="google/veo-3.1",
                    status="ok",
                    cost_usd=100,
                    started_at="2026-10-18T00:00:00.000Z",
                )
            )
    openrouter.answer(json=chat_answer(GOOD))

    result = run(photos)

    assert len(openrouter.requests) == 1
    assert result[0]["photoId"] == "p1"


@pytest.mark.parametrize("status", [429, 402])
def test_no_retry_and_prompt_report(openrouter, photos, rows, status):
    openrouter.answer(status=status, json={"error": {"message": "no"}})
    started = time.monotonic()
    with pytest.raises(ProviderError):
        run(photos)

    assert time.monotonic() - started < 1
    assert len(openrouter.requests) == 1
    (row,) = rows()
    assert row.finished_at and row.status == "error"


def test_every_chat_request_has_a_finite_timeout(openrouter, chat_answer, photos):
    openrouter.answer(json=chat_answer(GOOD))
    run(photos)
    timeout = openrouter.requests[0].extensions["timeout"]
    assert all(value is not None and value > 0 for value in timeout.values())


def test_off_format_answer_closes_row_as_bad_response(openrouter, chat_answer, photos, rows):
    body = chat_answer()
    body["choices"][0]["message"]["images"] = ["x"]
    openrouter.answer(json=body)

    with pytest.raises(ProviderError) as caught:
        run(photos)

    assert caught.value.kind == "bad_response"
    only = rows()
    assert [(r.status, r.error_kind) for r in only] == [("error", "bad_response")]
    assert only[0].finished_at is not None
