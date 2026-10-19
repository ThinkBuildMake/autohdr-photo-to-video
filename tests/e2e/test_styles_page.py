import pytest

from tests.support.library_rows import stub_presets  # noqa: F401

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("stub_presets")]


def test_styles_page_renders_presets_and_loads_htmx(page, live_server):
    response = page.goto(live_server + "/")

    assert response.status == 200
    assert page.get_by_role("heading", name="Styles").is_visible()
    assert page.get_by_text("Golden hour").first.is_visible()
    assert page.get_by_text("Crisp modern").first.is_visible()
    assert page.evaluate("window.htmx.version").startswith("2.")
