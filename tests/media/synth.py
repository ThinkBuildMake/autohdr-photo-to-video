"""Synthetic clips and tones for Media tests. Everything is written to a caller-given path."""

import subprocess

import numpy as np


def _ffmpeg(*args):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "error", "-y", *map(str, args)],
        check=True,
        capture_output=True,
    )


def color_clip(path, color, seconds=4.0, size=(1280, 720), fps=24, gop=None):
    src = f"color=c={color}:s={size[0]}x{size[1]}:r={fps}:d={seconds}"
    extra = ["-g", gop] if gop else []
    _ffmpeg("-f", "lavfi", "-i", src, "-c:v", "libx264", "-pix_fmt", "yuv420p", *extra, path)
    return path


def pattern_clip(path, seconds=4.0, fps=24):
    src = f"testsrc2=s=640x360:r={fps}:d={seconds}"
    _ffmpeg("-f", "lavfi", "-i", src, "-c:v", "libx264", "-pix_fmt", "yuv420p", path)
    return path


def tone_song(path, seconds=30):
    """WAV whose frequency in second t is 200 + 50 * floor(t) Hz."""
    src = f"aevalsrc='sin(2*PI*(200+50*floor(t))*t)':s=44100:d={seconds}"
    _ffmpeg("-f", "lavfi", "-i", src, path)
    return path


def frame_rgb_mean(video, index):
    """Mean (R, G, B) of frame number `index`."""
    out = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-v", "error", "-i", str(video),
            "-vf", f"select=eq(n\\,{index})", "-frames:v", "1",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ],
        check=True,
        capture_output=True,
    ).stdout  # fmt: skip
    pixels = np.frombuffer(out, dtype=np.uint8).reshape(-1, 3)
    return pixels.mean(axis=0)


def dominant_hz(video, start_s, end_s):
    """Strongest frequency in the audio between start_s and end_s."""
    out = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-v", "error", "-ss", str(start_s),
            "-t", str(end_s - start_s),
            "-i", str(video), "-vn", "-ac", "1", "-ar", "44100", "-f", "s16le", "-",
        ],
        check=True,
        capture_output=True,
    ).stdout  # fmt: skip
    samples = np.frombuffer(out, dtype=np.int16).astype(np.float64)
    spectrum = np.abs(np.fft.rfft(samples))
    return float(np.argmax(spectrum) * 44100 / len(samples))
