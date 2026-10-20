import logging

import pytest

from app.comparison import service, stubs
from tests.support.comparison_rows import add_job, add_shot, add_shots, cut_rows, job_status
from tests.support.library_rows import add_song


@pytest.fixture
def job():
    return add_job(add_song())


@pytest.fixture
def detector(monkeypatch):
    """The stub cut detector: set detector.cuts, or detector.error to make it raise."""

    class Detector:
        cuts: list[float] = []
        error: Exception | None = None

    def detect(video_key):
        if Detector.error:
            raise Detector.error
        return Detector.cuts

    monkeypatch.setattr(stubs, "detect_cuts", detect)
    return Detector


def test_cuts_are_measured_against_the_plan(job, detector):
    add_shots(job, [3.0, 2.5, 3.5])
    detector.cuts = [3.04, 5.47]

    service.record_cuts(job)

    rows = cut_rows(job)
    assert [(r["position"], r["expected_s"]) for r in rows] == [(2, 3.0), (3, 5.5)]
    assert [r["detected_s"] for r in rows] == [3.04, 5.47]
    assert [r["error_s"] for r in rows] == [0.04, -0.03]
    assert [r["transition"] for r in rows] == ["cut", "cut"]


@pytest.mark.parametrize("left_out", [{"status": "failed"}, {"removed": 1}])
def test_left_out_shot_moves_the_expected_cut(job, detector, left_out):
    add_shot(job, 1, 3.0)
    add_shot(job, 2, 2.5, **left_out)
    add_shot(job, 3, 3.5)
    detector.cuts = [3.0]

    service.record_cuts(job)

    rows = cut_rows(job)
    assert [(r["position"], r["expected_s"]) for r in rows] == [(3, 3.0)]


@pytest.mark.parametrize("cuts, error", [([5.47], None), ([], RuntimeError("no ffmpeg"))])
def test_missed_cut_is_recorded_and_job_stays_ready(job, detector, cuts, error):
    add_shots(job, [3.0, 2.5, 3.5])
    detector.cuts, detector.error = cuts, error

    service.record_cuts(job)

    first = cut_rows(job)[0]
    assert first["expected_s"] == 3.0
    assert first["detected_s"] is None
    assert first["error_s"] is None
    assert job_status(job) == "ready"


def test_detector_failure_is_logged(job, detector, caplog):
    add_shots(job, [3.0, 3.0])
    detector.error = RuntimeError("no ffmpeg")

    with caplog.at_level(logging.WARNING):
        service.record_cuts(job)

    [record] = [r for r in caplog.records if r.name == "app.comparison.service"]
    assert record.levelno == logging.WARNING
    assert job in record.getMessage() and "RuntimeError" in record.getMessage()
    assert cut_rows(job)[0]["detected_s"] is None
    assert job_status(job) == "ready"


def test_rechecking_replaces_the_rows(job, detector):
    add_shots(job, [3.0, 2.5, 3.5])
    detector.cuts = [3.04, 5.47]
    service.record_cuts(job)
    detector.cuts = [3.01, 5.52]

    service.record_cuts(job)

    rows = cut_rows(job)
    assert [r["position"] for r in rows] == [2, 3]
    assert [r["detected_s"] for r in rows] == [3.01, 5.52]


def test_one_detected_cut_matches_one_expected_cut(job, detector):
    add_shots(job, [3.0, 0.4, 3.0])
    detector.cuts = [3.0]

    service.record_cuts(job)

    rows = cut_rows(job)
    assert [(r["expected_s"], r["detected_s"], r["error_s"]) for r in rows] == [
        (3.0, 3.0, 0.0),
        (3.4, None, None),
    ]


def test_cut_off_by_more_than_the_limit_is_recorded(job, detector):
    add_shots(job, [3.0, 3.0])
    detector.cuts = [3.3]

    service.record_cuts(job)

    assert cut_rows(job)[0]["error_s"] == 0.3
