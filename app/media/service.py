"""Media: image and video processing. Stub: S05 builds it."""

from collections.abc import Sequence

_NOT_BUILT = "Media is built in S05."


class MediaError(Exception):
    """A Pillow or ffmpeg step failed; the message is the tool's."""


def crop16x9(image_bytes: bytes) -> bytes:
    raise NotImplementedError(_NOT_BUILT)


def thumbnail(image_bytes: bytes, long_side: int) -> bytes:
    raise NotImplementedError(_NOT_BUILT)


def extract_frames(clip_path: str, per_second: float) -> list[bytes]:
    raise NotImplementedError(_NOT_BUILT)


def probe(video_path: str) -> dict:
    """Returns {durationS, fps, width, height}."""
    raise NotImplementedError(_NOT_BUILT)


def assemble(
    clips: Sequence[dict],
    song_path: str,
    song_offset_s: float,
    out_path: str,
    width: int,
    height: int,
    fps: int,
) -> dict:
    """clips: [{path, lengthS, transition, transitionS}]. Returns {durationS}."""
    raise NotImplementedError(_NOT_BUILT)


def detect_cuts(video_path: str) -> list[float]:
    raise NotImplementedError(_NOT_BUILT)
