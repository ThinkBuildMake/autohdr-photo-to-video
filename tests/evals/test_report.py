import csv
from pathlib import Path

import pytest

from app.evals.__main__ import main
from app.evals.runs import COLUMNS
from tests.evals.conftest import read_sheet, run_suite
from tests.support.evals_rows import add_cut_check, add_job


def _report(folder: Path, mark, encoding: str = "utf-8", reviewed: bool = True) -> str:
    """Fills the sheet with `mark(row)` (every delivered shot reviewed "no" first, unless
    `reviewed` is off), runs `evals report` and returns the new report."""
    rows = read_sheet(folder)
    for row in rows:
        if reviewed and row["kind"] == "attempt" and row["in_video"] == "yes":
            for column in ("visibly_ai", "room_changed", "movement_matches", "transition_matches"):
                row[column] = "no"
        if reviewed and row["kind"] == "plan":
            row["text_followed"] = "no"
        if reviewed and row["kind"] == "reproduction":
            row["looks_like_reference"] = "no"
        mark(row)
    sheet = folder / "sheet.csv"
    with open(sheet, "w", newline="", encoding=encoding) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    before = set(folder.glob("report-*.md"))
    assert main(["report", "--sheet", str(sheet)]) == 0
    (new,) = set(folder.glob("report-*.md")) - before
    return new.read_text()


def _video_row(report: str, video: int) -> list[str]:
    (line,) = [line for line in report.splitlines() if line.startswith(f"| {video} |")]
    return [cell.strip() for cell in line.strip("|").split("|")]


def test_report_counts_the_filled_sheet_per_video(world, fake_jobs):
    job = add_job(
        world.shoots[0],
        world.song,
        world.style,
        minutes=9,
        shots=[["flagged", "passed"], ["passed"], ["passed"], ["passed"]],
    )
    add_cut_check(job, 1, 0.04)
    add_cut_check(job, 2, -0.07)
    fake_jobs.by_shoot[world.shoots[0]] = job
    folder = run_suite(world, "ev1")

    def mark(row):
        if row["kind"] != "attempt":
            return
        if row["position"] in ("1", "2"):
            row["visibly_ai"] = "yes"
        if row["position"] == "3" and row["in_video"] == "yes":
            row["room_changed"] = "x"

    report = _report(folder, mark)

    video, shoot, _style, _job, status, visibly_ai, rooms, _moves, _cuts, worst, time = _video_row(
        report, 1
    )
    assert (video, shoot, status) == ("1", "Shoot 01", "ready")
    assert visibly_ai == "2"
    assert rooms == "1"
    assert worst == "0.070 s"
    assert time == "9.0 min"


def test_report_gives_the_median_job_time(world, fake_jobs):
    for shoot, minutes in zip(world.shoots, (8, 10, 14), strict=False):
        fake_jobs.by_shoot[shoot] = add_job(shoot, world.song, world.style, minutes=minutes)
    folder = run_suite(world, "ev1")

    report = _report(folder, lambda row: None)

    assert "Median job time: 10.0 min" in report


def test_stopped_job_is_listed_and_the_rest_reported(world, fake_jobs):
    for n, shoot in enumerate(world.shoots, start=1):
        stopped = n == 4
        fake_jobs.by_shoot[shoot] = add_job(
            shoot,
            world.song,
            world.style,
            status="stopped" if stopped else "ready",
            stop_reason="out_of_credit" if stopped else None,
            minutes=None if stopped else 10,
        )
    folder = run_suite(world, "ev1")

    report = _report(folder, lambda row: None)

    assert _video_row(report, 4)[4] == "stopped (out_of_credit)"
    assert "- Video 4 (Shoot 04): out_of_credit" in report
    others = [_video_row(report, n) for n in range(1, 13) if n != 4]
    assert all(row[4] == "ready" and row[-1] == "10.0 min" for row in others)


def _seed_two_reproductions(world, fake_jobs) -> None:
    for shoot in world.shoots[1:3]:
        fake_jobs.by_shoot[shoot] = add_job(
            shoot, world.song, world.style, purpose="reproduction", shots=[["passed"]]
        )


