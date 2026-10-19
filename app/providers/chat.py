"""OpenRouter chat client: one attempt per call, errors mapped to kinds, cost recorded."""

import base64
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import get_settings
from app.providers import calls
from app.providers.errors import ProviderError

log = logging.getLogger(__name__)

TRANSPORT: httpx.BaseTransport | None = None

REFUSAL_REASONS = frozenset(
    {
        "SAFETY",
        "PROHIBITED_CONTENT",
        "IMAGE_SAFETY",
        "IMAGE_PROHIBITED_CONTENT",
        "BLOCKLIST",
        "SPII",
        "RECITATION",
        "CONTENT_FILTER",
        "REFUSAL",
    }
)

_pricing: dict[str, dict[str, float]] | None = None
_pricing_lock = threading.Lock()


@dataclass
class ChatAnswer:
    content: str
    images: list[bytes] = field(default_factory=list)
    request_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""


def scrub(text: str) -> str:
    key = get_settings().OPENROUTER_API_KEY
    return text.replace(key, "***") if key else text


def image_part(jpeg_bytes: bytes) -> dict[str, Any]:
    encoded = base64.b64encode(jpeg_bytes).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}


def text_part(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def parse_json(content: str, call_id: str | None = None) -> Any:
    """Parse a JSON answer, tolerating code fences. Anything else is bad_response."""
    text = content.strip()
    fenced = re.match(r"^```[a-zA-Z]*\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except ValueError:
        raise bad_response(call_id, "The answer was not JSON.") from None


def bad_response(call_id: str | None, message: str) -> ProviderError:
    """Build a bad_response error, closing the call's row as an error first."""
    error = ProviderError("bad_response", message)
    if call_id:
        calls.finish_error(call_id, error)
        _log_call(call_id, error)
    return error


def _log_call(call_id: str, error: ProviderError | None) -> None:
    from app.db.base import session_scope
    from app.providers.models import ProviderCall

    with session_scope() as session:
        row = session.get(ProviderCall, call_id)
        kind, model = (row.kind, row.model) if row else ("?", "?")
    log.info(
        "provider call kind=%s model=%s status=%s error=%s",
        kind,
        model,
        "error" if error else "ok",
        error.kind if error else "-",
    )


def _error_for(
    status: int, message: str, retry_after: float | None, reasons: bool
) -> ProviderError:
    text = scrub(f"HTTP {status}: {message}")[:500]
    if status == 429:
        return ProviderError("rate_limited", text, retry_after)
    if status == 402:
        return ProviderError("out_of_credit", text)
    if status == 403 or reasons:
        return ProviderError("refused", text)
    if status == 408:
        return ProviderError("timeout", text)
    return ProviderError("failed", text)


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return float(response.headers.get("Retry-After", ""))
    except ValueError:
        return None


def _error_object(body: Any) -> dict[str, Any] | None:
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        return body["error"]
    return None


def _has_reasons(error: dict[str, Any] | None) -> bool:
    metadata = (error or {}).get("metadata")
    return isinstance(metadata, dict) and bool(metadata.get("reasons"))


def _http_error(response: httpx.Response) -> ProviderError:
    try:
        body = response.json()
    except ValueError:
        body = None
    error = _error_object(body)
    message = str(error.get("message", "")) if error else ""
    return _error_for(response.status_code, message, _retry_after(response), _has_reasons(error))


def _body_error(error: dict[str, Any]) -> ProviderError:
    try:
        status = int(error.get("code", 500))
    except (TypeError, ValueError):
        status = 500
    return _error_for(status, str(error.get("message", "")), None, _has_reasons(error))


def _decode_image(url: str) -> bytes | None:
    if not url.startswith("data:") or "," not in url:
        return None
    try:
        return base64.b64decode(url.split(",", 1)[1])
    except ValueError:
        return None


def _content_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict) and part.get("text")
        )
    return ""


class _Refusal(ProviderError):
    """A 200 answer that was refused; it carries the usage so the money spent is still recorded."""

    def __init__(self, message: str, usage: dict[str, Any]):
        super().__init__("refused", message)
        self.usage = usage


