from pathlib import Path

from tests.support.markdown import sections

ROOT = Path(__file__).resolve().parents[2]
SCALING = ROOT / "docs" / "SCALING.md"


def next_pieces() -> list[tuple[str, str]]:
    """(Next piece, Add when) per row of HIGH_LEVEL_DESIGN.md §5 "What to add next"."""
    hld = sections((ROOT / "docs" / "HIGH_LEVEL_DESIGN.md").read_text())["What to add next"]
    rows = [line.strip("|").split("|") for line in hld.splitlines() if line.startswith("|")]
    return [(cells[0].strip(), cells[2].strip()) for cells in rows[2:]]


def test_n_jobs_section_keeps_the_limit_and_the_outputs():
    found = [
        body
        for heading, body in sections(SCALING.read_text()).items()
        if "N jobs at once" in heading
    ]

    assert len(found) == 1
    body = found[0]
    assert "the 30 min limit of PF-1" in body
    assert "outputs stay the same" in body
    assert "first_finished_at − jobs.first_submitted_at" in body
    assert "can miss PF-1" in body


def test_queue_wait_includes_jobs_that_have_not_started():
    body = next(
        body for heading, body in sections(SCALING.read_text()).items() if "Real queue" in heading
    )
    assert "has not started" in body
    assert "now − `jobs.submitted_at`" in body
    assert "`jobs.started_at − jobs.submitted_at`" in body


def test_one_section_per_next_piece_quoting_its_trigger():
    scaling = sections(SCALING.read_text())
    pieces = next_pieces()

    assert len(pieces) == 2
    for piece, trigger in pieces:
        found = [body for heading, body in scaling.items() if piece in heading]
        assert len(found) == 1, piece
        assert trigger in found[0], piece