def test_report_gives_the_style_checks(world, fake_jobs):
    _seed_two_reproductions(world, fake_jobs)
    folder = run_suite(world, "ev2")

    def mark(row):
        if row["kind"] == "plan":
            row["text_followed"] = "yes"
        if row["kind"] == "reproduction":
            row["looks_like_reference"] = "yes" if row["video"] == "1" else "no"

    report = _report(folder, mark)

    (line,) = [line for line in report.splitlines() if line.startswith("| Golden hour |")]
    style, like_reference, text_followed, *_ = [c.strip() for c in line.strip("|").split("|")]
    assert like_reference == "1 of 2"
    assert text_followed == "2 of 2"


def test_report_shows_the_check_catch_rate(world, fake_jobs):
    job = add_job(
        world.shoots[0],
        world.song,
        world.style,
        shots=[["flagged", "passed"]] * 4 + [["passed"]] * 4,
    )
    fake_jobs.by_shoot[world.shoots[0]] = job
    folder = run_suite(world, "ev1")

    def mark(row):
        if row["kind"] != "attempt":
            return
        position = int(row["position"])
        if row["flagged"] == "yes" and position <= 3:
            row["visibly_ai"] = "yes"
        if position in (5, 6):
            row["room_changed"] = "yes"

    report = _report(folder, mark)

    assert "3 of 5 caught" in report


def test_report_folder_holds_only_text_files(world, fake_jobs):
    _seed_two_reproductions(world, fake_jobs)
    folder = run_suite(world, "ev2")
    _report(folder, lambda row: None)

    files = [p for p in world.out.rglob("*") if p.is_file()]

    assert {p.name for p in folder.iterdir()} >= {"sheet.csv"}
    assert len(list(folder.glob("report-*.md"))) == 2
    assert {p.suffix for p in files} <= {".csv", ".md", ".json"}
    for path in files:
        head = path.read_bytes()[:4]
        assert not head.startswith(b"\xff\xd8")
        assert head != b"\x89PNG"
        path.read_text()


def _seed_catch_rate(world, fake_jobs) -> None:
    fake_jobs.by_shoot[world.shoots[0]] = add_job(
        world.shoots[0], world.song, world.style, shots=[["flagged", "passed"]] * 2
    )


def test_report_reads_a_sheet_saved_with_a_byte_order_mark(world, fake_jobs):
    _seed_catch_rate(world, fake_jobs)
    folder = run_suite(world, "ev1")

    report = _report(folder, lambda row: None, encoding="utf-8-sig")

    assert _video_row(report, 1)[1] == "Shoot 01"


def test_report_reads_yes_cells_in_any_case(world, fake_jobs):
    _seed_catch_rate(world, fake_jobs)
    folder = run_suite(world, "ev1")

    def mark(row):
        if row["kind"] == "attempt" and row["flagged"] == "yes":
            row["flagged"] = "Yes"
            row["visibly_ai"] = "YES"

    report = _report(folder, mark)

    assert "2 of 2 caught" in report


def _cells(report: str, start: str) -> list[str]:
    (line,) = [line for line in report.splitlines() if line.startswith(start)]
    return [c.strip() for c in line.strip("|").split("|")]


def test_two_sheets_with_the_same_video_numbers_stay_apart(world, fake_jobs):
    from app.evals.report import render

    first = run_suite(world, "ev1")
    _seed_two_reproductions(world, fake_jobs)
    assert main(["run", "--suite", "ev2", "--style", "Golden hour", "--out", str(world.out)]) == 0
    (second,) = [p for p in world.out.iterdir() if p.is_dir() and p != first]
    rows = read_sheet(first) + read_sheet(second)

    report = render(rows)

    videos = [line for line in report.splitlines() if line.startswith("| 1 |")]
    assert len(videos) == 2
    assert len({r["job_id"] for r in rows}) == 14


