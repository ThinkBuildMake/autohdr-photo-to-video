import os
import random
import re
import shlex
import shutil
import signal
import subprocess
import time
from pathlib import Path

import httpx

from tests.support.markdown import sections

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
# Set by tests/conftest.py or a developer's shell; a clean setup must not rely on them.
CLEARED = ("DATABASE_PATH", "OPENROUTER_API_KEY", "VIRTUAL_ENV")


def readme_section(prefix: str) -> str:
    found = [
        body for heading, body in sections(README.read_text()).items() if heading.startswith(prefix)
    ]
    assert len(found) == 1, prefix
    return found[0]


def clean_checkout(dest: Path) -> Path:
    """Copy what a fresh clone would have: tracked and new unignored files, no .env."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    for name in listed:
        if (ROOT / name).is_file():
            (dest / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dest / name)
    return dest


def healthy(port: int, proc: subprocess.Popen) -> bool:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline and proc.poll() is None:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=5).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    return False


def test_setup_steps_start_the_app(tmp_path):
    block = re.search(r"```bash\n(.*?)```", readme_section("Set up"), re.DOTALL)
    assert block, "no bash block in the setup section"
    lines = [ln for ln in block.group(1).splitlines() if ln.strip() and not ln.startswith("#")]
    start = [ln for ln in lines if "honcho start" in ln]
    assert len(start) == 1 and lines[-1] == start[0]
    tokens = shlex.split(start[0])
    assigned = dict(t.split("=", 1) for t in tokens if re.match(r"^[A-Z_]+=", t))
    argv = tokens[len(assigned) :]
    assert assigned["PORT"] == "8000" and assigned["FAKE_PROVIDERS"] == "1"
    checkout = clean_checkout(tmp_path / "checkout")
    env = {k: v for k, v in os.environ.items() if k not in CLEARED}
    env |= {"UV_PROJECT_ENVIRONMENT": str(ROOT / ".venv"), "UV_OFFLINE": "1"}
    for line in lines[:-1]:
        subprocess.run(line, shell=True, cwd=checkout, env=env, check=True)
    port = random.randrange(20000, 32000)
    env |= assigned | {"PORT": str(port)}
    proc = subprocess.Popen(argv, cwd=checkout, env=env, start_new_session=True)
    try:
        assert healthy(port, proc), "/healthz never answered 200"
        page = httpx.get(f"http://127.0.0.1:{port}/", auth=("any", assigned["DEMO_PASSPHRASE"]))
        assert page.status_code == 200
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


def architecture_names() -> list[str]:
    """Every module and every outside service in ARCHITECTURE.md."""
    text = (ROOT / "docs" / "ARCHITECTURE.md").read_text()
    modules = re.findall(r"^## Module: (\w+)", text, re.MULTILINE)
    diagram = text.split("```mermaid", 1)[1].split("```", 1)[0]
    outside = diagram.split("\n  end\n", 1)[1]
    services = re.findall(r"^\s+\w+\[\(?([^\]:)]+)", outside, re.MULTILINE)
    assert len(modules) == 10 and len(services) == 4
    return modules + services


def test_design_names_every_module_and_outside_service():
    design = readme_section("Design")

    missing = [name for name in architecture_names() if name not in design]

    assert missing == []
