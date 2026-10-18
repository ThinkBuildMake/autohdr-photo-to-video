"""Jobs errors."""

from app.errors import AppError


class JobNotFound(AppError):
    def __init__(self, job_id: str):
        super().__init__(404, "job_not_found", f"No job with id {job_id}.")


class AttemptLimitReached(Exception):
    """startAttempt was called after attempt 4 of the shot's current round (QC-2)."""


class JobNotRunning(Exception):
    """A worker write arrived after the job stopped running."""
