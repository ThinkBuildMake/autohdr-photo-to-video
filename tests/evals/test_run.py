import csv
import threading
import time
from types import SimpleNamespace

import pytest

from app.evals import runs
from app.evals.__main__ import main
from app.jobs import planning, queue
from app.jobs.errors import JobNotFound
from app.providers.errors import ProviderError
from tests.evals.conftest import STYLE, read_sheet, run_suite
from tests.support.evals_rows import add_job, add_style
from tests.support.library_rows import add_song

JUDGMENTS = ("visibly_ai", "room_changed", "movement_matches", "transition_matches")


def test_ev1_creates_and_submits_a_real_job_per_shoot(world, fake_jobs):
    folder = run_suite(world, "ev1")

    assert [body.photoshoot_id for body in fake_jobs.created] == world.shoots
    assert {body.style_id for body in fake_jobs.created} == {world.style}
    assert {body.style_text for body in fake_jobs.created} == {"Golden hour: slow and warm."}
    assert {body.song_id for body in fake_jobs.created} == {world.song}
    assert {body.purpose for body in fake_jobs.created} == {"video"}
    assert len(set(fake_jobs.submitted)) == 12
    for job_id in fake_jobs.submitted:
        assert queue.get_job(job_id).status == "ready"
    plans = [row for row in read_sheet(folder) if row["kind"] == "plan"]
    assert [row["job_id"] for row in plans] == fake_jobs.submitted
    assert all(row["note"] == "" for row in plans)


def test_ev2_skips_the_demo_shoot(world, fake_jobs):
    run_suite(world, "ev2")

    shoots = [body.photoshoot_id for body in fake_jobs.created]
    assert len(shoots) == 2
    assert world.shoots[0] not in shoots
    assert {body.purpose for body in fake_jobs.created} == {"reproduction"}
    assert len(fake_jobs.submitted) == 2


def test_ev2_refuses_a_style_with_no_reference_video(world, fake_jobs, capsys):
    add_style("No reference", world.song, demo_photoshoot_id=world.shoots[0])

    with pytest.raises(SystemExit) as stopped:
        main(["run", "--suite", "ev2", "--style", "No reference", "--out", str(world.out)])

    assert "reference video" in str(stopped.value.code)
    assert fake_jobs.created == []


def _seed_two_reproductions(world, fake_jobs) -> None:
    """31 attempts (2 + 2 flagged), one error attempt made no clip."""
    first = [["passed"]] * 8 + [["flagged", "passed"]] * 2
    second = [["passed"]] * 13 + [["flagged", "passed"]] * 2 + [["error", "passed"]]
    for shoot, shots in zip(world.shoots[1:3], (first, second), strict=True):
        fake_jobs.by_shoot[shoot] = add_job(
            shoot, world.song, world.style, purpose="reproduction", shots=shots
        )


def test_sheet_has_a_row_per_attempt_even_without_a_clip(world, fake_jobs):
    _seed_two_reproductions(world, fake_jobs)

    rows = read_sheet(run_suite(world, "ev2"))

    attempts = [row for row in rows if row["kind"] == "attempt"]
    assert len(attempts) == 31
    assert sum(row["flagged"] == "yes" for row in attempts) == 4
    assert {row["round"] for row in attempts} == {"0"}
    no_clip = [row for row in attempts if not row["clip_key"]]
    assert len(no_clip) == 1
    assert no_clip[0]["clip_link"] == ""
    for row in attempts:
        if row["clip_key"]:
            assert row["clip_link"].startswith("https://")
            assert row["clip_key"] in row["clip_link"]
        assert all(row[column] == "" for column in JUDGMENTS)


def test_plan_rows_carry_the_style_text_and_reproduction_rows_the_reference(world, fake_jobs):
    _seed_two_reproductions(world, fake_jobs)
    jobs = set(fake_jobs.by_shoot.values())

    rows = read_sheet(run_suite(world, "ev2"))

    plans = [row for row in rows if row["kind"] == "plan"]
    reproductions = [row for row in rows if row["kind"] == "reproduction"]
    assert {row["job_id"] for row in plans} == jobs
    assert {row["job_id"] for row in reproductions} == jobs
    assert {row["plan_text"] for row in plans} == {"Golden hour: slow and warm."}
    assert all(row["text_followed"] == "" for row in plans)
    assert all(row["looks_like_reference"] == "" for row in reproductions)
    assert all("/videos/" in row["clip_link"] for row in plans + reproductions)
    for row in reproductions:
        assert f"videos/{world.reference}.mp4" in row["reference_link"]
    assert all(row["reference_link"] == "" for row in plans)


def test_two_runs_in_one_second_get_different_folders(world, fake_jobs):
    for _ in range(2):
        main(["run", "--suite", "ev2", "--style", STYLE, "--out", str(world.out)])

    folders = [p.name for p in world.out.iterdir() if p.is_dir()]
    assert len(set(folders)) == 2
    assert all(name.startswith("ev2-golden-hour-") for name in folders)


def test_a_failed_plan_is_noted_on_the_sheet_and_the_job_is_skipped(world, fake_jobs, monkeypatch):
    real_plan = planning.plan_shots

    def plan(style_text, budget, photos, movements, lengths, ids):
        if ids["photoshootId"] == world.shoots[1]:
            raise ProviderError("bad_response", "planner down")
        return real_plan(style_text, budget, photos, movements, lengths, ids)

    monkeypatch.setattr(planning, "plan_shots", plan)

    rows = read_sheet(run_suite(world, "ev2"))

    (failed,) = [row for row in rows if row["kind"] == "plan" and row["note"]]
    assert "plan failed" in failed["note"]
    assert failed["job_id"] not in fake_jobs.submitted
    assert len(fake_jobs.submitted) == 1


