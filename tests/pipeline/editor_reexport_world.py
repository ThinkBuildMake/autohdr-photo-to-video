"""Six-shot real-module world; only OpenRouter HTTP and the S3 service are simulated."""

import base64
import hashlib
import io
import json
import subprocess
import threading
import uuid
import wave
from collections import Counter
from datetime import UTC, datetime

import httpx
import pytest
import requests
from fastapi.testclient import TestClient
from PIL import Image

from app.config import reset_settings
from app.files import service as files
from app.jobs import drafts, planning, queue
from app.jobs.plan_rules import MOVEMENTS
from app.jobs.schemas import JobCreate
from app.main import create_app
from app.media import service as media
from app.pipeline import runner
from app.providers import chat, video_api
from tests.photoshoots.conftest import put_bytes, seed_shoot
from tests.providers.chat.conftest import BASE, MODELS_JSON, TEST_KEY, _chat_answer
from tests.providers.video.conftest import MODEL_LIST, completed
from tests.support.fixtures import DEMO_AUTH, DEMO_PASSPHRASE
from tests.support.library_rows import add_song
from tests.support.worker_rows import rows

COLORS = ["red", "blue", "lime", "yellow", "magenta", "cyan", "orange"]
RGB = [
    (255, 0, 0),
    (0, 0, 255),
    (0, 255, 0),
    (255, 255, 0),
    (255, 0, 255),
    (0, 255, 255),
    (255, 165, 0),
]


def decode(path):
    """Every frame's mean RGB, independently of the production cut detector."""
    data = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            "scale=1:1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        check=True,
        capture_output=True,
        timeout=60,
    ).stdout
    return [tuple(data[i : i + 3]) for i in range(0, len(data), 3)]


class OpenRouter:
    def __init__(self, photos, clips):
        self.photos, self.clips = photos, clips
        self.counts = Counter()
        self.generated = []
        self.checked = []
        self.prompts = []
        self.submissions = {}
        self.lock = threading.Lock()
        self.barrier = None
        self.on_generate = None
        self.plans = 0

    def handler(self, request):
        path = request.url.path.removeprefix("/api/v1")
        if path == "/videos/models":
            return httpx.Response(200, json=MODEL_LIST)
        if path == "/models":
            return httpx.Response(200, json=MODELS_JSON)
        if path == "/videos" and request.method == "POST":
            body = json.loads(request.content)
            url = body["frame_images"][0]["image_url"]["url"]
            pixel = Image.open(io.BytesIO(base64.b64decode(url.split(",")[1]))).getpixel((0, 0))
            identity = min(
                range(7),
                key=lambda i: sum((a - b) ** 2 for a, b in zip(pixel, RGB[i], strict=True)),
            )
            position = 2 if identity == 6 else identity + 1
            with self.lock:
                self.counts[position] += 1
                self.generated.append(position)
                self.prompts.append(body)
                color = "black" if position == 4 else COLORS[position - 1]
                if self.counts[position] > 1 and position in (2, 3):
                    color = {2: "white", 3: "orange"}[position]
                key = str(uuid.uuid4())
                self.submissions[key] = (color, body["duration"])
            if self.on_generate:
                self.on_generate()
            if self.barrier:
                self.barrier.wait(timeout=20)
            return httpx.Response(200, json={"id": key})
        if path.startswith("/videos/"):
            key = path.split("/")[2]
            if path.endswith("/content"):
                return httpx.Response(200, content=self.clips[self.submissions[key]])
            return httpx.Response(200, json=completed(job_id=key))
        assert path == "/chat/completions", path
        parts = json.loads(request.content)["messages"][0]["content"]
        videos = [part for part in parts if part["type"] == "video_url"]
        if videos:
            clip = base64.b64decode(videos[0]["video_url"]["url"].split(",")[1])
            color = next(color for color, data in self.clips.items() if data == clip)
            with self.lock:
                self.checked.append(color[0])
            answer = dict(
                aiScore=0.1,
                matchScore=0.99,
                peopleCount=0,
                addedObjects=[],
                removedObjects=[],
                changedObjects=[],
                notes="Passed",
            )
        else:
            self.plans += 1
            answer = {
                "shots": [
                    dict(
                        room="living",
                        photoId=photo,
                        photoEditPrompts=[],
                        movementName="dolly_in",
                        movementPrompt=MOVEMENTS["dolly_in"],
                        speed="slow",
                        model=MODEL_LIST["data"][0]["id"],
                        lengthS=4,
                        transition="cut",
                        transitionS=0,
                        planNote="Synthetic editor integration",
                    )
                    for photo in self.photos[:6]
                ],
                "notes": "",
            }
        return httpx.Response(200, json=_chat_answer(json.dumps(answer)))


