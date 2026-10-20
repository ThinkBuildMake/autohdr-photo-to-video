"""Stand-ins Evals borrows until S26 removes them.

import_photoshoot (Photoshoots.importPhotoshoot), create_job and submit_job (Jobs.createJob,
submitJob). They answer with new ids and touch no table; S26 calls the real modules.
"""

import uuid
from collections.abc import Sequence

from app.jobs.schemas import JobCreate


def import_photoshoot(paths: Sequence[str], label: str) -> str:
    return str(uuid.uuid4())


def create_job(body: JobCreate) -> str:
    return str(uuid.uuid4())


def submit_job(job_id: str) -> None:
    return None
