"""Editor HTTP mutations through real worker, provider adapters and decoded output."""

from collections import Counter
from datetime import datetime, timedelta

import pytest

from app.media import service as media
from app.pipeline import runner
from tests.pipeline.editor_reexport_world import RGB
from tests.pipeline.editor_reexport_world import editor_world as editor_world  # noqa: F401
from tests.support.worker_rows import rows


def nearest(frame, palette):
    return min(
        palette, key=lambda key: sum((a - b) ** 2 for a, b in zip(frame, palette[key], strict=True))
    )


def assert_reused(world, positions):
    shots = world.shots()
    attempts = world.attempts()
    for position in positions:
        old = world.old_shots[position - 1]
        assert shots[position - 1] == old
        old_attempts = [a for a in world.old_attempts if a["job_shot_id"] == old["id"]]
        assert [a for a in attempts if a["job_shot_id"] == old["id"]] == old_attempts
        for attempt in old_attempts:
            assert world.digest(attempt["clip_key"]) == world.old_objects[attempt["clip_key"]]


def test_only_changed_shots_are_generated_and_output_reuses_untouched_clips(editor_world):
    world = editor_world
    world.edit(1, lengthS=2)
    world.edit(2, photoId=world.photos[6])
    world.edit(3, movementName="crane_up")
    world.edit(5, removed=True)
    job = world.export(overlap=True)

    assert Counter(world.api.generated) == {2: 1, 3: 1}
    assert Counter(world.api.checked) == {"white": 1, "orange": 1}
    assert world.api.plans == 1
    new_calls = [c for c in world.calls() if c["id"] not in {c["id"] for c in world.old_calls}]
    assert Counter(c["kind"] for c in new_calls) == {"generate_clip": 2, "check_clip": 2}
    assert {c["job_shot_id"] for c in new_calls} == {world.old_shots[i]["id"] for i in (1, 2)}
    assert all(c["status"] == "ok" for c in new_calls)
    assert_reused(world, [4, 6])
    for position in [2, 3]:
        assert (
            world.shots()[position - 1]["final_attempt_id"]
            != world.old_shots[position - 1]["final_attempt_id"]
        )
    palette = {1: RGB[0], 2: (255, 255, 255), 3: RGB[6], 4: (0, 0, 0), 5: RGB[4], 6: RGB[5]}
    # Literal oracle: shot 1 is two seconds, shots 2/3/4/6 four each; 5 is absent.
    assert [nearest(frame, palette) for frame in world.frames] == (
        [1] * 60 + [2] * 120 + [3] * 120 + [4] * 120 + [6] * 120
    )
    assert (world.probe["width"], world.probe["height"], world.probe["fps"]) == (1920, 1080, 30)
    assert world.probe["durationS"] == pytest.approx(18, abs=1 / 30)
    cuts = rows("select * from cut_checks where job_id=:j order by position", j=world.job_id)
    assert [c["position"] for c in cuts] == [2, 3, 4, 6]
    assert [c["expected_s"] for c in cuts] == [2, 6, 10, 14]
    detected = media.detect_cuts(str(world.folder / "playable.mp4"))
    assert detected == pytest.approx([2, 6, 10, 14], abs=0.1)
    for cut, boundary in zip(cuts, [2, 6, 10, 14], strict=True):
        assert cut["detected_s"] is not None
        assert abs(cut["detected_s"] - boundary) <= 0.1
        assert abs(cut["error_s"]) <= 0.1
    assert job["video_version"] == world.old_job["video_version"] + 1
    assert job["video_key"] != world.old_job["video_key"]
    assert world.digest(world.old_job["video_key"]) == world.old_video_hash
    assert world.digest(job["video_key"]) != world.old_video_hash
    assert job["first_submitted_at"] == world.old_job["first_submitted_at"]
    assert job["first_finished_at"] == world.old_job["first_finished_at"]
    submitted = datetime.fromisoformat(job["submitted_at"])
    started = datetime.fromisoformat(job["started_at"])
    finished = datetime.fromisoformat(job["finished_at"])
    # Stored times have millisecond precision.
    tolerance = timedelta(milliseconds=1)
    assert world.clicked - tolerance <= submitted <= world.accepted
    assert world.accepted - tolerance <= started <= finished <= world.playable
    assert 0 <= (world.playable - world.clicked).total_seconds() <= 600
    print(
        "generated=2,3 concurrently; reused=4,6 byte-for-byte; output=1,2,3,4,6; "
        "cuts=2,6,10,14 within 0.1s; old/new videos readable; mocked playback <=600s"
    )


