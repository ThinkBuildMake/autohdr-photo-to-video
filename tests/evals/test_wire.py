"""evals import + run + report across the real Photoshoots, Jobs, Pipeline, Files and Providers;
only OpenRouter HTTP and S3 are simulated. One of the two jobs is stopped (out of credit)."""

import json
import subprocess
import threading
import time
import wave
from datetime import datetime

import httpx

from app.config import reset_settings
from app.evals import runs
from app.evals.__main__ import main
from app.files import service as files
from app.jobs import queue
from app.metrics.__main__ import main as metrics_main
from app.photoshoots import service as photoshoots
from app.pipeline import runner
from app.providers import chat, video_api
from tests.evals.conftest import STYLE, read_sheet
from tests.pipeline.test_wire import OpenRouter
from tests.providers.chat.conftest import BASE, TEST_KEY
from tests.support.evals_rows import _jpeg, add_style
from tests.support.library_rows import add_song
from tests.support.worker_rows import rows

PHOTOS_PER_SHOOT = 4  # the mocked plan is four shots, one per photo


def _clips(tmp_path) -> dict[str, bytes]:
    clips = {}
    for color in ("red", "blue", "green", "yellow", "magenta"):
        path = tmp_path / f"{color}.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=320x180:r=24:d=4"]
            + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(path)],
            check=True,
            capture_output=True,
            timeout=30,
        )
        clips[color] = path.read_bytes()
    return clips


def _song(tmp_path) -> str:
    song = add_song()
    path = tmp_path / "tone.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0\xff\x0f" * 8000 * 8)
    files.put(f"songs/{song}.mp3", str(path))
    return song


def _transport(clips, stopped_photos: set[str]) -> httpx.MockTransport:
    """The shared OpenRouter answers, except: plans use the photos the request names, and a
    clip for a plan made from `stopped_photos` is answered 402 (out of credit)."""

    def handler(request):
        path = request.url.path.removeprefix("/api/v1")
        if path == "/chat/completions":
            parts = json.loads(request.content)["messages"][0]["content"]
            ids = [
                p["text"].split(";")[0].removeprefix("photoId: ")
                for p in parts
                if p["type"] == "text" and p["text"].startswith("photoId: ")
            ]
            if ids:
                response = OpenRouter(ids, clips).handler(request)
                if stopped_photos & set(ids):
                    response = httpx.Response(
                        200, content=response.content.replace(b"wire-", b"stopme wire-")
                    )
                return response
        if path == "/videos" and request.method == "POST" and b"stopme" in request.content:
            return httpx.Response(402, json={"error": {"message": "Insufficient credits"}})
        return api.handler(request)

    api = OpenRouter([], clips)
    return httpx.MockTransport(handler)


def test_import_and_run_over_real_modules_with_a_stopped_job(tmp_path, bucket, monkeypatch, capsys):
    folder = tmp_path / "shoots"
    for label in ("Shoot A", "Shoot B"):
        (folder / label).mkdir(parents=True)
        for n in range(PHOTOS_PER_SHOOT):
            (folder / label / f"{n}.jpg").write_bytes(_jpeg())
    out = tmp_path / "out"
    assert main(["import", "--folder", str(folder), "--out", str(out)]) == 0
    shoots = json.loads((out / "shoots.json").read_text())
    stopped_photos = {p.id for p in photoshoots.get_photoshoot(shoots["Shoot B"]).photos}

    monkeypatch.setenv("FAKE_PROVIDERS", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", TEST_KEY)
    monkeypatch.setenv("OPENROUTER_BASE_URL", BASE)
    reset_settings()
    chat.reset_pricing()
    video_api.reset_cache()
    transport = _transport(_clips(tmp_path), stopped_photos)
    monkeypatch.setattr(chat, "TRANSPORT", transport)
    monkeypatch.setattr(video_api, "TRANSPORT", transport)
    monkeypatch.setattr(runs, "POLL_S", 0.05)
    add_style(STYLE, _song(tmp_path))

    quit_worker = threading.Event()

    def worker():
        while not quit_worker.is_set():
            if not runner.run_next_job():
                time.sleep(0.05)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        assert (
            main(
                ["run", "--suite", "ev1", "--style", STYLE, "--out", str(out), "--timeout-min", "5"]
            )
            == 0
        )
    finally:
        quit_worker.set()
        thread.join(30)
        chat.reset_pricing()
        video_api.reset_cache()

    (run_folder,) = [p for p in out.iterdir() if p.is_dir()]
    sheet = read_sheet(run_folder)
    plans = {row["shoot"]: row["job_id"] for row in sheet if row["kind"] == "plan"}
    assert set(plans) == {"Shoot A", "Shoot B"}
    assert queue.get_job(plans["Shoot A"]).status == "ready_with_failures"
    stopped = queue.get_job(plans["Shoot B"])
    assert (stopped.status, stopped.stop_reason) == ("stopped", "out_of_credit")
    attempts = [row for row in sheet if row["kind"] == "attempt"]
    assert {row["job_id"] for row in attempts} == set(plans.values())
    a_rows = [row for row in attempts if row["job_id"] == plans["Shoot A"]]
    assert len(a_rows) == 8 and sum(row["flagged"] == "yes" for row in a_rows) == 5
    assert sum(row["in_video"] == "yes" for row in a_rows) == 3

    report = next(run_folder.glob("report-*.md")).read_text()
    table = {line.split("|")[2].strip(): line for line in report.splitlines() if "| Shoot " in line}
    assert "ready_with_failures" in table["Shoot A"] and table["Shoot A"].strip().endswith("min |")
    assert "stopped (out_of_credit)" in table["Shoot B"] and table["Shoot B"].endswith("| — |")
    assert "- Video 2 (Shoot B): out_of_credit" in report

    # CO-1: each job's provider calls were stored with their cost.
    for job_id in plans.values():
        calls = rows("select kind, status, cost_usd from provider_calls where job_id=:j", j=job_id)
        assert any(call["kind"] == "plan_shots" for call in calls)
        assert any(call["kind"] == "generate_clip" for call in calls)

    capsys.readouterr()
    assert metrics_main(["--sheet", str(run_folder / "sheet.csv")]) == 0
    panel_2 = capsys.readouterr().out.split("\n\n")[1]
    only = rows(
        "select first_submitted_at, first_finished_at from jobs where id=:j", j=plans["Shoot A"]
    )[0]
    wait = (
        datetime.fromisoformat(only["first_finished_at"])
        - datetime.fromisoformat(only["first_submitted_at"])
    ).total_seconds()
    assert f"Value:       {wait / 60:.1f} min" in panel_2
