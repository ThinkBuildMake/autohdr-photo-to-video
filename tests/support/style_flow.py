"""Synthetic authoring world: real app seams, simulated provider HTTP and bucket."""

import json
import subprocess
import time
import wave
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from app.config import reset_settings
from app.files import service as files
from app.jobs import planning, queue
from app.jobs.plan_rules import MOVEMENTS
from app.pipeline import runner
from app.providers import chat, video_api
from tests.photoshoots.conftest import seed_shoot
from tests.providers.chat.conftest import BASE, MODELS_JSON, TEST_KEY, _chat_answer
from tests.providers.video.conftest import MODEL_LIST, completed
from tests.support.library_rows import add_song


class StyleFlow:
    def __init__(self, song_id, shoots, photos, clip):
        self.song_id = song_id
        self.shoots = shoots
        self.photos = photos
        self.clip = clip

    def handler(self, request):
        path = request.url.path.removeprefix("/api/v1")
        if path == "/models":
            return httpx.Response(200, json=MODELS_JSON)
        if path == "/videos/models":
            return httpx.Response(200, json=MODEL_LIST)
        if path == "/videos":
            return httpx.Response(200, json={"id": "synthetic-clip"})
        if path.endswith("/content"):
            return httpx.Response(200, content=self.clip)
        if path.startswith("/videos/"):
            return httpx.Response(200, json=completed(job_id="synthetic-clip"))
        assert path == "/chat/completions", path
        body = json.loads(request.content)
        parts = body["messages"][0]["content"]
        if any(p["type"] == "video_url" for p in parts):
            answer = {
                "aiScore": 0.1,
                "matchScore": 0.99,
                "peopleCount": 0,
                "addedObjects": [],
                "removedObjects": [],
                "changedObjects": [],
                "notes": "Synthetic passing clip",
            }
        else:
            prompt = json.dumps(body)
            photo = next(photo for photo in self.photos if photo in prompt)
            answer = {
                "shots": [
                    {
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
                        "planNote": "Synthetic authoring plan",
                    }
                ],
                "notes": "",
            }
        return httpx.Response(200, json=_chat_answer(json.dumps(answer)))

    def finish(self, job_id):
        planning.wait_idle()
        job = queue.get_job(job_id)
        assert job.plan_status == "ready", job.plan_notes
        if job.status == "draft":
            queue.submit_job(job_id)
        assert runner.run_next_job()
        result = queue.get_job(job_id)
        assert result.status == "ready", result.stop_reason
        return result

    def wait_for_submission(self, job_id):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if queue.get_job(job_id).status == "queued":
                return
            time.sleep(0.02)
        raise AssertionError("Authoring did not submit its planned try within 15 seconds")

    def wait_for_job(self, client, count):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            jobs = client.get("/api/jobs").json()["jobs"]
            if len(jobs) == count:
                planning.wait_idle()
                return jobs[0]["id"]
            time.sleep(0.02)
        raise AssertionError("Authoring did not create a job within 15 seconds")

    def serve_media(self, route):
        from urllib.parse import unquote, urlparse

        from app.files.client import bucket_name, get_client

        path = unquote(urlparse(route.request.url).path).lstrip("/")
        if path.startswith(bucket_name() + "/"):
            path = path[len(bucket_name()) + 1 :]
        data = get_client().get_object(Bucket=bucket_name(), Key=path)["Body"].read()
        # Chromium in the gate needs VP8/WebM; keep the real pipeline's stored MP4 intact.
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.mp4"
            target = Path(directory) / "browser.webm"
            source.write_bytes(data)
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(source),
                    "-vf",
                    "scale=320:180",
                    "-c:v",
                    "libvpx",
                    "-deadline",
                    "realtime",
                    "-c:a",
                    "libopus",
                    "-ar",
                    "48000",
                    "-f",
                    "webm",
                    str(target),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            browser_video = target.read_bytes()
        # Chromium only seeks media that answers byte ranges.
        headers = {"Accept-Ranges": "bytes"}
        wanted = getattr(route.request, "headers", {}).get("range")
        if wanted:
            start, _, end = wanted.removeprefix("bytes=").partition("-")
            first, last = (
                int(start),
                min(int(end or len(browser_video) - 1), len(browser_video) - 1),
            )
            headers["Content-Range"] = f"bytes {first}-{last}/{len(browser_video)}"
            route.fulfill(
                status=206,
                content_type="video/webm",
                headers=headers,
                body=browser_video[first : last + 1],
            )
        else:
            route.fulfill(
                status=200, content_type="video/webm", headers=headers, body=browser_video
            )


@contextmanager
def style_world(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_PROVIDERS", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", TEST_KEY)
    monkeypatch.setenv("OPENROUTER_BASE_URL", BASE)
    reset_settings()
    chat.reset_pricing()
    video_api.reset_cache()
    shoots, photos = [], []
    for label in ("Demo house", "Second house"):
        shoot, ids = seed_shoot(["uploaded"], "ready", label=label)
        shoots.append(shoot)
        photos.extend(ids)
    clip = tmp_path / "synthetic.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:r=30:d=4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(clip),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    song = add_song()
    audio_path = tmp_path / "song.wav"
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * 8)
    files.put(f"songs/{song}.mp3", str(audio_path))
    world = StyleFlow(song, shoots, photos, clip.read_bytes())
    transport = httpx.MockTransport(world.handler)
    monkeypatch.setattr(chat, "TRANSPORT", transport)
    monkeypatch.setattr(video_api, "TRANSPORT", transport)
    try:
        yield world
    finally:
        planning.wait_idle()
        chat.reset_pricing()
        video_api.reset_cache()
