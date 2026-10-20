import inspect
import threading
import time

import httpx
from fastapi.routing import APIRoute

from app.main import create_app
from app.photoshoots import service as photoshoots
from tests.support.fixtures import DEMO_AUTH


def test_slow_bucket_call_does_not_block_health(live_server, monkeypatch):
    import app.files.service as files

    started = threading.Event()
    original = photoshoots.complete_upload

    def slow_head_object(key):
        started.set()
        time.sleep(5)

    def slow_complete_upload(photoshoot_id):
        files.head_object("photoshoots/stub/photo.jpg")
        return original(photoshoot_id)

    monkeypatch.setattr(files, "head_object", slow_head_object)
    monkeypatch.setattr(photoshoots, "complete_upload", slow_complete_upload)
    created = httpx.post(
        f"{live_server}/api/photoshoots",
        json={"files": [{"name": "a.jpg", "size": 1000, "type": "image/jpeg"}]},
        auth=DEMO_AUTH,
    )
    photoshoot_id = created.json()["photoshootId"]
    result = {}

    def call():
        result["response"] = httpx.post(
            f"{live_server}/api/photoshoots/{photoshoot_id}/complete",
            auth=DEMO_AUTH,
            timeout=30,
        )

    worker = threading.Thread(target=call)
    worker.start()
    assert started.wait(5)
    time.sleep(0.2)

    begun = time.monotonic()
    health = httpx.get(f"{live_server}/healthz", timeout=5)
    took = time.monotonic() - begun

    assert health.status_code == 200
    assert took < 1
    assert worker.is_alive()
    worker.join(timeout=15)
    assert result["response"].status_code == 202


def _api_routes(routes):
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):
            yield from _api_routes(route.original_router.routes)


def test_no_route_handler_is_async():
    routes = list(_api_routes(create_app().routes))

    assert len(routes) == 30  # 22 API routes, /healthz and 7 pages
    assert [r.path for r in routes if inspect.iscoroutinefunction(r.endpoint)] == []
