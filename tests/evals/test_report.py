import csv
from pathlib import Path

from app.evals.__main__ import main
from tests.evals.conftest import read_sheet, run_suite
from tests.support.evals_rows import add_cut_check, add_job


def _report(folder: Path, mark, encoding: str = "utf-8") -> str:
    """Fills the sheet with `mark(row)`, runs `evals report` and returns the new report."""
    rows = read_sheet(folder)
    for row in rows:
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
    style, like_reference, text_followed, _worst = [c.strip() for c in line.strip("|").split("|")]
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
