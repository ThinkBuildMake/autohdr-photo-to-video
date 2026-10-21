import shutil
import subprocess

from app.evals.report import fill_readme
from tests.docs.test_readme import README, ROOT, readme_section

COMMAND = "python -m app.evals all --folder ../test-shoots --yes"


def test_results_section_gives_the_command_and_claims_no_numbers():
    section = readme_section("Results on the 12 test shoots")

    assert COMMAND in section and "report --sheet" in section and "--readme README.md" in section
    assert "no paid run has been recorded yet" in section
    assert "Placeholder" not in section and "go-ahead" in section


def test_filling_the_results_keeps_every_other_section(tmp_path):
    copy = tmp_path / "README.md"
    shutil.copy(README, copy)

    fill_readme(copy, "# Evals report\n\n## Videos\n\n| a |\n", [tmp_path / "sheet.csv"])

    text = copy.read_text()
    assert "### Videos" in text and "no paid run" not in text
    assert (
        text.split("## Results on the 12 test shoots")[0]
        == README.read_text().split("## Results on the 12 test shoots")[0]
    )
    assert "## Documents" in text


def test_reports_under_evals_are_git_ignored():
    done = subprocess.run(["git", "check-ignore", "evals/reports/x"], cwd=ROOT)

    assert done.returncode == 0


def test_only_the_root_reports_folder_is_ignored():
    def ignored(path):
        return subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0

    assert ignored("evals/reports/x")
    assert not ignored("app/evals/x.py") and not ignored("tests/evals/x.py")
