import pytest

from app.db.schema import init_db
from app.providers import fake, fake_video, interface
from app.providers.errors import ProviderError
from tests.support.library_rows import add_song
from tests.support.worker_rows import add_job, add_shoot, add_shot


def test_flags_follow_shot_identity_and_clear():
    init_db()
    fake.reset()
    try:
        shoot, _ = add_shoot()
        job = add_job(shoot, add_song())
        target = add_shot(job, 1)
        fake.flag_shot(target)
        for _ in range(4):
            result = interface.check_clip("", [], b"", {"jobShotId": target})
            assert result.passed is False
            assert result.notes == f"Injected flag for {target}"
        assert interface.check_clip("", [], b"", {}).passed is True
        fake.clear()
        assert interface.check_clip("", [], b"", {"jobShotId": target}).passed is True
    finally:
        fake.reset()


def test_numbered_credit_failure_can_be_cleared_without_resetting_count():
    init_db()
    fake_video.reset()
    fake_video.fail_on(1, "out_of_credit")
    with pytest.raises(ProviderError, match="fake generate_clip error") as exc:
        interface.generate_clip(b"", "", "test", 4, {})
    assert exc.value.kind == "out_of_credit"
    fake_video.clear()
    fake_video.fail_on(2, "refused")
    with pytest.raises(ProviderError) as exc:
        interface.generate_clip(b"", "", "test", 4, {})
    assert exc.value.kind == "refused"
    fake_video.reset()


def test_fake_injection_cannot_change_real_provider_dispatch(monkeypatch, tmp_path):
    import json

    import httpx

    from app.config import reset_settings
    from app.providers import chat
    from tests.providers.chat.conftest import MODELS_JSON, _chat_answer

    init_db()
    fake.reset()
    fake.fail_on("check_clip", 1, "out_of_credit")
    fake_video.fail_on(1, "out_of_credit")
    monkeypatch.setenv("FAKE_PROVIDERS", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-test-key")
    reset_settings()
    chat.reset_pricing()
    requests = []

    def handler(request):
        requests.append(request.url.path)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELS_JSON)
        answer = {
            "aiScore": 0.1,
            "matchScore": 0.99,
            "peopleCount": 0,
            "addedObjects": [],
            "removedObjects": [],
            "changedObjects": [],
            "notes": "Real dispatch via mocked HTTP",
        }
        return httpx.Response(200, json=_chat_answer(json.dumps(answer)))

    monkeypatch.setattr(chat, "TRANSPORT", httpx.MockTransport(handler))
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"synthetic clip")
    try:
        result = interface.check_clip(str(path), [], b"", {})
        assert result.passed
        assert result.notes == "Real dispatch via mocked HTTP"
        assert any(p.endswith("/chat/completions") for p in requests)
    finally:
        fake.reset()
        fake_video.reset()
        chat.reset_pricing()


def test_local_launcher_requires_explicit_fake_mode():
    import os
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/demo_s23.py"],
        env={**os.environ, "FAKE_PROVIDERS": "0"},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "requires FAKE_PROVIDERS=1" in result.stderr
