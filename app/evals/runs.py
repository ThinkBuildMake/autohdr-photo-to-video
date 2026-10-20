"""evals run: create and submit a suite's jobs, wait for them, write the reviewer sheet."""

import csv
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.db.base import session_scope
from app.db.schema import init_db
from app.evals import stubs
from app.evals.report import write_report
from app.evals.shoots import SHOOTS_FILE
from app.files import service as files
from app.jobs.models import Attempt, Job, JobShot
from app.jobs.schemas import JobCreate
from app.library import service as library

FINISHED = {"ready", "ready_with_failures", "stopped"}
POLL_S = 30
SHEET_FILE = "sheet.csv"
JUDGMENTS = ["visibly_ai", "room_changed", "movement_matches", "transition_matches"]
COLUMNS = [
    "kind",
    "video",
    "shoot",
    "style",
    "job_id",
    "position",
    "attempt",
    "flagged",
    "in_video",
    "clip_link",
    *JUDGMENTS,
    "text_followed",
    "looks_like_reference",
]


@dataclass(frozen=True)
class RunJob:
    video: int
    shoot: str
    job_id: str


def _style(name: str):
    for summary in library.list_styles():
        if summary.name == name:
            return library.get_style(summary.id)
    raise SystemExit(f"No style named {name!r}.")


def _wait(job_ids: list[str]) -> None:
    """Until every job is finished; a job with no row (the stub's) counts as finished."""
    while True:
        with session_scope() as session:
            statuses = dict(
                session.execute(select(Job.id, Job.status).where(Job.id.in_(job_ids))).all()
            )
        if all(statuses.get(job_id, "stopped") in FINISHED for job_id in job_ids):
            return
        time.sleep(POLL_S)


def _yes(value: bool) -> str:
    return "yes" if value else "no"


def _attempt_rows(base: dict) -> list[dict]:
    """One row per attempt that made a clip, flagged ones included."""
    with session_scope() as session:
        found = session.execute(
            select(
                JobShot.position,
                JobShot.status.label("shot_status"),
                JobShot.removed,
                JobShot.final_attempt_id,
                Attempt.id,
                Attempt.attempt_no,
                Attempt.status,
                Attempt.clip_key,
            )
            .join(Attempt, Attempt.job_shot_id == JobShot.id)
            .where(JobShot.job_id == base["job_id"], Attempt.clip_key.is_not(None))
            .order_by(JobShot.position, Attempt.round, Attempt.attempt_no)
        ).all()
    return [
        {
            **base,
            "kind": "attempt",
            "position": row.position,
            "attempt": row.attempt_no,
            "flagged": _yes(row.status == "flagged"),
            "in_video": _yes(
                row.final_attempt_id == row.id and row.shot_status == "passed" and not row.removed
            ),
            "clip_link": files.presign_download(row.clip_key),
        }
        for row in found
    ]


def run_suite(suite: str, style_name: str, out: Path) -> Path:
    """Returns the new run folder."""
    init_db()
    style = _style(style_name)
    shoots_file = out / SHOOTS_FILE
    if not shoots_file.exists():
        raise SystemExit(f"No {shoots_file}: run `evals import --out {out}` first.")
    shoots = json.loads(shoots_file.read_text())
    purpose = "video" if suite == "ev1" else "reproduction"
    if suite == "ev2":
        shoots = {k: v for k, v in shoots.items() if v != style.demo_photoshoot_id}
        shoots = dict(list(shoots.items())[:2])
    jobs = []
    for video, (label, photoshoot_id) in enumerate(shoots.items(), start=1):
        job_id = stubs.create_job(
            JobCreate(
                photoshoot_id=photoshoot_id,
                style_text=style.style_text,
                song_id=style.song.id,
                style_id=style.id,
                purpose=purpose,
            )
        )
        stubs.submit_job(job_id)
        jobs.append(RunJob(video, label, job_id))
    _wait([job.job_id for job in jobs])
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder = out / f"{suite}-{stamp}"
    folder.mkdir(parents=True)
    with session_scope() as session:
        video_keys = dict(
            session.execute(
                select(Job.id, Job.video_key).where(Job.id.in_([job.job_id for job in jobs]))
            ).all()
        )
    rows = []
    for job in jobs:
        base = {"video": job.video, "shoot": job.shoot, "style": style.name, "job_id": job.job_id}
        key = video_keys.get(job.job_id)
        video = {**base, "clip_link": files.presign_download(key) if key else ""}
        rows.append({**video, "kind": "plan"})
        if purpose == "reproduction":
            rows.append({**video, "kind": "reproduction"})
        rows += _attempt_rows(base)
    with open(folder / SHEET_FILE, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, restval="")
        writer.writeheader()
        writer.writerows(rows)
    write_report(folder / SHEET_FILE)
    return folder