def test_jobs_that_do_not_finish_in_time_still_get_a_sheet_and_a_failing_exit(
    world, fake_jobs, monkeypatch
):
    # The clock stands still while the plans are made (they run on real threads), then jumps
    # past the deadline once the jobs are submitted: no race between planner speed and timeout.
    now = [0.0]
    monkeypatch.setattr(runs, "time", SimpleNamespace(monotonic=lambda: now[0], sleep=time.sleep))
    fake_jobs.finish = False
    submit = fake_jobs.submit_job
    fake_jobs.submit_job = lambda job_id: (now.__setitem__(0, 1e6), submit(job_id))[1]
    monkeypatch.setattr(runs.queue, "submit_job", fake_jobs.submit_job)

    with pytest.raises(SystemExit) as stopped:
        runs.run_suite("ev2", STYLE, world.out, timeout_min=1)

    assert "Timed out" in str(stopped.value.code)
    (folder,) = [p for p in world.out.iterdir() if p.is_dir()]
    notes = {row["note"] for row in read_sheet(folder) if row["kind"] == "plan"}
    assert notes == {"not finished before the timeout"}


def test_a_plan_that_never_arrives_times_out_too(world, fake_jobs, monkeypatch):
    release = threading.Event()
    real_plan = planning.plan_shots

    def slow(*args):
        release.wait(10)
        return real_plan(*args)

    monkeypatch.setattr(planning, "plan_shots", slow)

    try:
        with pytest.raises(SystemExit) as stopped:
            runs.run_suite("ev2", STYLE, world.out, timeout_min=0.0005)
    finally:
        release.set()

    assert "Timed out" in str(stopped.value.code)
    assert fake_jobs.submitted == []
    (folder,) = [p for p in world.out.iterdir() if p.is_dir()]
    assert all("not ready in time" in row["note"] for row in read_sheet(folder)[:1])


def test_a_missing_job_is_a_row_note_and_the_sheet_is_still_written(world, fake_jobs, monkeypatch):
    def gone(job_id):
        raise JobNotFound(job_id)

    monkeypatch.setattr(runs.queue, "get_job", gone)

    folder = runs.run_suite("ev2", STYLE, world.out)

    plans = [row for row in read_sheet(folder) if row["kind"] == "plan"]
    assert len(plans) == 2 and all("missing" in row["note"] for row in plans)


def test_an_interrupted_wait_still_writes_a_sheet_with_every_job(
    world, fake_jobs, monkeypatch, capsys
):
    fake_jobs.finish = False

    # the plans (real threads) finish first, then the wait for the videos is interrupted
    monkeypatch.setattr(runs, "_wait", _interrupt_second_wait(runs._wait))

    with pytest.raises(KeyboardInterrupt):
        runs.run_suite("ev2", STYLE, world.out)

    (folder,) = [p for p in world.out.iterdir() if p.is_dir()]
    plans = [row for row in read_sheet(folder) if row["kind"] == "plan"]
    assert {row["job_id"] for row in plans} == set(fake_jobs.submitted) and len(plans) == 2
    assert all("interrupted" in row["note"] for row in plans)
    assert str(folder / "sheet.csv") in capsys.readouterr().out


def _interrupt_second_wait(real_wait):
    calls = []

    def wait(jobs, done, deadline):
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return real_wait(jobs, done, deadline)

    return wait


def test_a_presign_error_while_building_rows_still_leaves_the_job_ids(
    world, fake_jobs, monkeypatch
):
    def broken(key):
        raise RuntimeError("bucket down")

    monkeypatch.setattr(runs, "_link", broken)

    folder = runs.run_suite("ev2", STYLE, world.out)

    plans = [row for row in read_sheet(folder) if row["kind"] == "plan"]
    assert {row["job_id"] for row in plans} == set(fake_jobs.submitted) and len(plans) == 2
    assert all("bucket down" in row["note"] for row in plans)


def test_relink_gives_fresh_links_and_keeps_the_reviewers_marks(world, fake_jobs):
    _seed_two_reproductions(world, fake_jobs)
    folder = run_suite(world, "ev2")
    rows = read_sheet(folder)
    stale = [{**row, "clip_link": "expired", "reference_link": "expired"} for row in rows]
    stale[3]["visibly_ai"] = "yes"
    with open(folder / "sheet.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(stale)

    fresh = runs.relink_sheet(folder / "sheet.csv")

    assert fresh.parent == folder
    with open(fresh, newline="") as handle:
        fixed = list(csv.DictReader(handle))
    assert fixed[3]["visibly_ai"] == "yes"
    for before, after in zip(rows, fixed, strict=True):
        assert after["clip_link"].startswith("https://") == bool(before["clip_key"])
        assert after["reference_link"].startswith("https://") == bool(before["reference_key"])


def test_run_before_import_says_so(tmp_path, bucket, capsys):
    add_style(STYLE, add_song())

    with pytest.raises(SystemExit) as stopped:
        main(["run", "--suite", "ev1", "--style", STYLE, "--out", str(tmp_path / "empty")])

    assert "evals import" in str(stopped.value.code) + capsys.readouterr().err
