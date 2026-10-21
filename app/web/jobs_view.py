"""Words and formatting the Jobs and Job pages show for a job's state."""

JOB_CHIPS = {
    "draft": ("Draft", "wait"),
    "queued": ("Waiting", "wait"),
    "running": ("Making", "work"),
    "ready": ("Ready", "done"),
    "ready_with_failures": ("Ready, some shots failed", "retry"),
    "stopped": ("Stopped", "fail"),
}

SHOT_CHIPS = {
    "pending": ("Waiting", "wait"),
    "editing": ("Editing the photo", "work"),
    "generating": ("Making the clip", "work"),
    "checking": ("Checking the clip", "work"),
    "passed": ("Passed", "done"),
    "failed": ("Failed", "fail"),
    "skipped": ("Skipped", "wait"),
}


STOP_MESSAGES = {
    "out_of_credit": (
        "Stopped: the video service account is out of credit",
        "Top up the account, then start again: only the unfinished shots are made.",
    ),
    "worker_restarted": (
        "Stopped: the app restarted while your video was being made",
        "Start again: only the unfinished shots are made.",
    ),
    "assembly_failed": (
        "Stopped: the clips could not be put together into a video",
        "Start again to try once more: the finished clips are kept.",
    ),
    "no_shot_passed": (
        "Stopped: no shot passed its check",
        "Start again to make every shot once more.",
    ),
}

FAILURE_REASONS = {
    "flagged_every_attempt": "Failed the check on every attempt",
    "provider_error": "The video service returned an error",
    "refused": "The video service refused this shot",
    "out_of_time": "Ran out of time",
    "no_photo": "No photo of this room",
    "job_stopped": "The job stopped before this shot finished",
}


def stop_message(reason: str | None) -> tuple[str, str]:
    return STOP_MESSAGES.get(reason, ("Stopped", STOP_MESSAGES["worker_restarted"][1]))


def failure(reason: str) -> str:
    return FAILURE_REASONS.get(reason, words(reason))


def credit_parts(credit: str) -> tuple[str, str | None]:
    """Song.credit is "title, artist, licence, source URL": split off the URL to link it.

    Only http(s) sources are linked, so a `javascript:` source can never run on click.
    """
    text, _, url = credit.rpartition(", ")
    return (text, url) if text and url.startswith(("http://", "https://")) else (credit, None)


def shot_chip(shot) -> tuple[str, str]:
    if shot.status in ("editing", "generating", "checking") and shot.attempts > 1:
        return "Trying again", "retry"
    return SHOT_CHIPS[shot.status]


def words(code: str) -> str:
    """A snake_case code as words: exterior_front -> Exterior front."""
    return code.replace("_", " ").capitalize()


def elapsed(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    parts = [f"{hours} h" if hours else "", f"{minutes} min" if minutes else ""]
    if secs or not (hours or minutes):
        parts.append(f"{secs} s")
    return " ".join(part for part in parts if part)


def shot_numbers(positions: list[int]) -> str:
    if len(positions) == 1:
        return str(positions[0])
    return ", ".join(map(str, positions[:-1])) + " and " + str(positions[-1])
