import pytest

from app.config import reset_settings
from app.db.base import reset_engine
from app.jobs import worker_interface
from app.media.errors import MediaError
from app.pipeline import clip_stubs, run
from tests.pipeline import run_world
from tests.pipeline.clip_world import flagged_check
from tests.support.worker_rows import rows

SIX = [{"position": p} for p in range(1, 7)]


def contents(*positions):
    return [f"clip-{p}".encode() for p in positions]


def finish(world, job):
    """The worker's run of a claimed job: every shot, then the finish step, in a fresh folder."""
    state = world.run_shots(job)
    run.finish_run(state, world.folder.parent / "finish" / "job")
    return state


@pytest.mark.parametrize(
    ("script", "reason", "attempts"),
    [
        ({"checks": [flagged_check()] * 4}, "flagged_every_attempt", ["flagged"] * 4),
        ({"generate": [RuntimeError("disk full")]}, "provider_error", ["error"]),
    ],
    ids=["flagged", "crash"],
)
def test_one_failed_shot_leaves_the_rest(monkeypatch, tmp_path, script, reason, attempts):
    world = run_world.install(monkeypatch, tmp_path)
    job_id = world.seed(SIX)
    world.checks[3] = script.get("checks", [])
    world.generate[3] = script.get("generate", [])

    finish(world, world.claim())

    assert world.assembled[0]["contents"] == contents(1, 2, 4, 5, 6)
    row = world.job(job_id)
    assert row["status"] == "ready_with_failures"
    assert row["video_key"] == f"jobs/{job_id}/video-v1.mp4"
    assert clip_stubs.BUCKET[row["video_key"]] == b"|".join(contents(1, 2, 4, 5, 6))
    assert (row["video_width"], row["video_height"], row["video_fps"]) == (1920, 1080, 30)
    assert row["video_duration_s"] == 20.0
    shot = world.shots(job_id)[3]
    assert (shot["status"], shot["failure_reason"]) == ("failed", reason)
    tried = rows(
        "select status, finished_at from attempts where job_shot_id = :s order by attempt_no",
        s=shot["id"],
    )
    assert [a["status"] for a in tried] == attempts
    assert all(a["finished_at"] for a in tried)


def test_no_shot_passed_lists_every_reason(monkeypatch, tmp_path):
    world = run_world.install(monkeypatch, tmp_path)
    job_id = world.seed(SIX)
    for position in (1, 2, 3):
        world.checks[position] = [flagged_check()] * 4
    world.generate[4] = ["failed"] * 4
    world.generate[5] = [RuntimeError("boom")]
    world.generate[6] = ["refused", "refused"]

    finish(world, world.claim())

    row = world.job(job_id)
    assert (row["status"], row["stop_reason"]) == ("stopped", "no_shot_passed")
    reasons = {p: s["failure_reason"] for p, s in world.shots(job_id).items()}
    assert reasons == {
        1: "flagged_every_attempt",
        2: "flagged_every_attempt",
        3: "flagged_every_attempt",
        4: "provider_error",
        5: "provider_error",
        6: "refused",
    }
    assert world.assembled == []
    assert world.cuts == []


def _fail_assemble(world, monkeypatch, job_id):
    world.assemble_error = MediaError("ffmpeg: invalid data")


def _lose_song(world, monkeypatch, job_id):
    for key in [k for k in clip_stubs.BUCKET if k.startswith("songs/")]:
        del clip_stubs.BUCKET[key]


def _fail_put(world, monkeypatch, job_id):
    def put(key, path):
        raise OSError("bucket unavailable")

    monkeypatch.setattr(clip_stubs, "put", put)


def _refuse_finish(world, monkeypatch, job_id):
    def finish_job(*args, **kwargs):
        raise ValueError("A job is not finished while a shot is still being made")

    monkeypatch.setattr(worker_interface, "finish_job", finish_job)


