"""Fail when a photo or video is committed outside tests/fixtures/."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SUFFIXES = (".jpg", ".jpeg", ".png", ".mp4")


def find_committed_media(repo_root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repo_root, capture_output=True, check=True
    ).stdout.decode()
    return [
        path
        for path in out.split("\0")
        if path and path.lower().endswith(SUFFIXES) and not path.startswith("tests/fixtures/")
    ]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]) if args else REPO_ROOT
    found = find_committed_media(root)
    for path in found:
        print(f"photo or video committed outside tests/fixtures: {path}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
