"""Assemble clips over a song: re-encoded, frame-exact cuts and crossfades."""

from collections.abc import Sequence

from app.media import tools
from app.media.errors import MediaError
from app.media.video import probe


def _incoming(clip: dict, index: int) -> float:
    """Seconds of crossfade into this clip; 0 means a hard cut."""
    transition = clip.get("transition", "cut")
    if transition not in ("cut", "crossfade"):
        raise MediaError(f"unknown transition: {transition}")
    seconds = float(clip.get("transitionS") or 0)
    if index == 0 or transition == "cut" or seconds <= 0:
        return 0.0
    return seconds


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
    if not clips:
        raise MediaError("no clips to assemble")
    fades = [_incoming(clip, i) for i, clip in enumerate(clips)]

    args: list[str] = ["ffmpeg"]
    for clip in clips:
        args += ["-i", str(clip["path"])]
    args += ["-ss", str(song_offset_s), "-i", str(song_path)]

    # Cut boundaries sit on the frame grid from the cumulative plan, so rounding
    # never accumulates from clip to clip.
    bounds = [0.0]
    for clip in clips:
        bounds.append(bounds[-1] + float(clip["lengthS"]))
    starts = [round(t * fps) for t in bounds]
    fade_frames = [round(f * fps) for f in fades]

    parts: list[str] = []
    for i in range(len(clips)):
        frames = max(1, starts[i + 1] - starts[i]) + fade_frames[i]
        parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps},format=yuv420p,"
            f"tpad=stop_mode=clone:stop_duration={frames / fps + 1},"
            f"trim=end_frame={frames},setpts=PTS-STARTPTS[v{i}]"
        )

    acc = "v0"
    for i in range(1, len(clips)):
        out = f"j{i}"
        if fade_frames[i] > 0:
            offset = (starts[i] - fade_frames[i]) / fps
            parts.append(
                f"[{acc}][v{i}]xfade=transition=fade:duration={fade_frames[i] / fps}"
                f":offset={offset}[{out}]"
            )
        else:
            parts.append(f"[{acc}][v{i}]concat=n=2:v=1:a=0,settb=1/{fps}[{out}]")
        acc = out
    total = starts[-1] / fps

    parts.append(f"[{len(clips)}:a]apad[a]")
    args += [
        "-filter_complex",
        ";".join(parts),
        "-map",
        f"[{acc}]",
        "-map",
        "[a]",
        "-t",
        str(total),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        "-y",
        str(out_path),
    ]
    tools.run(args)
    return {"durationS": probe(str(out_path))["durationS"]}
