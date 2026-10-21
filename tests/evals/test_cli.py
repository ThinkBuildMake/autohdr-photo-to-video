import pytest

from app.evals import runs
from app.evals.__main__ import build_parser, main
from tests.evals.conftest import STYLE


def test_all_without_yes_prints_the_cost_and_creates_no_job(world, fake_jobs, tmp_path, capsys):
    assert main(["all", "--folder", str(tmp_path / "shoots"), "--out", str(world.out)]) == 1

    out = capsys.readouterr().out
    assert "14 real, paid jobs" in out
    assert fake_jobs.created == []


def test_all_with_yes_runs_ev1_and_each_reference_style(world, fake_jobs, tmp_path, capsys):
    shoots = tmp_path / "shoots"  # the world's shoots are already imported and reused
    code = main(["all", "--folder", str(shoots), "--out", str(world.out), "--yes"])

    assert code == 0
    out = capsys.readouterr().out
    assert out.count("reviewer sheet:") == 2
    assert "--readme README.md" in out
    assert len(fake_jobs.created) == 14


def test_links_and_timeout_parse():
    args = build_parser().parse_args(
        ["run", "--suite", "ev1", "--style", STYLE, "--timeout-min", "5"]
    )
    assert args.timeout_min == 5
    assert build_parser().parse_args(["links", "--sheet", "s.csv"]).command == "links"
    with pytest.raises(SystemExit):
        build_parser().parse_args(["report"])


def test_links_writes_a_fresh_sheet_and_does_not_stack_suffixes(world, fake_jobs, capsys):
    from tests.evals.conftest import run_suite

    folder = run_suite(world, "ev1")
    sheet = folder / "sheet.csv"
    assert main(["links", "--sheet", str(sheet)]) == 0
    relinked = folder / "sheet-relinked.csv"
    assert relinked.exists()
    assert main(["links", "--sheet", str(relinked)]) == 0
    assert not (folder / "sheet-relinked-relinked.csv").exists()


def test_all_counts_the_ev1_jobs_from_the_folder(world, fake_jobs, tmp_path, capsys):
    (tmp_path / "shoots" / "Shoot 13").mkdir()

    assert main(["all", "--folder", str(tmp_path / "shoots"), "--out", str(world.out)]) == 1

    assert "15 real, paid jobs (13 EV-1" in capsys.readouterr().out


def test_all_still_runs_the_later_suites_when_one_times_out(
    world, fake_jobs, tmp_path, capsys, monkeypatch
):
    real = runs.run_suite

    def flaky(suite, *args):
        if suite == "ev1":
            raise SystemExit("Timed out after 1 minutes; sheet in somewhere.")
        return real(suite, *args)

    monkeypatch.setattr("app.evals.__main__.run_suite", flaky)

    code = main(["all", "--folder", str(tmp_path / "shoots"), "--out", str(world.out), "--yes"])

    out = capsys.readouterr().out
    assert code == 1 and "Timed out" in out and out.count("reviewer sheet:") == 1