def _parse_answer(body: Any) -> tuple[str, list[bytes], str | None, dict[str, Any]]:
    error = _error_object(body)
    if error:
        raise _body_error(error)
    choices = body.get("choices") if isinstance(body, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProviderError("bad_response", "The answer had no choices.")
    choice = choices[0]
    finish = str(choice.get("finish_reason") or "").lower()
    native = str(choice.get("native_finish_reason") or "").upper()
    if finish == "content_filter" or native in REFUSAL_REASONS:
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        raise _Refusal(scrub(f"The model refused ({finish or native})."), usage)
    message = choice.get("message")
    message = message if isinstance(message, dict) else {}
    images: list[bytes] = []
    for item in message.get("images") or []:
        url = ((item or {}).get("image_url") or {}).get("url", "")
        data = _decode_image(url) if isinstance(url, str) else None
        if data:
            images.append(data)
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    request_id = body.get("id") if isinstance(body.get("id"), str) else None
    return _content_text(message), images, request_id, usage


def reset_pricing() -> None:
    global _pricing
    with _pricing_lock:
        _pricing = None


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _load_pricing(client: httpx.Client) -> dict[str, dict[str, float]]:
    global _pricing
    with _pricing_lock:
        if _pricing is not None:
            return _pricing
        parsed: dict[str, dict[str, float]] = {}
        try:
            response = client.get(f"{get_settings().OPENROUTER_BASE_URL}/models")
            response.raise_for_status()
            for item in response.json().get("data", []):
                prices = item.get("pricing") or {}
                parsed[item["id"]] = {
                    name: _number(prices.get(name))
                    for name in ("prompt", "completion", "image_output")
                }
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            log.warning("model prices could not be read (%s)", type(exc).__name__)
            return {}
        _pricing = parsed
        return parsed


def _cost(model: str, usage: dict[str, Any], images: list[bytes], client: httpx.Client):
    byok_models = [m.strip() for m in get_settings().BYOK_MODELS.split(",") if m.strip()]
    if not (usage.get("is_byok") is True or model in byok_models):
        return _number(usage.get("cost")), "reported"
    price = _load_pricing(client).get(model)
    if price is None:
        log.warning("no list price for model %s", model)
        return 0.0, "list_price"
    out_price = price["image_output"] if images and price["image_output"] else price["completion"]
    cost = _number(usage.get("prompt_tokens")) * price["prompt"]
    cost += _number(usage.get("completion_tokens")) * out_price
    return cost, "list_price"


def chat(
    kind: str,
    model: str,
    messages: list[dict[str, Any]],
    ids: dict[str, Any],
    *,
    timeout_s: float,
    json_mode: bool = False,
    modalities: list[str] | None = None,
) -> ChatAnswer:
    settings = get_settings()
    call_id = calls.start_call(kind, model, ids)
    payload: dict[str, Any] = {"model": model, "messages": messages}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if modalities:
        payload["modalities"] = modalities
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(transport=TRANSPORT, timeout=timeout_s) as client:
            try:
                response = client.post(
                    f"{settings.OPENROUTER_BASE_URL}/chat/completions",
                    content=json.dumps(payload),
                    headers=headers,
                )
            except httpx.TimeoutException:
                raise ProviderError("timeout", "The request timed out.") from None
            except httpx.HTTPError as exc:
                raise ProviderError(
                    "failed", scrub(f"Transport error: {type(exc).__name__}")
                ) from None
            if response.status_code >= 400:
                raise _http_error(response)
            try:
                body = response.json()
            except ValueError:
                raise ProviderError("bad_response", "The answer was not JSON.") from None
            try:
                content, images, request_id, usage = _parse_answer(body)
            except _Refusal as refusal:
                # The answer was billed even though it was refused: keep what it cost.
                try:
                    refusal_cost = _cost(model, refusal.usage, [], client)
                except Exception:
                    refusal_cost = None
                calls.finish_error(call_id, refusal, refusal_cost)
                _log_call(call_id, refusal)
                raise
            cost, source = _cost(model, usage, images, client)
    except _Refusal:
        raise
    except ProviderError as error:
        calls.finish_error(call_id, error)
        _log_call(call_id, error)
        raise
    except Exception as exc:
        # An answer in an unexpected shape must still close its row.
        error = ProviderError(
            "bad_response", f"The answer could not be read ({type(exc).__name__})."
        )
        calls.finish_error(call_id, error)
        _log_call(call_id, error)
        raise error from None
    calls.finish_ok(call_id, cost, source, provider_request_id=request_id)
    _log_call(call_id, None)
    return ChatAnswer(content, images, request_id, usage, call_id)
