import re
from pathlib import Path

from tests.support.markdown import sections

ROOT = Path(__file__).resolve().parents[2]
DEMO = (ROOT / "docs" / "DEMO.md").read_text()
PASSPHRASE_FILE = Path.home() / ".autohdr-demo-passphrase"


def test_sections_come_in_order():
    headings = [h for h in sections(DEMO) if re.match(r"\d\.", h)]

    assert headings == [
        "0. Before the rehearsal",
        "1. Live clip check (paid)",
        "2. Live flow",
        "3. Pre-made demo job (offline copy)",
        "4. Freeze deploys",
        "5. Screen pass against the wireframe",
    ]


FLOW = DEMO[DEMO.index("## 2. Live flow") : DEMO.index("## 3.")]


def test_live_flow_names_every_stage_in_order():
    flow = FLOW.lower()
    stages = ["preset", "upload", "plan", "make my video", "play", "re-export", "comparison"]

    positions = [flow.index(stage) for stage in stages]

    assert positions == sorted(positions)


def test_paid_commands_and_freeze_steps_are_written_down():
    assert "OPENROUTER_LIVE=1" in DEMO
    assert "scripts/demo_video.py fetch" in DEMO
    assert "scripts/demo_video.py verify" in DEMO
    assert "/healthz" in DEMO
    freeze = sections(DEMO)["4. Freeze deploys"]
    assert "no connected source" in freeze
    assert "Push a commit" in freeze


def test_referenced_repo_paths_exist():
    paths = re.findall(r"(?:scripts|tests|docs)/[\w./-]+\.(?:py|md|html)", DEMO)

    assert paths
    assert [p for p in paths if not (ROOT / p).exists()] == []


def test_no_secret_is_in_the_doc():
    if PASSPHRASE_FILE.exists():
        assert PASSPHRASE_FILE.read_text().strip() not in DEMO
    assert not re.search(r"sk-[A-Za-z0-9_-]{10,}|OPENROUTER_API_KEY=\S+", DEMO)


def test_screen_pass_names_the_wireframe_link_and_screens():
    body = sections(DEMO)["5. Screen pass against the wireframe"]

    assert "https://claude.ai/artifact/Y9f7bkitn6dqRLvP5sN5vH" in body
    assert ".lazy" not in DEMO
    for screen in [
        "Styles",
        "New video",
        "Jobs",
        "Job",
        "Editor",
        "Create a style",
        "Reference and reproduction",
        "Redo this shot",
        "Re-exporting banner",
        "Play both",
    ]:
        assert screen in body


APP = ROOT / "app"
APP_UI = "".join(
    p.read_text()
    for d in ("web/templates", "web/static")
    for p in (APP / d).rglob("*")
    if p.is_file()
)
APP_ROUTES = {
    re.sub(r"\{[^}]*\}", "{}", m)
    for p in (APP / "web" / "pages").glob("*.py")
    for m in re.findall(r'@router\.get\("([^"]*)"', p.read_text())
}


def test_every_quoted_label_in_the_live_flow_exists_in_the_app():
    flow = FLOW
    labels = re.findall(r'"([^"]+)"', flow)

    assert labels
    assert [t for t in labels if t not in APP_UI] == []


def test_every_page_route_in_the_live_flow_exists_in_the_app():
    flow = FLOW
    routes = {re.sub(r"\{[^}]*\}", "{}", r.split("?")[0]) for r in re.findall(r"`(/[^`]*)`", flow)}

    assert {"/new", "/styles/new", "/styles/{}/reproductions"} <= routes
    assert routes - APP_ROUTES == set()


def test_part_b_makes_the_reproduction_before_viewing_it():
    part_b = FLOW[FLOW.index("### B.") :]

    starts = part_b.index('"Start the reproduction"')
    makes = part_b.index('"Make my video"', starts)
    assert makes < part_b.index('"See reproductions"', makes)
