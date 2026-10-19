"""One runner for ffmpeg and ffprobe: every tool failure becomes a MediaError."""

import subprocess

from app.media.errors import MediaError

_QUIET = ["-hide_banner", "-v", "error"]


def run(args: list[str]) -> bytes:
    """Run a tool (args[0] is ffmpeg or ffprobe) and return its stdout."""
    argv = [args[0], *_QUIET, *args[1:]] if args[0] in ("ffmpeg", "ffprobe") else list(args)
    try:
        result = subprocess.run(argv, capture_output=True)
    except FileNotFoundError as exc:
        raise MediaError(str(exc)) from exc
    if result.returncode != 0:
        message = result.stderr.decode(errors="replace").strip()
        raise MediaError(message or f"{args[0]} exited with {result.returncode}")
    return result.stdout
