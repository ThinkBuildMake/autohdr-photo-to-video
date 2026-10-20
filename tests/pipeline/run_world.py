"""A seeded job driven through the run state: real Jobs tables, scripted clips, fake clock.

Jobs calls in clip_stubs go to the real Jobs interface; Files stay in clip_stubs.BUCKET;
generate_clip and check_clip are scripted per shot position; Media.assemble and
Comparison.record_cuts are recorded at their module boundaries.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from app.comparison import service as comparison
from app.db.base import session_scope
from app.jobs import shot_writes, worker_interface
from app.media import service as media
from app.pipeline import clip, clip_stubs, run
from app.providers.errors import ProviderError
from app.shared.enums import ProviderErrorKind
from app.shared.types import ClipResult, Job
from tests.pipeline.clip_world import passed_check
from tests.support.library_rows import add_song
from tests.support.worker_rows import add_job, add_shoot, rows

START = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)


@dataclass
class World:
    folder: Path
    now: datetime = START
    positions: dict[str, int] = field(default_factory=dict)
    generate: dict[int, list] = field(default_factory=dict)
    checks: dict[int, list] = field(default_factory=dict)
    clock_at_generate: dict[int, datetime] = field(default_factory=dict)
    generated: list[int] = field(default_factory=list)
    assembled: list[dict] = field(default_factory=list)
    assemble_error: Exception | None = None
    cuts: list[tuple[str, str]] = field(default_factory=list)
    _calls: dict[str, int] = field(default_factory=dict)

    def _next(self, script: dict[int, list], key: str, position: int, default):
        n = self._calls.get(f"{key}{position}", 0)
        self._calls[f"{key}{position}"] = n + 1
        items = script.get(position, [])
        return items[n] if n < len(items) else default

    def seed(self, shots: list[dict], video_version: int = 0) -> str:
        """A queued job. shots: [{position, length_s?, transition?, transition_s?, removed?}]."""
        song = add_song()
        clip_stubs.BUCKET[f"songs/{song}.mp3"] = b"song"
        shoot, _ = add_shoot(0)
        job = add_job(
            shoot, song, submitted_at="2026-10-19T09:59:00.000Z", video_version=video_version
        )
        for values in shots:
            shot = str(uuid.uuid4())
            self.positions[shot] = values["position"]
            with session_scope() as session:
                session.execute(
                    text(
                        "insert into job_shots (id,job_id,position,room,movement_name,"
                        "movement_prompt,model,length_s,transition,transition_s,removed)"
                        " values (:i,:j,:p,'living','dolly_in','m','google/veo-3.1',:l,:t,:ts,:rm)"
                    ),
                    {
                        "i": shot,
                        "j": job,
                        "p": values["position"],
                        "l": values.get("length_s", 4.0),
                        "t": values.get("transition", "cut"),
                        "ts": values.get("transition_s", 0.0),
                        "rm": values.get("removed", 0),
                    },
                )
        return job

    def pass_shot(self, job_id: str, position: int) -> None:
        """Mark a seeded shot passed with a final clip in the bucket, as an earlier run left it."""
        key = f"jobs/{job_id}/shots/{position}/r0/a1.mp4"
        clip_stubs.BUCKET[key] = f"clip-{position}".encode()
        shot = rows(
            "select id from job_shots where job_id = :j and position = :p", j=job_id, p=position
        )[0]["id"]
        attempt = str(uuid.uuid4())
        with session_scope() as session:
            session.execute(
                text(
                    "insert into attempts (id,job_shot_id,round,attempt_no,prompt,model,"
                    "requested_s,status,clip_key,started_at)"
                    " values (:a,:s,0,1,'p','google/veo-3.1',4,'passed',:k,'2026-10-19T09:00:00Z')"
                ),
                {"a": attempt, "s": shot, "k": key},
            )
            session.execute(
                text("update job_shots set status='passed', final_attempt_id=:a where id=:s"),
                {"a": attempt, "s": shot},
            )

    def claim(self) -> Job:
        job = worker_interface.claim_next_job()
        assert job is not None
        return job

    def run_shots(self, job: Job) -> run.Run:
        """The shot loop the runner (S12, wired in S22) drives: prepare, then make_clip."""
        state = run.Run.for_job(job)
        for shot in job.shots:
            state.run_shot(shot.id, lambda shot=shot: self._make(job, shot, state))
        return state

    def _make(self, job: Job, shot, state: run.Run) -> None:
        clip_stubs.set_shot_state(shot.id, "editing", "Preparing the photo")
        folder = self.folder / str(shot.position)
        folder.mkdir(parents=True, exist_ok=True)
        clip.make_clip(
            job.id, shot, 0, b"jpeg", "prompt", shot.length_s, folder, has_time=state.has_time
        )

    def job(self, job_id: str) -> dict:
        return rows("select * from jobs where id = :i", i=job_id)[0]

    def shots(self, job_id: str) -> dict[int, dict]:
        found = rows(
            "select s.*, a.clip_key from job_shots s left join attempts a"
            " on a.id = s.final_attempt_id where s.job_id = :j",
            j=job_id,
        )
        return {r["position"]: r for r in found}


def _error(item) -> Exception:
    if isinstance(item, Exception):
        return item
    return ProviderError(ProviderErrorKind(item), f"scripted {item}")


def install(monkeypatch, tmp_path) -> World:
    world = World(folder=tmp_path / "job")
    monkeypatch.setattr(shot_writes, "now_utc", lambda: world.now)
    monkeypatch.setattr(run, "now_utc", lambda: world.now)
    for name in ("set_shot_state", "start_attempt", "finish_attempt", "set_shot_result"):
        monkeypatch.setattr(clip_stubs, name, getattr(worker_interface, name))

    def generate_clip(first_frame_jpeg, prompt, model, length_s, ids):
        position = world.positions[ids["jobShotId"]]
        world.generated.append(position)
        if position in world.clock_at_generate:
            world.now = world.clock_at_generate.pop(position)
        step = world._next(world.generate, "generate", position, None)
        if step is not None:
            raise _error(step)
        path = world.folder / f"generated-{uuid.uuid4()}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"clip-{position}".encode())
        return ClipResult(
            path=str(path),
            seconds=length_s,
            model=model,
            cost_usd=0.0,
            cost_source="reported",
            provider_request_id=None,
        )

    def check_clip(clip_path, frames, source_jpeg, ids):
        position = world.positions[ids["jobShotId"]]
        return world._next(world.checks, "check", position, passed_check())

    def assemble(clips, song_path, song_offset_s, out_path, width, height, fps):
        if world.assemble_error is not None:
            raise world.assemble_error
        contents = [Path(c["path"]).read_bytes() for c in clips]
        world.assembled.append(
            {
                "clips": [{k: v for k, v in c.items() if k != "path"} for c in clips],
                "contents": contents,
                "song": Path(song_path).read_bytes(),
                "size": (width, height, fps),
            }
        )
        Path(out_path).write_bytes(b"|".join(contents))
        return {"durationS": sum(c["lengthS"] for c in clips)}

    def record_cuts(job_id):
        world.cuts.append((job_id, world.job(job_id)["status"]))

    monkeypatch.setattr(clip_stubs, "generate_clip", generate_clip)
    monkeypatch.setattr(clip_stubs, "check_clip", check_clip)
    monkeypatch.setattr(clip_stubs, "extract_frames", lambda clip_path, per_second: [])
    monkeypatch.setattr(clip, "_wait", lambda seconds: None)
    monkeypatch.setattr(media, "assemble", assemble)
    monkeypatch.setattr(comparison, "record_cuts", record_cuts)
    clip_stubs.BUCKET.clear()
    return world


def at(minutes: float) -> datetime:
    return START + timedelta(minutes=minutes)
