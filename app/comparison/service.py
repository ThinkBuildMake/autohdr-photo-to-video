"""Comparison module interface. Stub until S13."""

from app.comparison import stubs
from app.comparison.schemas import Reproduction
from app.errors import AppError
from app.jobs import queue
from app.library import service as library
from app.shared.types import Style


def set_reference(style_id: str, job_id: str) -> Style:
    library.get_style(style_id)
    queue.get_job(job_id)
    library.set_reference_job(style_id, job_id)
    return library.get_style(style_id)


def get_reproduction(style_id: str, job_id: str) -> Reproduction:
    style = library.get_style(style_id)
    queue.get_job(job_id)
    if style.reference_job_id is None:
        raise AppError(409, "no_reference", "This style has no reference video yet.")
    return stubs.stub_reproduction(style.reference_job_id, job_id)


def record_cuts(job_id: str) -> None:
    """S13 detects the cuts in the job's video and replaces its cut_checks rows."""
    return None
