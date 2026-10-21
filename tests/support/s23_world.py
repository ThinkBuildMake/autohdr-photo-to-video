"""Submitted job across real modules; only OpenRouter HTTP and S3 are simulated."""

import base64
import json
import subprocess
import threading
import time
import uuid
import wave
from collections import Counter

import httpx
import pytest

from app.config import reset_settings
from app.db.base import session_scope
from app.files import service as files
from app.jobs import drafts, planning, queue
from app.jobs.plan_rules import MOVEMENTS
from app.jobs.schemas import JobCreate
from app.library.models import Style
from app.providers import chat, video_api
from tests.photoshoots.conftest import seed_shoot
from tests.providers.chat.conftest import BASE, MODELS_JSON, TEST_KEY, _chat_answer
from tests.providers.video.conftest import MODEL_LIST, completed
from tests.support.library_rows import add_song


class ScenarioRouter:
    """Route concurrent requests by clip identity, never by thread arrival order."""

    def __init__(self, photos, clips):
        self.photos = photos
        self.clips = clips
        self.submissions = {}
        self.checks = Counter()
        self.generations = Counter()
        self.lock = threading.Lock()
        self.errors = {}
        self.flagged = set()
        self.retry_entered = threading.Event()
        self.release_retry = threading.Event()
        self.pause_retry = False
        self.error_seen = threading.Event()
        self.error_at = {}
        self.hold_color = None
        self.held = threading.Event()
        self.release = threading.Event()

    def handler(self, request):
        path = request.url.path.removeprefix("/api/v1")
        if path == "/videos/models":
            return httpx.Response(200, json=MODEL_LIST)
        if path == "/models":
            return httpx.Response(200, json=MODELS_JSON)
        if path == "/videos" and request.method == "POST":
            body = json.loads(request.content)
            color = next(
                c for c in ("red", "blue", "green", "yellow") if f"wire-{c}" in body["prompt"]
            )
            assert body["duration"] == 4
            with self.lock:
                self.generations[color] += 1
                number = self.generations[color]
                error = self.errors.get(color)
            if color == self.hold_color:
                self.held.set()
                assert self.release.wait(30), "test did not release held generation"
            if error is not None and (error != 429 or number == 1):
                self.error_at[color] = time.monotonic()
                self.error_seen.set()
                return httpx.Response(
                    error,
                    json={"error": {"message": "Injected scenario", "code": error}},
                    headers={"Retry-After": "0"},
                )
            if color in self.errors and number == 2 and self.pause_retry:
                self.retry_entered.set()
                assert self.release_retry.wait(30), "test did not release retry"
            with self.lock:
                key = str(uuid.uuid4())
                self.submissions[key] = color
            return httpx.Response(200, json={"id": key})
        if path.startswith("/videos/"):
            key = path.split("/")[2]
            color = self.submissions[key]
            if path.endswith("/content"):
                return httpx.Response(200, content=self.clips[color])
            return httpx.Response(200, json=completed(job_id=key))
        assert path == "/chat/completions", path
        parts = json.loads(request.content)["messages"][0]["content"]
        videos = [p for p in parts if p["type"] == "video_url"]
        if not videos:
            shots = []
            for photo, color in zip(self.photos, ("red", "blue", "green", "yellow"), strict=True):
                shot = {
                    "room": "living",
                    "photoId": photo,
                    "photoEditPrompts": [],
                    "movementName": "dolly_in",
                    "movementPrompt": MOVEMENTS["dolly_in"],
                    "speed": "slow",
                    "model": MODEL_LIST["data"][0]["id"],
                    "lengthS": 4,
                    "transition": "cut",
                    "transitionS": 0,
                    "planNote": "Synthetic integration plan",
                }
                shot["movementPrompt"] += f" wire-{color}"
                shots.append(shot)
            answer = {"shots": shots, "notes": ""}
        else:
            clip = base64.b64decode(videos[0]["video_url"]["url"].split(",", 1)[1])
            color = next(c for c, data in self.clips.items() if data == clip)
            with self.lock:
                self.checks[color] += 1
                flagged = color in self.flagged
            answer = {
                "aiScore": 0.9 if flagged else 0.1,
                "matchScore": 0.4 if flagged else 0.99,
                "peopleCount": 0,
                "addedObjects": [],
                "removedObjects": [],
                "changedObjects": [],
                "notes": "Synthetic flagged clip" if flagged else "Passed",
            }
        return httpx.Response(200, json=_chat_answer(json.dumps(answer)))


@pytest.fixture
def s23_world(bucket, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_PROVIDERS", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", TEST_KEY)
    monkeypatch.setenv("OPENROUTER_BASE_URL", BASE)
    reset_settings()
    chat.reset_pricing()
    video_api.reset_cache()
    shoot, photos = seed_shoot(["uploaded"] * 4, shoot_status="ready")
    clips = {}
    for color in ("red", "blue", "green", "yellow", "magenta"):
        path = tmp_path / f"{color}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=320x180:r=24:d=4",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-y",
                str(path),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        clips[color] = path.read_bytes()
    song = add_song()
    song_path = tmp_path / "tone.wav"
    with wave.open(str(song_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0\xff\x0f" * 8000 * 8)
    # The file key is owned by Library; ffmpeg identifies this synthetic WAV by its header.
    files.put(f"songs/{song}.mp3", str(song_path))
    style_id = str(uuid.uuid4())
    with session_scope() as session:
        session.add(
            Style(
                id=style_id,
                name="Wire style",
                author_name="Test",
                style_text="Slow rooms",
                song_id=song,
                fps=24,
            )
        )
    api = ScenarioRouter(photos, clips)
    transport = httpx.MockTransport(api.handler)
    monkeypatch.setattr(chat, "TRANSPORT", transport)
    monkeypatch.setattr(video_api, "TRANSPORT", transport)
    try:
        job = drafts.create_job(
            JobCreate(photoshoot_id=shoot, style_text="Slow rooms", song_id=song, style_id=style_id)
        )
        planning.wait_idle()
        assert queue.get_job(job.id).plan_status == "ready"
        yield job.id, api
    finally:
        planning.wait_idle()
        chat.reset_pricing()
        video_api.reset_cache()