class World:
    def __init__(self, job_id, photos, api, client, folder):
        self.job_id, self.photos, self.api = job_id, photos, api
        self.client, self.folder = client, folder
        self.old_job = self.job()
        self.old_shots = self.shots()
        self.old_attempts = self.attempts()
        self.old_objects = {a["clip_key"]: self.digest(a["clip_key"]) for a in self.old_attempts}
        self.old_video_hash = self.digest(self.old_job["video_key"])
        assert len(self.old_shots) == len(self.old_attempts) == 6
        assert Counter(api.generated) == {1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1}
        assert all(shot["status"] == "passed" for shot in self.old_shots)
        initial = decode(self.download(self.old_job["video_key"]))
        assert len(initial) == 720
        self.old_calls = self.calls()
        api.generated.clear()
        api.checked.clear()
        api.prompts.clear()

    def job(self):
        return rows("select * from jobs where id=:j", j=self.job_id)[0]

    def shots(self):
        return rows("select * from job_shots where job_id=:j order by position", j=self.job_id)

    def attempts(self):
        return rows(
            "select a.* from attempts a join job_shots s on s.id=a.job_shot_id "
            "where s.job_id=:j order by s.position,a.round,a.attempt_no",
            j=self.job_id,
        )

    def calls(self):
        return rows("select * from provider_calls where job_id=:j order by id", j=self.job_id)

    def download(self, key):
        path = self.folder / (hashlib.sha256(key.encode()).hexdigest() + ".mp4")
        files.get(key, str(path))
        return path

    def digest(self, key):
        return hashlib.sha256(self.download(key).read_bytes()).hexdigest()

    def edit(self, position, **body):
        response = self.client.patch(f"/api/jobs/{self.job_id}/shots/{position}", json=body)
        assert response.status_code == 200, response.text
        return response.json()

    def export(self, overlap=False):
        self.clicked = datetime.now(UTC)
        response = self.client.post(f"/api/jobs/{self.job_id}/export")
        assert response.status_code == 202, response.text
        self.accepted = datetime.now(UTC)
        if overlap:
            self.api.barrier = threading.Barrier(2)
        try:
            assert runner.run_next_job()
        finally:
            self.api.barrier = None
        assert queue.get_job(self.job_id).status == "ready"
        link = self.client.get(f"/api/jobs/{self.job_id}/video")
        assert link.status_code == 200
        # Follow the actual signed URL through moto and decode the persistent object.
        response = requests.get(link.json()["url"], timeout=10)
        assert response.status_code == 200
        path = self.folder / "playable.mp4"
        path.write_bytes(response.content)
        self.frames = decode(path)
        self.probe = media.probe(str(path))
        self.playable = datetime.now(UTC)
        job = self.job()
        print(
            f"click={self.clicked.isoformat()} accept={self.accepted.isoformat()} "
            f"queued={job['submitted_at']} started={job['started_at']} "
            f"finished={job['finished_at']} decoded={self.playable.isoformat()}"
        )
        return job


@pytest.fixture
def editor_world(bucket, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_PROVIDERS", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", TEST_KEY)
    monkeypatch.setenv("OPENROUTER_BASE_URL", BASE)
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    monkeypatch.setenv("SHOTS_IN_FLIGHT", "6")
    reset_settings()
    chat.reset_pricing()
    video_api.reset_cache()
    shoot, photos = seed_shoot(["uploaded"] * 7, shoot_status="ready")
    for photo, color in zip(photos, COLORS, strict=True):
        buffer = io.BytesIO()
        Image.new("RGB", (64, 36), color).save(buffer, "JPEG")
        put_bytes(f"photoshoots/{shoot}/{photo}.jpg", buffer.getvalue())
    clips = {}
    for color, duration in [(color, 4) for color in [*COLORS, "white", "black"]] + [("cyan", 6)]:
        path = tmp_path / f"{color}-{duration}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=320x180:r=24:d={duration}",
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
        clips[color, duration] = path.read_bytes()
    song = add_song()
    song_path = tmp_path / "song.wav"
    with wave.open(str(song_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * 30)
    files.put(f"songs/{song}.mp3", str(song_path))
    api = OpenRouter(photos, clips)
    transport = httpx.MockTransport(api.handler)
    monkeypatch.setattr(chat, "TRANSPORT", transport)
    monkeypatch.setattr(video_api, "TRANSPORT", transport)
    try:
        with TestClient(create_app()) as client:
            client.auth = DEMO_AUTH
            job = drafts.create_job(
                JobCreate(photoshoot_id=shoot, style_text="Slow rooms", song_id=song)
            )
            planning.wait_idle()
            assert queue.get_job(job.id).plan_status == "ready"
            assert client.post(f"/api/jobs/{job.id}/submit").status_code == 202
            assert runner.run_next_job()
            assert queue.get_job(job.id).status == "ready"
            yield World(job.id, photos, api, client, tmp_path)
    finally:
        planning.wait_idle()
        chat.reset_pricing()
        video_api.reset_cache()
