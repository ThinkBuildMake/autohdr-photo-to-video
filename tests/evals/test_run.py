import pytest

from app.evals.__main__ import main
from tests.evals.conftest import STYLE, read_sheet, run_suite
from tests.support.evals_rows import add_job, add_style
from tests.support.library_rows import add_song

JUDGMENTS = ("visibly_ai", "room_changed", "movement_matches", "transition_matches")


def test_ev1_creates_and_submits_a_job_per_shoot(world, fake_jobs):
    run_suite(world, "ev1")

    assert [body.photoshoot_id for body in fake_jobs.created] == world.shoots
    assert {body.style_id for body in fake_jobs.created} == {world.style}
    assert {body.style_text for body in fake_jobs.created} == {"Golden hour: slow and warm."}
    assert {body.song_id for body in fake_jobs.created} == {world.song}
    assert {body.purpose for body in fake_jobs.created} == {"video"}
    assert len(fake_jobs.submitted) == 12
    assert len(set(fake_jobs.submitted)) == 12


def test_ev2_skips_the_demo_shoot(world, fake_jobs):
    run_suite(world, "ev2")

    shoots = [body.photoshoot_id for body in fake_jobs.created]
    assert len(shoots) == 2
    assert world.shoots[0] not in shoots
    assert {body.purpose for body in fake_jobs.created} == {"reproduction"}
    assert {body.style_text for body in fake_jobs.created} == {"Golden hour: slow and warm."}
    assert len(fake_jobs.submitted) == 2


def _seed_two_reproductions(world, fake_jobs) -> None:
    """30 attempts with clips (4 flagged) and one error attempt without a clip."""
    first = [["passed"]] * 8 + [["flagged", "passed"]] * 2
    second = [["passed"]] * 13 + [["flagged", "passed"]] * 2 + [["error", "passed"]]
    for shoot, shots in zip(world.shoots[1:3], (first, second), strict=True):
        fake_jobs.by_shoot[shoot] = add_job(
            shoot, world.song, world.style, purpose="reproduction", shots=shots
        )


def test_sheet_has_a_row_per_attempt(world, fake_jobs):
    _seed_two_reproductions(world, fake_jobs)

    rows = read_sheet(run_suite(world, "ev2"))

    attempts = [row for row in rows if row["kind"] == "attempt"]
    assert len(attempts) == 30
    assert sum(row["flagged"] == "yes" for row in attempts) == 4
    for row in attempts:
        assert row["clip_link"].startswith("https://")
        assert "/clips/" in row["clip_link"]
        assert all(row[column] == "" for column in JUDGMENTS)


def test_sheet_has_plan_and_reproduction_rows(world, fake_jobs):
    _seed_two_reproductions(world, fake_jobs)
    jobs = {fake_jobs.by_shoot[shoot] for shoot in world.shoots[1:3]}

    rows = read_sheet(run_suite(world, "ev2"))

    plans = [row for row in rows if row["kind"] == "plan"]
    reproductions = [row for row in rows if row["kind"] == "reproduction"]
    assert {row["job_id"] for row in plans} == jobs
    assert {row["job_id"] for row in reproductions} == jobs
    assert len(plans) == 2
    assert len(reproductions) == 2
    assert all(row["text_followed"] == "" for row in plans)
    assert all(row["looks_like_reference"] == "" for row in reproductions)
    assert all("/videos/" in row["clip_link"] for row in plans + reproductions)


def test_run_before_import_says_so(tmp_path, bucket, capsys):
    add_style(STYLE, add_song())

    with pytest.raises(SystemExit) as stopped:
        main(["run", "--suite", "ev1", "--style", STYLE, "--out", str(tmp_path / "empty")])

    assert stopped.value.code not in (0, None)
    assert "evals import" in str(stopped.value.code) + capsys.readouterr().err
