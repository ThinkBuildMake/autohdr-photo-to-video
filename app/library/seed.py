"""Songs seed command: `python -m app.library.seed --manifest PATH`.

Adds or updates Creative Commons tracks from a JSON manifest. Only BY-NC and BY-NC-SA
are accepted: music under a video is an adaptation, so no-derivatives licences are
refused by name (GC-5). The audio file itself is not read or copied; the manifest
names where it is stored (`fileKey`).

Manifest format: either `{"tracks": [...]}` or a bare list of tracks. Each track has:
  title, artist           text
  licence                 e.g. "BY-NC", "CC BY-NC-SA 4.0"
  sourceUrl               page where the track was obtained (also accepted: source_url)
  fileKey                 storage key, e.g. "songs/track-a.mp3" (or `file`, a file name,
                          stored as "songs/<file>")
  durationS               length in seconds (also accepted: duration_s)
Other keys (licence_url, source, credit, ...) are ignored; the credit line is built
from title, artist, licence and source URL.
"""

import argparse
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.db.base import session_scope
from app.db.schema import init_db
from app.library import models

ALLOWED = ("BY-NC", "BY-NC-SA")

_LEADING_CC = re.compile(r"^CC[\s-]*")
_TRAILING_VERSION = re.compile(r"[\s-]*\d+(\.\d+)*$")


@dataclass
class SeedResult:
    added: list[str] = field(default_factory=list)
    refused: list[tuple[str, str]] = field(default_factory=list)


def normalise_licence(raw: str) -> str:
    code = _LEADING_CC.sub("", raw.strip().upper())
    return _TRAILING_VERSION.sub("", code).replace(" ", "")


def _field(track: dict, *names: str):
    for name in names:
        if track.get(name) not in (None, ""):
            return track[name]
    return None


def _parse(track: dict) -> tuple[dict | None, str]:
    """Return the song columns, or None and the reason the track is refused."""
    file_key = _field(track, "fileKey", "file_key")
    if file_key is None and _field(track, "file") is not None:
        file_key = f"songs/{track['file']}"
    values = {
        "title": _field(track, "title"),
        "artist": _field(track, "artist"),
        "licence": _field(track, "licence"),
        "source_url": _field(track, "sourceUrl", "source_url"),
        "file_key": file_key,
        "duration_s": _field(track, "durationS", "duration_s"),
    }
    missing = [name for name, value in values.items() if value is None]
    if missing:
        return None, "missing " + ", ".join(missing)
    try:
        values["duration_s"] = float(values["duration_s"])
    except (TypeError, ValueError):
        return None, "durationS is not a number"
    licence = str(values.pop("licence"))
    code = normalise_licence(licence)
    if code not in ALLOWED:
        return None, (
            f"licence {licence} is not BY-NC or BY-NC-SA (no adaptation: "
            "music under a video is an adaptation)"
        )
    values["licence_code"] = code
    return values, code


def _tracks(manifest_path: Path) -> list[dict]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    tracks = data.get("tracks") if isinstance(data, dict) else data
    if not isinstance(tracks, list):
        raise ValueError('the manifest must be {"tracks": [...]} or a list of tracks')
    return [t if isinstance(t, dict) else {} for t in tracks]


def seed_songs(manifest_path) -> SeedResult:
    init_db()
    result = SeedResult()
    for track in _tracks(Path(manifest_path)):
        values, code = _parse(track)
        label = str(track.get("title") or "(untitled)")
        who = str(track.get("artist") or "unknown artist")
        if values is None:
            result.refused.append((f"{label} by {who}", code))
            continue
        song_id = str(uuid.uuid5(uuid.NAMESPACE_URL, values["source_url"]))
        with session_scope() as session:
            row = session.get(models.Song, song_id)
            if row is None:
                session.add(models.Song(id=song_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
        result.added.append(f"{label} by {who} ({code})")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.library.seed")
    parser.add_argument("--manifest", required=True, help="JSON file listing the songs")
    args = parser.parse_args(argv)
    try:
        result = seed_songs(args.manifest)
    except (OSError, ValueError) as error:
        print(f"cannot read manifest: {error}", file=sys.stderr)
        return 1
    for line in result.added:
        print(f"added: {line}")
    for label, reason in result.refused:
        print(f"refused: {label}: {reason}", file=sys.stderr)
    return 1 if result.refused else 0


if __name__ == "__main__":
    sys.exit(main())
