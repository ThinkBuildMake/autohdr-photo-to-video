"""Video inspection and frame extraction on top of ffprobe and ffmpeg."""

import json
import tempfile
from pathlib import Path

from app.media import tools
from app.media.errors import MediaError


def _fraction(text: str) -> float:
    num, _, den = text.partition("/")
    denominator = float(den) if den else 1.0
    return float(num) / denominator if denominator else 0.0


def probe(video_path: str) -> dict:
    """Returns {durationS, fps, width, height} for the first video stream."""
    out = tools.run(
        [
            "ffprobe",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,avg_frame_rate:format=duration",
            "-of",
            "json",
            str(video_path),
        ]
    )
    info = json.loads(out)
    streams = info.get("streams") or []
    if not streams:
        raise MediaError(f"no video stream in {video_path}")
    stream = streams[0]
    fps = _fraction(stream.get("r_frame_rate") or "0/0")
    if not fps:
        fps = _fraction(stream.get("avg_frame_rate") or "0/0")
    return {
        "durationS": float(info.get("format", {}).get("duration") or 0.0),
        "fps": round(fps, 3),
        "width": int(stream["width"]),
        "height": int(stream["height"]),
    }


def extract_frames(clip_path: str, per_second: float) -> list[bytes]:
    """JPEG frames sampled at per_second, in playback order."""
    with tempfile.TemporaryDirectory() as tmp:
        tools.run(
            [
                "ffmpeg",
                "-i",
                str(clip_path),
                "-vf",
                f"fps={per_second}",
                "-q:v",
                "3",
                f"{tmp}/%05d.jpg",
            ]
        )
        return [p.read_bytes() for p in sorted(Path(tmp).glob("*.jpg"))]