@pytest.mark.parametrize(
    "break_it",
    [_fail_assemble, _lose_song, _fail_put, _refuse_finish],
    ids=["media_error", "song_missing", "bucket_write", "finish_refused"],
)
def test_assembly_failure_stops_the_job(monkeypatch, tmp_path, break_it):
    world = run_world.install(monkeypatch, tmp_path)
    job_id = world.seed(SIX)
    state = world.run_shots(world.claim())
    break_it(world, monkeypatch, job_id)

    run.finish_run(state, tmp_path / "finish" / "job")

    row = world.job(job_id)
    assert (row["status"], row["stop_reason"]) == ("stopped", "assembly_failed")
    for shot in world.shots(job_id).values():
        assert shot["status"] == "passed"
        assert shot["clip_key"] in clip_stubs.BUCKET
    assert world.cuts == []


def test_removed_shot_is_left_out(monkeypatch, tmp_path):
    world = run_world.install(monkeypatch, tmp_path)
    plan = [
        {"position": p, "length_s": p + 0.5, "removed": int(p == 5)} for p in (4, 2, 6, 1, 5, 3)
    ]
    plan[1].update(transition="crossfade", transition_s=0.5)
    job_id = world.seed(plan)

    finish(world, world.claim())

    assembled = world.assembled[0]
    assert assembled["contents"] == contents(1, 2, 3, 4, 6)
    assert assembled["clips"] == [
        {"lengthS": 1.5, "transition": "cut", "transitionS": 0.0},
        {"lengthS": 2.5, "transition": "crossfade", "transitionS": 0.5},
        {"lengthS": 3.5, "transition": "cut", "transitionS": 0.0},
        {"lengthS": 4.5, "transition": "cut", "transitionS": 0.0},
        {"lengthS": 6.5, "transition": "cut", "transitionS": 0.0},
    ]
    assert assembled["song"] == b"song"
    assert world.job(job_id)["status"] == "ready"


def test_cuts_are_recorded_after_finishing(monkeypatch, tmp_path):
    world = run_world.install(monkeypatch, tmp_path)
    job_id = world.seed(SIX)

    finish(world, world.claim())

    assert world.cuts == [(job_id, "ready")]


def test_a_failing_cut_check_never_fails_the_job(monkeypatch, tmp_path):
    world = run_world.install(monkeypatch, tmp_path)
    job_id = world.seed(SIX)

    def record_cuts(job_id):
        raise RuntimeError("detector crashed")

    monkeypatch.setattr(run.comparison, "record_cuts", record_cuts)

    finish(world, world.claim())

    assert world.job(job_id)["status"] == "ready"


def test_separate_runs_give_the_same_video(monkeypatch, tmp_path):
    plan = [{"position": p, "length_s": 4.0 + p / 2} for p in range(1, 7)]
    plan[3].update(transition="crossfade", transition_s=0.5)
    videos = []
    for name in ("single", "first", "second"):
        monkeypatch.setenv("DATABASE_PATH", str(tmp_path / f"{name}.db"))
        reset_settings()
        reset_engine()
        world = run_world.install(monkeypatch, tmp_path / name)
        job_id = world.seed(plan)
        world.checks[2] = [flagged_check()]
        world.checks[5] = [flagged_check()] * 4

        finish(world, world.claim())

        row = world.job(job_id)
        videos.append(
            {
                "assembled": world.assembled,
                "video": clip_stubs.BUCKET[row["video_key"]],
                "status": row["status"],
                "duration_s": row["video_duration_s"],
            }
        )

    assert videos[0]["status"] == "ready_with_failures"
    assert videos[0]["assembled"][0]["contents"] == contents(1, 2, 3, 4, 6)
    assert videos[1] == videos[0]
    assert videos[2] == videos[0]


def test_recut_only_export_reassembles(monkeypatch, tmp_path):
    world = run_world.install(monkeypatch, tmp_path)
    job_id = world.seed([{"position": 1, "length_s": 5.0}, {"position": 2}, {"position": 3}], 1)
    for position in (1, 2, 3):
        world.pass_shot(job_id, position)

    finish(world, world.claim())

    assert world.generated == []
    assembled = world.assembled[0]
    assert assembled["contents"] == contents(1, 2, 3)
    assert [c["lengthS"] for c in assembled["clips"]] == [5.0, 4.0, 4.0]
    row = world.job(job_id)
    assert (row["status"], row["video_version"]) == ("ready", 2)
    assert row["video_key"] == f"jobs/{job_id}/video-v2.mp4"
    assert clip_stubs.BUCKET[row["video_key"]] == b"|".join(contents(1, 2, 3))