def test_recut_only_and_restore_keep_old_clips_without_paid_calls(editor_world):
    world = editor_world
    world.edit(5, removed=True)
    world.edit(5, removed=False)
    world.edit(1, lengthS=2)
    world.export()
    assert world.api.generated == []
    assert world.api.checked == []
    assert world.calls() == world.old_calls
    assert world.api.plans == 1
    assert_reused(world, [2, 3, 4, 5, 6])
    palette = {i + 1: RGB[i] for i in range(6)}
    palette[4] = (0, 0, 0)
    assert [nearest(frame, palette) for frame in world.frames] == (
        [1] * 60 + [2] * 120 + [3] * 120 + [4] * 120 + [5] * 120 + [6] * 120
    )
    print(
        "remove/restore 5: original attempt/key/bytes retained; output=1,2,3,4,5,6; "
        "re-cut generated=0 checked=0 replanned=0"
    )


def test_fast_shot_is_remade_and_crossfade_is_visible_in_decoded_output(editor_world):
    world = editor_world
    world.edit(6, speed="fast", transition="crossfade", transitionS=0.4)
    world.export()
    assert world.api.generated == [6]
    assert world.api.checked == ["cyan"]
    assert "Camera speed: fast." in world.api.prompts[0]["prompt"]
    assert world.api.prompts[0]["duration"] == 6
    attempt = world.attempts()[-1]
    assert "Camera speed: fast." in attempt["prompt"]
    assert attempt["id"] != world.old_shots[5]["final_attempt_id"]
    assert_reused(world, [1, 2, 3, 4, 5])
    # Crossfade enters shot 6 over [19.6,20.0): magenta -> cyan. At its midpoint,
    # red and green must both be present; either hard-cut endpoint fails this oracle.
    before, middle, after = [world.frames[round(t * 30)] for t in (19.5, 19.8, 20.1)]
    assert nearest(before, {5: RGB[4], 6: RGB[5]}) == 5
    assert 60 < middle[0] < 200 and 60 < middle[1] < 200 and middle[2] > 220
    assert nearest(after, {5: RGB[4], 6: RGB[5]}) == 6
    assert len(world.frames) == 720
    assert world.probe["durationS"] == pytest.approx(24, abs=1 / 30)
    print(f"shot6 prompt=fast requested=6s; fade RGB before={before} middle={middle} after={after}")


def test_invalid_and_busy_mutations_are_atomic_and_make_no_provider_calls(editor_world):
    world = editor_world
    before = (world.job(), world.shots(), world.attempts(), world.calls())
    response = world.client.patch(
        f"/api/jobs/{world.job_id}/shots/2", json={"lengthS": -1, "photoId": world.photos[6]}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_edit"
    assert (world.job(), world.shots(), world.attempts(), world.calls()) == before
    world.edit(2, photoId=world.photos[6])
    queued = world.client.post(f"/api/jobs/{world.job_id}/export")
    assert queued.status_code == 202

    def assert_busy():
        before = (world.job(), world.shots(), world.attempts(), world.calls())
        for response in [
            world.client.post(f"/api/jobs/{world.job_id}/export"),
            world.client.patch(f"/api/jobs/{world.job_id}/shots/1", json={"lengthS": 2}),
        ]:
            assert response.status_code == 409
            assert response.json()["error"] == "job_busy"
        assert (world.job(), world.shots(), world.attempts(), world.calls()) == before

    assert_busy()
    assert world.api.generated == world.api.checked == []
    running_checked = []

    def during_generation():
        assert world.job()["status"] == "running"
        assert_busy()
        running_checked.append(True)

    world.api.on_generate = during_generation
    assert runner.run_next_job()
    assert running_checked == [True]
    assert world.api.generated == [2]
    assert world.api.checked == ["white"]
    assert world.api.plans == 1
    print(
        "invalid edit=400 atomic; queued/running edit/export=409 atomic; only accepted shot2 paid"
    )
