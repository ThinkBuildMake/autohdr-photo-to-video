import pytest

from app.media import service, tools
from tests.media.synth import color_clip, dominant_hz, frame_rgb_mean, tone_song


def _clip(path, length, transition="cut", transition_s=0):
    return {"path": str(path), "lengthS": length, "transition": transition,
            "transitionS": transition_s}  # fmt: skip


def test_cuts_land_within_a_frame(tmp_path):
    paths = [color_clip(tmp_path / f"{c}.mp4", c) for c in ("red", "green", "blue")]
    song = tone_song(tmp_path / "song.wav")
    clips = [_clip(p, n) for p, n in zip(paths, (3.0, 2.5, 3.5), strict=True)]
    out = str(tmp_path / "out.mp4")
    service.assemble(clips, str(song), 0, out, 1920, 1080, 30)
    cuts = service.detect_cuts(out)
    assert len(cuts) == 2
    assert abs(cuts[0] - 3.0) <= 1 / 30
    assert abs(cuts[1] - 5.5) <= 1 / 30
    before, after = frame_rgb_mean(out, 89), frame_rgb_mean(out, 90)
    assert before[0] > 240 and before[1] < 15 and before[2] < 15
    assert after[1] > 100 and after[0] < 15 and after[2] < 15


def test_crossfade_ends_at_the_cut(tmp_path):
    red = color_clip(tmp_path / "red.mp4", "red")
    blue = color_clip(tmp_path / "blue.mp4", "blue")
    song = tone_song(tmp_path / "song.wav")
    clips = [_clip(red, 3.0), _clip(blue, 3.0, "crossfade", 0.5)]
    out = str(tmp_path / "out.mp4")
    result = service.assemble(clips, str(song), 0, out, 1920, 1080, 30)
    assert abs(result["durationS"] - 6.0) <= 1 / 30
    r, g, b = frame_rgb_mean(out, 90)
    assert r < 10 and g < 10 and b > 245
    r, g, b = frame_rgb_mean(out, 74)
    assert r > 245 and g < 10 and b < 10
    r, g, b = frame_rgb_mean(out, 82)
    assert r > 60 and b > 60


@pytest.mark.parametrize(("fps", "size", "src_fps"), [(24, (1280, 720), 24), (30, (640, 480), 25)])
def test_output_format(tmp_path, fps, size, src_fps):
    a = color_clip(tmp_path / "a.mp4", "red", size=size, fps=src_fps)
    b = color_clip(tmp_path / "b.mp4", "blue", size=size, fps=src_fps)
    song = tone_song(tmp_path / "song.wav")
    out = str(tmp_path / "out.mp4")
    clips = [_clip(a, 2.0), _clip(b, 1.5)]
    service.assemble(clips, str(song), 0, out, 1920, 1080, fps)
    info = service.probe(out)
    assert (info["width"], info["height"]) == (1920, 1080)
    assert info["fps"] == fps
    assert abs(info["durationS"] - 3.5) <= 1 / fps


def test_song_starts_at_offset(tmp_path):
    song = tone_song(tmp_path / "song.wav", seconds=30)
    clips = [_clip(color_clip(tmp_path / f"{i}.mp4", "red", seconds=2), 1.0) for i in range(3)]
    out = str(tmp_path / "out.mp4")
    service.assemble(clips, str(song), 12, out, 1920, 1080, 30)
    for k, hz in enumerate((800, 850, 900)):
        assert abs(dominant_hz(out, k + 0.1, k + 0.9) - hz) <= 5


def test_non_video_clip_raises_tool_message(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    song = tone_song(tmp_path / "song.wav", seconds=5)
    with pytest.raises(service.MediaError) as exc:
        service.assemble([_clip(bad, 1.0)], str(song), 0, str(tmp_path / "o.mp4"), 1920, 1080, 30)
    assert "Invalid data found when processing input" in str(exc.value)


def test_unknown_transition_is_named(tmp_path):
    clips = [_clip("a.mp4", 1.0), _clip("b.mp4", 1.0, "wipe", 0.5)]
    with pytest.raises(service.MediaError, match="wipe"):
        service.assemble(clips, "s.wav", 0, str(tmp_path / "o.mp4"), 1920, 1080, 30)


@pytest.mark.parametrize("fps", [24, 30])
def test_cuts_are_reencoded_not_keyframe_snapped(tmp_path, monkeypatch, fps):
    calls = []
    real = tools.run

    def spy(args):
        calls.append(list(args))
        return real(args)

    monkeypatch.setattr(tools, "run", spy)
    colors = ("red", "green", "blue")
    paths = [color_clip(tmp_path / f"{c}.mp4", c, gop=48) for c in colors]
    song = tone_song(tmp_path / "song.wav")
    clips = [_clip(p, n) for p, n in zip(paths, (1.5, 2.0, 1.5), strict=True)]
    out = str(tmp_path / "out.mp4")
    service.assemble(clips, str(song), 0, out, 1920, 1080, fps)
    cuts = service.detect_cuts(out)
    assert len(cuts) == 2
    assert abs(cuts[0] - 1.5) <= 1 / fps
    assert abs(cuts[1] - 3.5) <= 1 / fps
    assert calls
    assert all("copy" not in call for call in calls)


def test_crossfade_after_an_earlier_cut(tmp_path):
    paths = [color_clip(tmp_path / f"{c}.mp4", c) for c in ("red", "green", "blue")]
    song = tone_song(tmp_path / "song.wav")
    clips = [
        _clip(paths[0], 2.0),
        _clip(paths[1], 2.0),
        _clip(paths[2], 2.0, "crossfade", 0.5),
    ]
    out = str(tmp_path / "out.mp4")
    result = service.assemble(clips, str(song), 0, out, 1920, 1080, 30)
    assert abs(result["durationS"] - 6.0) <= 1 / 30
    r, g, b = frame_rgb_mean(out, 60)
    assert g > 100 and r < 15 and b < 15
    r, g, b = frame_rgb_mean(out, 120)
    assert b > 245 and r < 10 and g < 10


@pytest.mark.parametrize("fps", [24, 30])
def test_cuts_do_not_drift_with_fractional_frame_lengths(tmp_path, fps):
    colors = ("red", "green", "blue")
    paths = [color_clip(tmp_path / f"{i}.mp4", colors[i % 3], seconds=4) for i in range(12)]
    song = tone_song(tmp_path / "song.wav")
    clips = [_clip(p, 2.49) for p in paths]
    out = str(tmp_path / "out.mp4")
    service.assemble(clips, str(song), 0, out, 1920, 1080, fps)
    cuts = service.detect_cuts(out)
    assert len(cuts) == 11
    for i, cut in enumerate(cuts, start=1):
        assert abs(cut - i * 2.49) <= 1 / fps
