"""Pipeline: runs the next queued job. Stub until S12."""

from app.jobs import worker_interface


def run_next_job() -> bool:
    """Returns True when a job was run, False when there was nothing to do."""
    job = worker_interface.claim_next_job()
    if job is None:
        return False
    raise NotImplementedError("Running a job is built in S12.")
