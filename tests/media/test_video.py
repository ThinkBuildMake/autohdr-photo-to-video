import io

import pytest
from PIL import Image

from app.media.errors import MediaError
from app.media.tools import run
from app.media.video import extract_frames, probe
from tests.media.synth import color_clip, dominant_hz, frame_rgb_mean, pattern_clip, tone_song


def test_extract_frames_six_per_second(tmp_path):
    clip = pattern_clip(tmp_path / "pattern.mp4", seconds=4.0, fps=24)
    frames = extract_frames(str(clip), 6)
    assert len(frames) == 24
    for frame in frames:
        assert Image.open(io.BytesIO(frame)).format == "JPEG"


def test_probe_reports_size_rate_duration(tmp_path):
    clip = color_clip(tmp_path / "red.mp4", "red", seconds=4.0, size=(1280, 720), fps=24)
    info = probe(str(clip))
    assert info["width"] == 1280
    assert info["height"] == 720
    assert info["fps"] == 24.0
    assert abs(info["durationS"] - 4.0) <= 1 / 24


def test_probe_non_video_raises_tool_message(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(MediaError) as err:
        probe(str(bad))
    assert "Invalid data found when processing input" in str(err.value)


def test_run_missing_tool_raises_media_error():
    with pytest.raises(MediaError):
        run(["no-such-media-tool-xyz"])


def test_synth_helpers_measure_what_they_make(tmp_path):
    clip = color_clip(tmp_path / "red.mp4", "red", seconds=1.0)
    assert frame_rgb_mean(clip, 5)[0] > 200
    song = tone_song(tmp_path / "song.wav", seconds=5)
    assert abs(dominant_hz(song, 2.2, 2.8) - 300) <= 5
