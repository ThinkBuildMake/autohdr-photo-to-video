"""Real Files and Media seams for completed-job cut checks."""

import logging
import subprocess

import pytest

from app.comparison import service
from app.files import service as files
from tests.support.comparison_rows import add_job, add_shots, cut_rows, job_status
from tests.support.library_rows import add_song


@pytest.mark.parametrize("fps", [24, 30])
def test_real_video_cuts_are_present_and_within_plan_tolerance(bucket, tmp_path, fps):
    video = tmp_path / "cuts.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"color=red:s=320x180:r={fps}:d=1",
            "-f", "lavfi", "-i", f"color=blue:s=320x180:r={fps}:d=1.5",
            "-f", "lavfi", "-i", f"color=green:s=320x180:r={fps}:d=1",
            "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[out]",
            "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip
    key = "jobs/synthetic/video-v1.mp4"
    files.put(key, str(video))
    job = add_job(add_song(), video_key=key)
    add_shots(job, [1.0, 1.5, 1.0])

    service.record_cuts(job)

    rows = cut_rows(job)
    assert [(r["position"], r["expected_s"]) for r in rows] == [(2, 1.0), (3, 2.5)]
    assert all(r["detected_s"] is not None for r in rows)
    assert [r["detected_s"] for r in rows] == pytest.approx([1.0, 2.5], abs=0.1)
    assert all(abs(r["error_s"]) <= 0.1 for r in rows)
    service.record_cuts(job)
    assert [
        {key: value for key, value in row.items() if key != "checked_at"} for row in cut_rows(job)
    ] == [{key: value for key, value in row.items() if key != "checked_at"} for row in rows]
    assert job_status(job) == "ready"


@pytest.mark.parametrize("object_exists", [False, True])
def test_download_or_detection_failure_keeps_null_rows_and_ready_job(
    bucket, tmp_path, caplog, object_exists
):
    key = "jobs/synthetic/broken.mp4"
    if object_exists:
        invalid = tmp_path / "broken.mp4"
        invalid.write_bytes(b"synthetic invalid video")
        files.put(key, str(invalid))
    job = add_job(add_song(), video_key=key)
    add_shots(job, [1.0, 1.5, 1.0])

    with caplog.at_level(logging.WARNING):
        service.record_cuts(job)

    rows = cut_rows(job)
    assert len(rows) == 2
    assert all(r["detected_s"] is None and r["error_s"] is None for r in rows)
    assert job_status(job) == "ready"
    assert any(r.name == "app.comparison.service" and job in r.getMessage() for r in caplog.records)
