"""Fail when configuration or code points at an outside host that is not approved."""

import ast
import dataclasses
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

APPROVED = ("openrouter.ai", "t3.storageapi.dev")
LOCAL = ("localhost", "127.0.0.1", "0.0.0.0")
URL = re.compile(r"https?://[^\s'\"<>)\]]+")


def _host_ok(host: str) -> bool:
    host = host.lower()
    return host in LOCAL or host in APPROVED or host.endswith(".t3.storageapi.dev")


def _unapproved(text: str) -> list[str]:
    found = []
    for match in URL.findall(text):
        host = urlparse(match).hostname or ""
        if not _host_ok(host):
            found.append(host)
    return found


def find_unapproved_hosts(repo_root: Path, settings) -> list[tuple[str, str]]:
    repo_root = Path(repo_root)
    findings: list[tuple[str, str]] = []

    env_example = repo_root / ".env.example"
    if env_example.is_file():
        for line in env_example.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            for host in _unapproved(value):
                findings.append((f".env.example {key.strip()}", host))

    if settings is not None:
        for field in dataclasses.fields(settings):
            value = getattr(settings, field.name)
            if isinstance(value, str):
                for host in _unapproved(value):
                    findings.append((f"Settings.{field.name}", host))

    app_dir = repo_root / "app"
    if app_dir.is_dir():
        for path in sorted(app_dir.rglob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            rel = path.relative_to(repo_root).as_posix()
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for host in _unapproved(node.value):
                        findings.append((f"{rel}:{node.lineno}", host))
    return findings


def main() -> int:
    from app.config import load_settings

    findings = find_unapproved_hosts(REPO_ROOT, load_settings())
    for where, host in findings:
        print(f"unapproved host {host} in {where}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
