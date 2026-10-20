import pytest

pytestmark = pytest.mark.e2e


def test_new_video_asks_for_the_passphrase(browser, live_server):
    context = browser.new_context()
    page = context.new_page()
    try:
        response = page.goto(live_server + "/new")
    finally:
        context.close()

    assert response.status == 401
    assert response.headers["www-authenticate"].startswith("Basic")
