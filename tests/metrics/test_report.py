import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.comparison.models import CutCheck
from app.db.base import session_scope
from app.db.schema import init_db
from app.jobs.models import Attempt, Job, JobShot
from app.library.models import Song
from app.metrics import queries
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
                    stop_reason="out_of_credit" if status == "stopped" else None,
                    started_at=t(m=2, s=0),
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
                error_kind="out_of_credit",
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


def test_error_rows_identify_unmeasured_calls():
    init_db()
    with session_scope() as s:
        s.add(
            ProviderCall(
                id="unmatched",
                kind="generate_clip",
                model="m",
                status="error",
                error_kind="rate_limited",
                started_at="2026-01-01T00:00:00Z",
            )
        )
    with session_scope() as s:
        panel = _panels(render_report(s))[2]
    assert "call=unmatched" in panel
    assert "rate_limited" in panel
    assert "unmeasured" in panel
    assert "message availability" in panel


def test_error_measurements_survive_requeue_and_identify_each_call():
    test_seeded_rows_print_the_expected_numbers()
    with session_scope() as s:
        job = s.get(Job, "j2")
        job.status = "queued"
        job.finished_at = None
        job.stop_reason = None
    with session_scope() as s:
        panel = _panels(render_report(s))[2]
    assert "call=c1 job=j1 shot=s1 attempt=a1 error=unknown: 42.0 s" in panel
    # A job-only stop timestamp is cleared on requeue; do not invent a delay
    # from a later completion. Actual pipeline errors keep their attempt timestamp.
    assert "call=c2 job=j2 shot=- attempt=- error=out_of_credit: unmeasured" in panel
    assert "call=c3" not in panel


def test_early_edit_error_is_not_measured_against_a_later_stop():
    init_db()
    _seed()
    t = "2026-10-18T10:{m:02d}:{s:02d}.000Z".format
    with session_scope() as s:
        s.add(
            Job(
                id="j",
                style_text="x",
                photoshoot_id="ps",
                song_id="song",
                song_offset_s=0,
                fps=24,
                status="stopped",
                stop_reason="out_of_credit",
                started_at=t(m=0, s=0),
                finished_at=t(m=20, s=0),
            )
        )
        s.flush()
        # a handled edit error at minute 1 (no attempt), and the credit error that stopped the job
        for call_id, kind, finished in (
            ("early", "rate_limited", t(m=1, s=0)),
            ("cause", "out_of_credit", t(m=19, s=58)),
        ):
            s.add(
                ProviderCall(
                    id=call_id,
                    kind="edit_photo",
                    model="m",
                    job_id="j",
                    status="error",
                    error_kind=kind,
                    started_at=t(m=0, s=59),
                    finished_at=finished,
                )
            )
    with session_scope() as s:
        delays = {r["call_id"]: r["delay_s"] for r in queries.provider_error_delays(s)}
        assert queries.provider_error_to_user_s(s) == pytest.approx(2.0, abs=0.01)
    assert delays["early"] is None
    assert delays["cause"] == pytest.approx(2.0, abs=0.01)


def test_sheet_restricts_every_panel_to_its_jobs(tmp_path, capsys):
    from app.metrics.__main__ import main

    test_seeded_rows_print_the_expected_numbers()
    with session_scope() as s:
        everything = render_report(s)
        only_j1 = render_report(s, ["j1"])
        nothing = render_report(s, [])
    assert "15.5 min" in everything and "15.5 min" not in only_j1
    slowest, typical, provider_error, attempts, dropped, cut = _panels(only_j1)
    assert "10.0 min" in slowest and "10.0 min" in typical
    assert "42.0 s" in provider_error and "call=c2" not in provider_error
    assert "Value:       2\n" in attempts and "Value:       2\n" in dropped
    assert all("no data yet" in panel for panel in _panels(nothing))

    sheet = tmp_path / "sheet.csv"
    sheet.write_text("kind,job_id\nplan,j2\nattempt,j2\nplan,\n")
    assert main(["--sheet", str(sheet)]) == 0
    printed = capsys.readouterr().out
    assert "21.0 min" in _panels(printed)[1]