def test_a_null_cut_on_a_plain_cut_counts_as_a_failure(world, fake_jobs):
    job = add_job(world.shoots[0], world.song, world.style, shots=[["passed"], ["passed"]])
    add_cut_check(job, 1, 0.02)
    add_cut_check(job, 2, None)
    fake_jobs.by_shoot[world.shoots[0]] = job
    folder = run_suite(world, "ev1")

    report = _report(folder, lambda row: None)

    assert _video_row(report, 1)[9] == "0.020 s, cut not measured"


def test_a_job_with_no_cut_rows_and_several_shots_fails_the_cut_check(world, fake_jobs):
    fake_jobs.by_shoot[world.shoots[0]] = add_job(
        world.shoots[0], world.song, world.style, shots=[["passed"], ["passed"]]
    )
    folder = run_suite(world, "ev1")

    assert "cut not measured" in _video_row(_report(folder, lambda row: None), 1)[9]


def test_blank_marks_on_delivered_shots_are_listed_and_exit_two(world, fake_jobs, capsys):
    fake_jobs.by_shoot[world.shoots[0]] = add_job(
        world.shoots[0], world.song, world.style, shots=[["passed"], ["passed"]]
    )
    folder = run_suite(world, "ev1")
    rows = read_sheet(folder)
    for row in rows:
        if row["position"] == "1" and row["kind"] == "attempt":
            row["visibly_ai"] = row["room_changed"] = "no"
    sheet = folder / "sheet.csv"
    with open(sheet, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    assert main(["report", "--sheet", str(sheet)]) == 2

    assert "rows are not reviewed yet" in capsys.readouterr().out
    report = max(folder.glob("report-*.md")).read_text()
    assert report.split("## Unreviewed")[1].count("- Video 1 (Shoot 01), attempt 2") == 1


README_TEXT = "# Top\n\nintro\n\n## Results on the 12 test shoots\n\nOLDTEXT\n\n## After\n\nkept\n"


def _write(sheet, rows) -> None:
    with open(sheet, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _run_both_suites(world, fake_jobs, videos: int = 12) -> list:
    """An EV-1 sheet with `videos` delivered videos and an EV-2 sheet, every mark filled in."""
    for shoot in world.shoots[:videos]:
        fake_jobs.by_shoot[shoot] = add_job(shoot, world.song, world.style, shots=[["passed"]])
    ev1 = run_suite(world, "ev1")
    fake_jobs.by_shoot.clear()
    assert main(["run", "--suite", "ev2", "--style", "Golden hour", "--out", str(world.out)]) == 0
    sheets = [p / "sheet.csv" for p in sorted(world.out.iterdir()) if p.is_dir()]
    assert ev1 / "sheet.csv" in sheets
    for sheet in sheets:
        rows = read_sheet(sheet.parent)
        for row in rows:
            for column in (*MARKS_COLUMNS, "text_followed", "looks_like_reference"):
                row[column] = "no"
        _write(sheet, rows)
    return sheets


MARKS_COLUMNS = ("visibly_ai", "room_changed", "movement_matches", "transition_matches")


def _mark_real(sheets) -> None:
    for sheet in sheets:
        rows = read_sheet(sheet.parent)
        for row in rows:
            row["providers"] = "real"
        _write(sheet, rows)


def _fill(sheets, tmp_path) -> tuple:
    readme = tmp_path / "README.md"
    readme.write_text(README_TEXT)
    args = [a for sheet in sheets for a in ("--sheet", str(sheet))]
    return main(["report", *args, "--readme", str(readme)]), readme


def test_readme_fill_replaces_only_its_section_and_repeats_cleanly(world, fake_jobs, tmp_path):
    sheets = _run_both_suites(world, fake_jobs)
    _mark_real(sheets)

    code, readme = _fill(sheets, tmp_path)
    once = readme.read_text()
    assert _fill(sheets, tmp_path)[0] == 0 and code == 0
    readme.write_text(once)
    assert (
        main(
            [
                "report",
                "--sheet",
                str(sheets[0]),
                "--sheet",
                str(sheets[1]),
                "--readme",
                str(readme),
            ]
        )
        == 0
    )

    assert readme.read_text() == once
    assert once.startswith("# Top\n\nintro\n\n## Results on the 12 test shoots\n\nPaid run by `")
    assert "### Videos" in once and "### Styles" in once and "OLDTEXT" not in once
    assert once.endswith("\n\n## After\n\nkept\n")


def test_a_mock_run_sheet_cannot_fill_the_readme(world, fake_jobs, tmp_path, capsys):
    sheets = _run_both_suites(world, fake_jobs)  # made under FAKE_PROVIDERS: marked fake

    code, readme = _fill(sheets, tmp_path)

    assert code == 2 and "real providers" in capsys.readouterr().out
    assert "OLDTEXT" in readme.read_text()


def test_a_one_video_sheet_cannot_fill_the_readme(world, fake_jobs, tmp_path, capsys):
    sheets = _run_both_suites(world, fake_jobs, videos=1)
    _mark_real(sheets)

    code, readme = _fill(sheets, tmp_path)

    assert code == 2 and "12" in capsys.readouterr().out
    assert "OLDTEXT" in readme.read_text()


def test_a_sheet_with_no_reproduction_cannot_fill_the_readme(world, fake_jobs, tmp_path, capsys):
    sheets = _run_both_suites(world, fake_jobs)[:1]
    _mark_real(sheets)

    code, readme = _fill(sheets, tmp_path)

    assert code == 2 and "reproduction" in capsys.readouterr().out
    assert "OLDTEXT" in readme.read_text()


def test_a_sheet_missing_a_mark_column_says_which(world, fake_jobs, tmp_path):
    sheet = run_suite(world, "ev1") / "sheet.csv"
    rows = read_sheet(sheet.parent)
    for row in rows:
        del row["room_changed"]
    _write(sheet, rows)

    with pytest.raises(SystemExit) as stopped:
        main(["report", "--sheet", str(sheet)])

    assert "room_changed" in str(stopped.value.code)


def test_readme_is_left_alone_while_shots_are_unreviewed(world, fake_jobs, tmp_path, capsys):
    fake_jobs.by_shoot[world.shoots[0]] = add_job(
        world.shoots[0], world.song, world.style, shots=[["passed"]]
    )
    folder = run_suite(world, "ev1")
    readme = tmp_path / "README.md"
    readme.write_text("## Results on the 12 test shoots\n\nold\n")

    assert main(["report", "--sheet", str(folder / "sheet.csv"), "--readme", str(readme)]) == 2

    assert readme.read_text().endswith("old\n")


def test_a_blank_plan_mark_blocks_the_readme(world, fake_jobs, tmp_path):
    fake_jobs.by_shoot[world.shoots[0]] = add_job(
        world.shoots[0], world.song, world.style, shots=[["passed"]]
    )
    folder = run_suite(world, "ev1")
    rows = read_sheet(folder)
    for row in rows:
        if row["kind"] == "attempt":
            for c in ("visibly_ai", "room_changed", "movement_matches", "transition_matches"):
                row[c] = "no"
    sheet = folder / "sheet.csv"
    with open(sheet, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    readme = tmp_path / "README.md"
    readme.write_text("## Results on the 12 test shoots\n\nKEEP\n")

    assert main(["report", "--sheet", str(sheet), "--readme", str(readme)]) == 2
    assert "KEEP" in readme.read_text()


def test_an_empty_sheet_does_not_fill_the_readme(tmp_path, capsys):
    sheet = tmp_path / "sheet.csv"
    sheet.write_text(",".join(COLUMNS) + "\n")
    readme = tmp_path / "README.md"
    readme.write_text("## Results on the 12 test shoots\n\nKEEP\n")

    assert main(["report", "--sheet", str(sheet), "--readme", str(readme)]) == 2

    assert "no delivered videos" in capsys.readouterr().out
    assert "KEEP" in readme.read_text()


def test_a_stopped_job_that_never_assembled_says_so(world, fake_jobs):
    fake_jobs.by_shoot[world.shoots[0]] = add_job(
        world.shoots[0],
        world.song,
        world.style,
        status="stopped",
        stop_reason="out_of_credit",
        minutes=None,
        shots=[["error"], ["error"]],
    )
    folder = run_suite(world, "ev1")

    assert _video_row(_report(folder, lambda row: None), 1)[9] == "not assembled"
