import pytest

from app.providers import calls
from app.providers.errors import ProviderError


def test_shared_calls_preserve_clip_cost_and_recovery_metadata(videos_api):
    call_id = calls.start_call("generate_clip", "synthetic", {})
    calls.set_request_id(call_id, "request-1")
    calls.record_cost(call_id, 0.8, "reported", 4.0)
    assert (call_id, "synthetic", "request-1") in calls.open_clip_calls()
    calls.finish_ok(call_id, 0.0, "list_price", "request-1", 4.0)
    assert calls.recorded(call_id)[:3] == (0.8, "reported", 4.0)
    assert calls.open_clip_calls() == []
    calls.finish_error(call_id, ProviderError("failed", "collection failed"))
    assert calls.recorded(call_id)[:3] == (0.8, "reported", 4.0)


@pytest.mark.parametrize("kind", ["generate_clip", "check_clip"])
def test_provider_call_errors_scrub_signed_urls_and_secrets(videos_api, kind):
    from app.db.base import session_scope
    from app.providers.models import ProviderCall

    call_id = calls.start_call(kind, "synthetic", {})
    calls.finish_error(
        call_id,
        ProviderError(
            "failed",
            "Failed https://bucket.test/clip?X-Amz-Signature=private-signature "
            "Bearer private-token sk-or-private-key data:image/jpeg;base64,c2VjcmV0",
        ),
    )
    with session_scope() as session:
        row = session.get(ProviderCall, call_id)
        assert row.status == "error"
        assert row.error_message == (
            "Failed [presigned url] Bearer [redacted] [api key] [base64 data]"
        )
