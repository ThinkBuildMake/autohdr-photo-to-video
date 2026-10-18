import os
import subprocess
import sys
from pathlib import Path

from app.comparison.models import CutCheck
from app.db.base import session_scope
from app.db.schema import init_db
from app.jobs.models import Attempt, Job, JobShot
from app.library.models import Song
from app.metrics.report import render_report
from app.photoshoots.models import Photoshoot
from app.providers.models import ProviderCall

REPO_ROOT = Path(__file__).resolve().parents[2]

TITLES = [
    "Video wait time (slowest)",
    "Video wait time (typical)",
    "Time to tell the user about a provider error",
    "Regeneration attempts per shot",
    "Shots dropped because every attempt was flagged",
    "Cut-time error against the style",
]


def _panels(text: str) -> list[str]:
    """Split a report into one block per panel, in printed order."""
    starts = [text.index(title) for title in TITLES]
    assert starts == sorted(starts)
    ends = [*starts[1:], len(text)]
    return [text[a:b] for a, b in zip(starts, ends, strict=True)]


def test_empty_database_prints_six_panels_with_no_data_yet(tmp_path):
    env = {**os.environ, "DATABASE_PATH": str(tmp_path / "fresh.db"), "FAKE_PROVIDERS": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "app.metrics"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    panels = _panels(result.stdout)
    assert len(panels) == 6
    for panel in panels:
        assert "no data yet" in panel


def _seed():
    with session_scope() as s:
        s.add(
            Song(
                id="song",
                title="s",
                artist="a",
                licence_code="BY-NC",
                source_url="u",
                file_key="k",
                duration_s=60,
            )
        )
        s.add(Photoshoot(id="ps"))
        s.flush()


def test_seeded_rows_print_the_expected_numbers():
    init_db()
    _seed()
    t = "2026-10-18T10:{m:02d}:{s:02d}.000Z".format
    with session_scope() as s:
        for job_id, status, submitted, finished, video in (
            ("j1", "ready", t(m=0, s=0), t(m=10, s=0), "v1"),
            ("j2", "stopped", t(m=0, s=0), t(m=21, s=0), None),
        ):
            s.add(
                Job(
                    id=job_id,
                    style_text="x",
                    photoshoot_id="ps",
                    song_id="song",
                    song_offset_s=0,
                    fps=24,
                    status=status,
                    stop_reason="no_shot_passed" if status == "stopped" else None,
                    first_submitted_at=submitted,
                    first_finished_at=finished,
                    finished_at=finished,
                    video_key=video,
                )
            )
        s.flush()
        for shot_id, job_id, reason in (
            ("s1", "j1", "flagged_every_attempt"),
            ("s2", "j1", "flagged_every_attempt"),
            ("s3", "j1", None),
            ("s4", "j2", "flagged_every_attempt"),
        ):
            s.add(
                JobShot(
                    id=shot_id,
                    job_id=job_id,
                    position=int(shot_id[1:]),
                    room="kitchen",
                    movement_name="dolly_in",
                    movement_prompt="p",
                    model="m",
                    length_s=3,
                    status="failed" if reason else "passed",
                    failure_reason=reason,
                )
            )
        s.flush()
        # shot s1: three attempts in round 0 -> 2 regenerations; s3: one attempt
        for att_id, shot_id, rnd, no, finished in (
            ("a1", "s1", 0, 1, t(m=1, s=30)),
            ("a2", "s1", 0, 2, t(m=2, s=0)),
            ("a3", "s1", 0, 3, t(m=3, s=0)),
            ("a4", "s3", 0, 1, t(m=4, s=0)),
            ("a5", "s3", 1, 1, t(m=5, s=0)),
        ):
            s.add(
                Attempt(
                    id=att_id,
                    job_shot_id=shot_id,
                    round=rnd,
                    attempt_no=no,
                    prompt="p",
                    model="m",
                    requested_s=3,
                    started_at=t(m=1, s=0),
                    finished_at=finished,
                )
            )
        s.flush()
        # error with an attempt: 42 s; error without one on stopped job j2: 21:00 - 20:30 = 30 s
        s.add(
            ProviderCall(
                id="c1",
                kind="video",
                model="m",
                job_id="j1",
                job_shot_id="s1",
                attempt_id="a1",
                status="error",
                started_at=t(m=0, s=50),
                finished_at=t(m=0, s=48),
            )
        )
        s.add(
            ProviderCall(
                id="c2",
                kind="video",
                model="m",
                job_id="j2",
                status="error",
                started_at=t(m=19, s=0),
                finished_at=t(m=20, s=30),
            )
        )
        s.add(
            ProviderCall(
                id="c3",
                kind="video",
                model="m",
                job_id="j1",
                status="ok",
                started_at=t(m=0, s=0),
                finished_at=t(m=0, s=5),
            )
        )
        for position, expected, detected, error in ((1, 3.0, 3.04, 0.04), (2, 6.0, 5.93, -0.07)):
            s.add(
                CutCheck(
                    job_id="j1",
                    position=position,
                    expected_s=expected,
                    detected_s=detected,
                    error_s=error,
                    transition="cut",
                )
            )

    with session_scope() as s:
        text = render_report(s)

    slowest, typical, provider_error, attempts, dropped, cut = _panels(text)
    # j1 waited 10 min; j2 waited 21 min
    assert "21.0 min" in slowest
    assert "15.5 min" in typical
    # c1: a1 finished 10:01:30, call finished 10:00:48 -> 42 s; c2: 30 s
    assert "42.0 s" in provider_error
    # s1 has 3 attempts in round 0 -> 2 regenerations
    assert "Value:       2\n" in attempts
    # j1 has a video and two flagged shots; j2 has none (no video)
    assert "Value:       2\n" in dropped
    assert "0.070 s" in cut
    for panel in (slowest, typical, provider_error, attempts, dropped, cut):
        assert "no data yet" not in panel
