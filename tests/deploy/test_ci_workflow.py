from pathlib import Path

import yaml

WORKFLOW = yaml.safe_load(
    (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text()
)
BRANCH = "claude/dazzling-keller-xgo5vz"


def _commands() -> str:
    return "\n".join(
        step.get("run", "") for job in WORKFLOW["jobs"].values() for step in job["steps"]
    )


def test_runs_on_the_story_branch_main_and_pull_requests():
    triggers = WORKFLOW[True]

    assert triggers["push"]["branches"] == [BRANCH, "main"]
    assert "pull_request" in triggers


def test_gate_runs_ruff_both_pytest_suites_chromium_and_docker_build():
    commands = _commands()

    assert "ruff check" in commands
    assert 'pytest -m "not e2e"' in commands
    assert "playwright install --with-deps chromium" in commands
    assert "pytest -m e2e" in commands
    assert "docker build" in commands


def test_nothing_is_allowed_to_fail_or_cancel():
    jobs = WORKFLOW["jobs"].values()

    assert not any(job.get("continue-on-error") for job in jobs)
    assert not any(step.get("continue-on-error") for job in jobs for step in job["steps"])
    assert "cancel-in-progress" not in str(WORKFLOW.get("concurrency", ""))
