"""Real storage and job reads behind the public Comparison interface."""

import subprocess

import pytest
import requests

from app.comparison import service
from app.files import service as files
from app.jobs.reading import load_job
from app.library import service as library
from tests.support.comparison_rows import add_cut_check, add_job, add_shot, add_shots
from tests.support.library_rows import stub_presets  # noqa: F401
from tests.support.stub_data import GOLDEN_HOUR_ID, STUB_SONG_ID, STUB_STYLES

pytestmark = pytest.mark.usefixtures("stub_presets")


def test_both_video_links_resolve_to_their_stored_job_outputs(bucket, tmp_path):
    job_ids, outputs = [], []
    for color in ("red", "blue"):
        job_id = add_job(
            STUB_SONG_ID, style_id=GOLDEN_HOUR_ID, style_text=STUB_STYLES[0].style_text
        )
        video = tmp_path / f"{color}.mp4"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-v", "error", "-y",
                "-f", "lavfi", "-i", f"color={color}:s=160x90:r=30:d=0.2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
            ],
            check=True,
            capture_output=True,
        )  # fmt: skip
        files.put(f"jobs/{job_id}/video-v1.mp4", str(video))
        job_ids.append(job_id)
        outputs.append(video.read_bytes())
    library.set_reference_job(GOLDEN_HOUR_ID, job_ids[0])

    comparison = service.get_reproduction(GOLDEN_HOUR_ID, job_ids[1])

    assert outputs[0] != outputs[1]
    for side, job_id, expected in zip(
        (comparison.reference, comparison.reproduction), job_ids, outputs, strict=True
    ):
        response = requests.get(side.video_url, timeout=10)
        assert response.status_code == 200
        assert response.content == expected
        job = load_job(job_id)
        assert requests.get(job.video.url, timeout=10).content == expected


@pytest.mark.parametrize("measurement", ["measured", "missing", "detector_failure"])
def test_unequal_plans_keep_separate_signed_errors_and_unknown_measurements(bucket, measurement):
    reference = add_job(STUB_SONG_ID)
    reproduction = add_job(STUB_SONG_ID, status="ready_with_failures", style_id=GOLDEN_HOUR_ID)
    library.set_reference_job(GOLDEN_HOUR_ID, reference)
    add_shots(reference, [2.0, 3.0, 4.0])
    add_shot(reproduction, 1, 1.0)
    add_shot(reproduction, 2, 2.5, movement="crane_up", transition="crossfade")
    if measurement == "measured":
        add_cut_check(reference, 2, 2.0, 1.88)
        add_cut_check(reference, 3, 5.0, 5.04)
        add_cut_check(reproduction, 2, 1.0, 1.1)
    elif measurement == "missing":
        add_cut_check(reference, 2, 2.0, None)
        add_cut_check(reproduction, 2, 1.0, None)
    else:
        # Missing bucket objects exercise the real detector failure path.
        service.record_cuts(reference)
        service.record_cuts(reproduction)

    comparison = service.get_reproduction(GOLDEN_HOUR_ID, reproduction)

    assert [row.position for row in comparison.shots] == [1, 2, 3]
    assert comparison.summary.reference.shot_count == 3
    assert comparison.summary.reference.total_s == 9.0
    assert comparison.summary.reproduction.shot_count == 2
    assert comparison.summary.reproduction.total_s == 3.5
    assert comparison.summary.reference.movements == {"dolly_in": 3}
    assert comparison.summary.reproduction.movements == {"dolly_in": 1, "crane_up": 1}
    assert comparison.summary.reference.transitions == {"cut": 2}
    assert comparison.summary.reproduction.transitions == {"crossfade": 1}
    assert comparison.shots[1].reference.length_s == 3.0
    assert comparison.shots[1].reproduction.length_s == 2.5
    assert comparison.shots[2].reproduction is None
    assert comparison.shots[0].reference.cut_error_s is None
    assert comparison.shots[0].reproduction.cut_error_s is None
    if measurement == "measured":
        ref_errors = [row.reference.cut_error_s for row in comparison.shots]
        rep_errors = [row.reproduction.cut_error_s for row in comparison.shots[:2]]
        assert ref_errors == [None, -0.12, 0.04]
        assert rep_errors == [None, 0.1]
        assert max(abs(e) for e in ref_errors if e is not None) == 0.12
        assert max(abs(e) for e in rep_errors if e is not None) == 0.1
        assert comparison.max_cut_error_s == 0.12
    else:
        assert comparison.max_cut_error_s is None
        assert all(
            timing.cut_error_s is None
            for row in comparison.shots
            for timing in (row.reference, row.reproduction)
            if timing is not None
        )
