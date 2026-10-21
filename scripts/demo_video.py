#!/usr/bin/env python3
"""Offline copy of the demo job's video (docs/DEMO.md).

  demo_video.py fetch --base URL JOB_ID OUT   download the finished video
  demo_video.py verify OUT [--min-seconds N]  check it has picture, song and length

The passphrase comes from DEMO_PASSPHRASE or ~/.autohdr-demo-passphrase. It and the signed
download link are never printed.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

PASSPHRASE_FILE = Path.home() / ".autohdr-demo-passphrase"


def passphrase() -> str:
    text = os.environ.get("DEMO_PASSPHRASE") or (
        PASSPHRASE_FILE.read_text() if PASSPHRASE_FILE.exists() else ""
    )
    if not text.strip():
        sys.exit("no passphrase: set DEMO_PASSPHRASE or fill ~/.autohdr-demo-passphrase")
    return text.strip()


def fetch(base: str, job_id: str, out: str) -> int:
    auth = ("demo", passphrase())
    part = out + ".part"  # a failed run never touches an existing OUT
    try:
        links = httpx.get(f"{base.rstrip('/')}/api/jobs/{job_id}/video", auth=auth, timeout=30)
        if links.status_code != 200:
            print(f"fetch failed: the app answered {links.status_code}", file=sys.stderr)
            return 1
        with httpx.stream("GET", links.json()["downloadUrl"], timeout=120) as response:
            if response.status_code != 200:
                print(
                    f"fetch failed: the download answered {response.status_code}", file=sys.stderr
                )
                return 1
            with open(part, "wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
        os.replace(part, out)
    except OSError as error:
        print(f"fetch failed: cannot write {out} ({error.strerror})", file=sys.stderr)
        Path(part).unlink(missing_ok=True)
        return 1
    except (httpx.HTTPError, ValueError, KeyError) as error:
        # Only the error class is printed: httpx messages can carry the signed link.
        print(
            f"fetch failed: {type(error).__name__}; check the network and the job id",
            file=sys.stderr,
        )
        Path(part).unlink(missing_ok=True)
        return 1
    print(f"saved {out} ({os.path.getsize(out)} bytes)")
    return 0


def verify(path: str, min_seconds: float) -> int:
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-of", "json", path,
             "-show_entries", "stream=codec_type,codec_name:format=duration"],
            check=True, capture_output=True, text=True,
        )  # fmt: skip
        info = json.loads(probe.stdout)
    except (OSError, subprocess.CalledProcessError, ValueError):
        print(f"FAIL: {path} is missing or not a video", file=sys.stderr)
        return 1
    codecs = {s["codec_type"]: s["codec_name"] for s in info.get("streams", [])}
    seconds = float(info.get("format", {}).get("duration") or 0)
    problems = [
        text
        for text, bad in [
            ("no video stream", "video" not in codecs),
            ("no song (audio stream)", "audio" not in codecs),
            (f"only {seconds:.1f}s, need {min_seconds:g}s", seconds < min_seconds),
        ]
        if bad
    ]
    if problems:
        print("FAIL: " + "; ".join(problems), file=sys.stderr)
        return 1
    print(f"OK: {seconds:.1f}s, {os.path.getsize(path)} bytes, audio {codecs['audio']}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--base", required=True)
    f.add_argument("job_id")
    f.add_argument("out")
    v = sub.add_parser("verify")
    v.add_argument("out")
    v.add_argument("--min-seconds", type=float, default=20)
    args = parser.parse_args(argv)
    if args.cmd == "fetch":
        return fetch(args.base, args.job_id, args.out)
    return verify(args.out, args.min_seconds)


if __name__ == "__main__":
    sys.exit(main())
