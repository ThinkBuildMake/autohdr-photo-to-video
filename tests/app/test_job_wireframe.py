import pytest

from app.shared.enums import JobStatus, ShotStatus, StopReason
from tests.support.job_screens import JOB_A, job, shot, stub_jobs  # noqa: F401


def test_job_property_and_photo_pair(client, stub_jobs):  # noqa: F811
    stub_jobs.add(
        job(
            photoshoot_label="Oak house",
            photo_count=28,
            shots=[
                shot(
                    1,
                    photo_url="https://bucket/original.jpg?signature=abc",
                    first_frame_url="https://bucket/edited.jpg?signature=def",
                )
            ],
        )
    )
    html = client.get(f"/jobs/{JOB_A}").text
    assert "Oak house, 28 photos · Style:" in html
    assert 'alt="Your photo" src="https://bucket/original.jpg?signature=abc"' in html
    assert 'alt="Edited first frame" src="https://bucket/edited.jpg?signature=def"' in html


def test_partial_banner_precedes_player_and_keeps_reasons(client, stub_jobs):  # noqa: F811
    stub_jobs.add(
        job(
            status=JobStatus.ready_with_failures,
            shots=[
                shot(
                    2,
                    status=ShotStatus.failed,
                    failure_reason="provider_error",
                    status_detail="Service down",
                )
            ],
        )
    )
    html = client.get(f"/jobs/{JOB_A}").text
    assert html.index("failures") < html.index("card player")
    assert "Shot 2</strong>" in html
    assert "The video service returned an error: Service down" in html


@pytest.mark.parametrize("status", [JobStatus.queued, JobStatus.stopped, JobStatus.ready])
def test_job_state_copy(client, stub_jobs, status):  # noqa: F811
    stub_jobs.add(
        job(
            status=status,
            waiting_behind="running-job",
            waiting_behind_label="Condo",
            stop_reason=StopReason.out_of_credit,
            shots=[
                shot(1),
                shot(2, status=ShotStatus.failed, failure_reason="provider_error"),
                shot(4),
            ],
        )
    )
    html = client.get(f"/jobs/{JOB_A}").text
    if status == JobStatus.queued:
        assert "Waiting: another video is being made" in html
        assert "Estimated wait:" in html
        assert "Yours starts as soon as the Condo video finishes" in html
    elif status == JobStatus.stopped:
        assert "Shots 1 and 4 are finished and kept." in html
    else:
        assert "demo use only" in html
        assert "Took 5 min. Watch it before you send it to the agent." in html


def test_crop_only_pair_has_reason(client, stub_jobs):  # noqa: F811
    stub_jobs.add(
        job(
            shots=[
                shot(
                    1,
                    edit_status="crop_only",
                    edit_note="Changed a window",
                    first_frame_url="https://bucket/crop.jpg",
                )
            ]
        )
    )
    html = client.get(f"/jobs/{JOB_A}").text
    assert 'alt="Crop-only first frame" src="https://bucket/crop.jpg"' in html
    assert "crop only): Changed a window" in html


def test_partly_failed_job_also_says_how_long_it_took(client, stub_jobs):  # noqa: F811
    stub_jobs.add(
        job(
            status=JobStatus.ready_with_failures,
            shots=[shot(1), shot(2, status=ShotStatus.failed, failure_reason="provider_error")],
        )
    )
    html = client.get(f"/jobs/{JOB_A}").text
    assert "Your video is ready" in html
    assert "Took 5 min." in html
    assert "Ready, with 1 shot that did not work" in html
