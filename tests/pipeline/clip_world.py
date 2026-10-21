"""The scripted world make_clip runs in: external boundaries scripted, time faked."""

import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

from app.files import service as files
from app.jobs import worker_interface as jobs
from app.media import service as media
from app.pipeline import clip
from app.providers import interface as providers
from app.providers.errors import ProviderError
from app.shared.enums import ProviderErrorKind
from app.shared.types import ClipCheck, ClipResult, JobShot

BUCKET = {}


def passed_check() -> ClipCheck:
    return ClipCheck(
        ai_score=0.1,
        match_score=0.95,
        people_count=0,
        added_objects=[],
        removed_objects=[],
        changed_objects=[],
        passed=True,
        notes="looks real",
    )


def flagged_check(notes: str = "looks AI-made", ai_score: float = 0.8) -> ClipCheck:
    return passed_check().model_copy(
        update={"passed": False, "ai_score": ai_score, "match_score": 0.4, "notes": notes}
    )


def shot_id(position: int) -> str:
    return f"99999999-9999-4999-8999-99999999990{position}"


def make_shot(position: int, **overrides) -> JobShot:
    values = dict(
        id=shot_id(position),
        position=position,
        room="living",
        movement_name="push in",
        movement_prompt="Slow push in",
        speed="slow",
        photo_edit_prompts=[],
        length_s=4.0,
        transition="cut",
        transition_s=0.0,
        photo_id=f"88888888-8888-4888-8888-88888888880{position}",
        removed=False,
        pending_change="none",
        plan_note="",
        edit_status=None,
        edit_note=None,
        model="google/veo-3.1",
        used_fallback=False,
        status="pending",
        status_detail="",
        failure_reason=None,
        attempts=0,
        clip_url=None,
    )
    values.update(overrides)
    return JobShot(**values)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0


@dataclass
class ClipWorld:
    clock: FakeClock = field(default_factory=FakeClock)
    events: list[tuple[str, dict, float]] = field(default_factory=list)
    generate: dict[str, list] = field(default_factory=dict)
    checks: dict[str, list] = field(default_factory=dict)
    frame_errors: dict[str, list] = field(default_factory=dict)
    clip_paths: list[str] = field(default_factory=list)
    current_shot: threading.local = field(default_factory=threading.local)
    lock: threading.Lock = field(default_factory=threading.Lock)
    _shots: dict[str, int] = field(default_factory=dict)
    _attempt_shot: dict[str, str] = field(default_factory=dict)
    _calls: dict[str, int] = field(default_factory=dict)

    def record(self, name: str, **args) -> None:
        with self.lock:
            self.events.append((name, args, self.clock.now))

    def named(self, name: str, shot_id: str | None = None) -> list[dict]:
        with self.lock:
            return [
                args
                for n, args, _ in self.events
                if n == name and (shot_id is None or args.get("shot") == shot_id)
            ]

    def attempts(self, shot_id: str) -> list[dict]:
        return self.named("start_attempt", shot_id)

    def result(self, shot_id: str) -> dict | None:
        results = self.named("set_shot_result", shot_id)
        return results[-1] if results else None

    def details(self, shot_id: str) -> list[tuple[str, str]]:
        return [(a["status"], a["detail"]) for a in self.named("set_shot_state", shot_id)]

    def finishes(self, shot_id: str | None = None) -> list[dict]:
        with self.lock:
            return [
                args
                for n, args, _ in self.events
                if n == "finish_attempt"
                and (shot_id is None or self._attempt_shot.get(args["attempt_id"]) == shot_id)
            ]

    def names(self) -> list[str]:
        with self.lock:
            return [n for n, _, _ in self.events]

    def _next(self, script: dict[str, list], key: str, default):
        index = self._calls.get(f"{key}:{id(script)}", 0)
        self._calls[f"{key}:{id(script)}"] = index + 1
        items = script.get(key, [])
        return items[index] if index < len(items) else default


