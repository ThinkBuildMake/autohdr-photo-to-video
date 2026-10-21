"""Fail when app code that is not itself a stubs module imports one or names "stub-media"."""

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _imports_stubs(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any("stubs" in a.name.split(".") for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and (
            "stubs" in (node.module or "").split(".") or any(a.name == "stubs" for a in node.names)
        ):
            return True
    return False


def find_stub_uses(repo_root: Path) -> list[str]:
    found = []
    for path in sorted((repo_root / "app").rglob("*.py")):
        if path.name == "stubs.py":
            continue
        source = path.read_text(encoding="utf-8")
        name = path.relative_to(repo_root).as_posix()
        if _imports_stubs(ast.parse(source)):
            found.append(f"{name}: imports a stubs module")
        if "stub-media" in source:
            found.append(f"{name}: names stub-media")
    return found


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    found = find_stub_uses(Path(args[0]) if args else REPO_ROOT)
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
