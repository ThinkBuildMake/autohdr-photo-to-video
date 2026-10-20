"""evals import: one photoshoot per test shoot folder, reusing one already uploaded."""

import json
from pathlib import Path

from sqlalchemy import select

from app.db.base import session_scope
from app.db.schema import init_db
from app.evals import stubs
from app.photoshoots.models import Photoshoot

SHOOTS_FILE = "shoots.json"
PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png"}


def import_shoots(folder: Path, out: Path) -> dict[str, str]:
    """Returns and saves label -> photoshoot id, in folder-name order."""
    init_db()
    subfolders = sorted(p for p in folder.iterdir() if p.is_dir())
    with session_scope() as session:
        existing = dict(session.execute(select(Photoshoot.label, Photoshoot.id)).tuples().all())
    shoots = {}
    for sub in subfolders:
        if sub.name in existing:
            shoots[sub.name] = existing[sub.name]
        else:
            paths = [
                str(p)
                for p in sorted(sub.iterdir())
                if p.is_file() and p.suffix.lower() in PHOTO_SUFFIXES
            ]
            shoots[sub.name] = stubs.import_photoshoot(paths, sub.name)
    out.mkdir(parents=True, exist_ok=True)
    (out / SHOOTS_FILE).write_text(json.dumps(shoots, indent=2))
    return shoots
