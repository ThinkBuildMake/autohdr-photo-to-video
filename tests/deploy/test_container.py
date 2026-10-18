import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "Dockerfile").read_text().splitlines()


def test_image_is_the_gpu_free_slim_python():
    froms = [line for line in DOCKERFILE if line.startswith("FROM ")]

    assert froms == ["FROM python:3.13-slim-trixie"]


def test_dockerfile_mentions_no_gpu_stack():
    assert [line for line in DOCKERFILE if re.search(r"nvidia|cuda|gpu", line, re.I)] == []


def test_container_command_runs_honcho_start():
    assert 'CMD ["honcho", "start"]' in DOCKERFILE


def test_lockfile_has_no_torch_or_cuda_packages():
    packages = tomllib.loads((ROOT / "uv.lock").read_text())["package"]
    names = [package["name"] for package in packages]

    assert [n for n in names if n == "torch" or n.startswith("nvidia-") or "cuda" in n] == []


def test_railway_builds_the_dockerfile_and_checks_healthz():
    config = json.loads((ROOT / "railway.json").read_text())

    assert config["build"]["builder"] == "DOCKERFILE"
    assert config["deploy"]["healthcheckPath"] == "/healthz"
    assert config["deploy"]["restartPolicyType"] == "ALWAYS"