def _as_error(item) -> ProviderError:
    if isinstance(item, ProviderError):
        return item
    return ProviderError(ProviderErrorKind(item), f"scripted {item}")


def install(monkeypatch) -> ClipWorld:
    world = ClipWorld()
    monkeypatch.setattr(providers, "allowed_lengths", lambda model: [4.0, 6.0, 8.0])

    def set_shot_state(job_shot_id, status, detail):
        world.record("set_shot_state", shot=job_shot_id, status=status, detail=detail)

    def start_attempt(job_shot_id, prompt, model, requested_s):
        with world.lock:
            position = int(job_shot_id[-1])
            n = world._shots.get(job_shot_id, 0) + 1
            world._shots[job_shot_id] = n
            attempt_id = f"att-{position}-{n}"
            world._attempt_shot[attempt_id] = job_shot_id
        world.record(
            "start_attempt",
            shot=job_shot_id,
            attempt_id=attempt_id,
            prompt=prompt,
            model=model,
            requested_s=requested_s,
        )
        return attempt_id

    def finish_attempt(attempt_id, status, clip_key=None, check=None, error=None, cost_usd=0.0):
        world.record(
            "finish_attempt",
            attempt_id=attempt_id,
            status=status,
            clip_key=clip_key,
            check=check,
            error=error,
            cost_usd=cost_usd,
        )

    def set_shot_result(job_shot_id, result, failure_reason=None, final_attempt_id=None):
        world.record(
            "set_shot_result",
            shot=job_shot_id,
            result=result,
            failure_reason=failure_reason,
            final_attempt_id=final_attempt_id,
        )

    def generate_clip(first_frame_jpeg, prompt, model, length_s, ids):
        shot = ids["jobShotId"]
        world.record("generate_clip", shot=shot, model=model, ids=dict(ids))
        step = world._next(world.generate, shot, None)
        if step is not None:
            world.record("generate_failed", shot=shot)
            raise _as_error(step)
        fd, path = tempfile.mkstemp(suffix=".mp4")
        os.write(fd, b"clip")
        os.close(fd)
        world.clip_paths.append(path)
        world.current_shot.id = shot
        return ClipResult(
            path=path,
            seconds=length_s,
            model=model,
            cost_usd=0.25,
            cost_source="reported",
            provider_request_id=None,
        )

    def extract_frames(clip_path, per_second):
        world.record("extract_frames", path=clip_path)
        shot = world.current_shot.id
        step = world._next(world.frame_errors, shot, None)
        if step is not None:
            raise step
        return []

    def check_clip(clip_path, frames, source_jpeg, ids):
        shot = ids["jobShotId"]
        world.record("check_clip", shot=shot, ids=dict(ids))
        step = world._next(world.checks, shot, passed_check())
        if isinstance(step, (ProviderError, str)):
            world.record("check_failed", shot=shot)
            raise _as_error(step)
        return step

    def put(key, path):
        world.record("put", key=key)
        BUCKET[key] = b"clip"

    def wait(seconds):
        world.record("wait", seconds=seconds)
        world.clock.now += seconds

    monkeypatch.setattr(jobs, "set_shot_state", set_shot_state)
    monkeypatch.setattr(jobs, "start_attempt", start_attempt)
    monkeypatch.setattr(jobs, "finish_attempt", finish_attempt)
    monkeypatch.setattr(jobs, "set_shot_result", set_shot_result)
    monkeypatch.setattr(providers, "generate_clip", generate_clip)
    monkeypatch.setattr(media, "extract_frames", extract_frames)
    monkeypatch.setattr(providers, "check_clip", check_clip)
    monkeypatch.setattr(files, "put", put)
    monkeypatch.setattr(files, "get", lambda key, path: Path(path).write_bytes(BUCKET[key]))
    monkeypatch.setattr(clip, "_wait", wait)
    BUCKET.clear()
    return world
