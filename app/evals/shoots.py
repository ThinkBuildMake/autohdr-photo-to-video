"""evals import: one photoshoot per test shoot folder, reusing one already uploaded."""

import json
import time
from pathlib import Path

from sqlalchemy import select

from app.db.base import session_scope
from app.db.schema import init_db
from app.photoshoots import service as photoshoots
from app.photoshoots.models import Photoshoot

SHOOTS_FILE = "shoots.json"
PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png"}
LABEL_POLL_S = 0.5
LABEL_TIMEOUT_S = 600


def _ready_shoots() -> dict[str, str]:
    """Label -> id of the newest ready shoot with that label; says so when a label repeats."""
    with session_scope() as session:
        rows = session.execute(
            select(Photoshoot.label, Photoshoot.id)
            .where(Photoshoot.status == "ready", Photoshoot.label.is_not(None))
            .order_by(Photoshoot.created_at.desc())
        ).all()
    newest: dict[str, str] = {}
    for label, shoot_id in rows:
        if label in newest:
            print(f"warning: several ready shoots are labelled {label!r}; using the newest")
        newest.setdefault(label, shoot_id)
    return newest


def _wait_labelled(shoot_id: str, label: str) -> None:
    deadline = time.monotonic() + LABEL_TIMEOUT_S
    while (status := photoshoots.get_photoshoot(shoot_id).status) == "labelling":
        if time.monotonic() > deadline:
            raise SystemExit(f"Shoot {label!r} is still being labelled after 10 minutes.")
        time.sleep(LABEL_POLL_S)
    if status != "ready":
        raise SystemExit(f"Shoot {label!r} ended as {status}, not ready.")


def import_shoots(folder: Path, out: Path) -> dict[str, str]:
    """Returns and saves label -> photoshoot id, in folder-name order."""
    init_db()
    existing = _ready_shoots()
    shoots = {}
    for sub in sorted(p for p in folder.iterdir() if p.is_dir()):
        if sub.name in existing:
            shoots[sub.name] = existing[sub.name]
            continue
        paths = [
            str(p)
            for p in sorted(sub.iterdir())
            if p.is_file() and p.suffix.lower() in PHOTO_SUFFIXES
        ]
        shoots[sub.name] = photoshoots.import_photoshoot(paths, sub.name)
        _wait_labelled(shoots[sub.name], sub.name)
    out.mkdir(parents=True, exist_ok=True)
    (out / SHOOTS_FILE).write_text(json.dumps(shoots, indent=2))
    return shoots
