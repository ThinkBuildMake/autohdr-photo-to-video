"""Submitted job across real modules; only OpenRouter HTTP and S3 are simulated."""

import base64
import json
import subprocess
import threading
import uuid
import wave
from collections import Counter
from datetime import datetime

import httpx
import pytest

from app.config import reset_settings
from app.db.base import session_scope
from app.files import service as files
from app.jobs import drafts, planning, queue
from app.jobs.plan_rules import MOVEMENTS
from app.jobs.schemas import JobCreate
from app.library.models import Style
from app.media import service as media
from app.metrics import queries
from app.metrics.report import render_report
from app.pipeline import runner
from app.providers import chat, video_api
from tests.photoshoots.conftest import seed_shoot
from tests.providers.chat.conftest import BASE, MODELS_JSON, TEST_KEY, _chat_answer
from tests.providers.video.conftest import MODEL_LIST, completed
from tests.support.library_rows import add_song
from tests.support.worker_rows import rows


class OpenRouter:
    """Route concurrent requests by clip identity, never by thread arrival order."""

    def __init__(self, photos, clips):
        self.photos = photos
        self.clips = clips
        self.submissions = {}
        self.checks = Counter()
        self.generations = Counter()
        self.lock = threading.Lock()

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
                key = str(uuid.uuid4())
                self.generations[color] += 1
                self.submissions[key] = (
                    "magenta" if color == "red" and self.generations[color] == 1 else color
                )
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
                flagged = color in ("green", "magenta")
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
def submitted_world(bucket, tmp_path, monkeypatch):
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
    api = OpenRouter(photos, clips)
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


def test_submitted_job_runs_every_seam_and_reports_stored_metrics(submitted_world, tmp_path):
    job_id, api = submitted_world
    submitted = queue.submit_job(job_id)
    assert submitted.status == "queued"

    assert runner.run_next_job() is True

    job = rows("select * from jobs where id=:j", j=job_id)[0]
    assert queue.get_job(job_id).status == "ready_with_failures"
    assert queue.get_video(job_id)["duration_s"] == pytest.approx(12, abs=1 / 24)
    assert job["fps"] == 24
    output = str(tmp_path / "finished.mp4")
    files.get(job["video_key"], output)
    probe = media.probe(output)
    assert (probe["width"], probe["height"], probe["fps"]) == (1920, 1080, 24)
    assert probe["durationS"] == pytest.approx(12, abs=1 / 24)
    # Decode every frame; nearest palette entry tolerates lossy H.264 encoding.
    decoded = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            output,
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
        timeout=30,
    ).stdout
    palette = {
        "red": (255, 0, 0),
        "blue": (0, 0, 255),
        "yellow": (255, 255, 0),
        "green": (0, 128, 0),
        "magenta": (255, 0, 255),
    }
    frame_colors = [
        min(
            palette,
            key=lambda color: sum(
                (a - b) ** 2 for a, b in zip(decoded[i : i + 3], palette[color], strict=True)
            ),
        )
        for i in range(0, len(decoded), 3)
    ]
    assert frame_colors == ["red"] * 96 + ["blue"] * 96 + ["yellow"] * 96
    assert not {"magenta", "green"}.intersection(frame_colors)
    shots = rows("select * from job_shots where job_id=:j order by position", j=job_id)
    attempts = rows(
        "select a.* from attempts a join job_shots s on s.id=a.job_shot_id "
        "where s.job_id=:j order by s.position,a.attempt_no",
        j=job_id,
    )
    by_shot = [[a for a in attempts if a["job_shot_id"] == s["id"]] for s in shots]
    assert [[a["status"] for a in group] for group in by_shot] == [
        ["flagged", "passed"],
        ["passed"],
        ["flagged"] * 4,
        ["passed"],
    ]
    assert shots[0]["final_attempt_id"] == by_shot[0][1]["id"]
    assert by_shot[0][0]["check_ai_score"] == 0.9
    assert shots[2]["status"] == "failed"
    assert shots[2]["failure_reason"] == "flagged_every_attempt"
    assert shots[2]["final_attempt_id"] is None
    assert api.checks == {"magenta": 1, "red": 1, "blue": 1, "green": 4, "yellow": 1}
    calls = rows("select * from provider_calls where job_id=:j", j=job_id)
    assert Counter(c["kind"] for c in calls) == {
        "plan_shots": 1,
        "generate_clip": 8,
        "check_clip": 8,
    }
    assert all(c["status"] == "ok" for c in calls)
    cuts = rows("select * from cut_checks where job_id=:j order by position", j=job_id)
    # Independent fixture oracle: red, blue, yellow each occupy exactly 96 frames.
    assert [s["length_s"] for s in shots] == [4, 4, 4, 4]
    expected = [96 / 24, 192 / 24]
    assert len(cuts) == 2
    assert [c["job_id"] for c in cuts] == [job_id, job_id]
    assert [c["position"] for c in cuts] == [shots[1]["position"], shots[3]["position"]]
    assert [c["transition"] for c in cuts] == ["cut", "cut"]
    assert [c["expected_s"] for c in cuts] == expected
    detected = media.detect_cuts(output)
    assert len(detected) == len(expected) > 0
    for actual, planned, cut in zip(detected, expected, cuts, strict=True):
        assert abs(actual - planned) <= 0.1
        assert cut["detected_s"] == pytest.approx(actual)
        assert cut["error_s"] == pytest.approx(actual - planned, abs=0.001)
    wait = (
        datetime.fromisoformat(job["first_finished_at"])
        - datetime.fromisoformat(job["first_submitted_at"])
    ).total_seconds()
    assert 0 <= wait <= 1800
    assert job["first_submitted_at"] == submitted.submitted_at
    regenerations = max(len(group) for group in by_shot) - 1
    dropped = sum(s["failure_reason"] == "flagged_every_attempt" for s in shots)
    cut_error = max(abs(c["detected_s"] - c["expected_s"]) for c in cuts)
    assert (regenerations, dropped) == (3, 1)
    with session_scope() as session:
        assert queries.slowest_wait_s(session) == pytest.approx(wait, abs=0.001)
        assert queries.typical_wait_s(session) == pytest.approx(wait, abs=0.001)
        assert queries.max_regenerations_per_shot(session) == regenerations
        assert queries.max_shots_dropped_per_video(session) == dropped
        assert queries.max_cut_error_s(session) == pytest.approx(cut_error, abs=0.001)
        report = render_report(session)
    panels = report.split("\n\n")
    assert f"Value:       {wait / 60:.1f} min" in panels[0]
    assert f"Value:       {wait / 60:.1f} min" in panels[1]
    assert panels[3].splitlines()[-1] == f"  Value:       {regenerations}"
    assert panels[4].splitlines()[-1] == f"  Value:       {dropped}"
    assert f"Value:       {cut_error:.3f} s" in panels[5]
    print(f"video={probe}; planned={expected}; detected={detected}")
    print("attempts=flagged,passed / passed / four flagged / passed; dropped=1")
    print(report)
