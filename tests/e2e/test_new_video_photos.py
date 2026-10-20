import base64
import json
import re
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
import pytest
from playwright.sync_api import expect

from app.config import reset_settings
from app.files.service import get, head_object, put
from app.jobs import planning
from app.main import create_app
from app.photoshoots import labelling
from app.providers import chat
from tests.photoshoots.conftest import jpeg_bytes, object_keys, put_bytes
from tests.providers.chat.conftest import BASE, TEST_KEY, _chat_answer
from tests.support.fixtures import DEMO_PASSPHRASE, serve

pytestmark = pytest.mark.e2e

MB = 1024 * 1024
LIMIT = 26_214_400

S3 = "https://test-bucket.s3.us-east-1.amazonaws.com/**"
_KEY_RE = re.compile(r"photoshoots/[0-9a-f-]+/[0-9a-f-]+\.jpg")
MOCK_LABELS = (
    ("kitchen", "island with pendants"),
    ("bedroom", "double bed"),
)


def _photo_ids(request: httpx.Request) -> list[str]:
    body = json.loads(request.content)
    ids = []
    for part in body["messages"][0]["content"]:
        text = part.get("text", "") if isinstance(part, dict) else ""
        if text.startswith("photoId: "):
            ids.append(text.removeprefix("photoId: ").strip())
    return ids


def _labels(request: httpx.Request) -> httpx.Response:
    labels = [
        {"photoId": photo_id, "room": room, "subject": subject}
        for photo_id, (room, subject) in zip(_photo_ids(request), MOCK_LABELS, strict=True)
    ]
    return httpx.Response(200, json=_chat_answer(json.dumps({"labels": labels})))


def _failed_label(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, json={"error": {"message": "down"}})


def _parts(body: bytes, content_type: str):
    boundary = content_type.split("boundary=", 1)[1].split(";", 1)[0].strip().strip('"')
    marker = b"--" + boundary.encode()
    for chunk in body.split(marker):
        if chunk in (b"", b"--", b"--\r\n") or not chunk.startswith(b"\r\n"):
            continue
        header, _, data = chunk[2:].partition(b"\r\n\r\n")
        if data.endswith(b"\r\n"):
            data = data[:-2]
        yield header.decode("utf-8", "replace"), data


def _form_file(route) -> tuple[str, bytes, str]:
    header = route.request.headers["content-type"]
    key, data, filename = None, None, ""
    for part_header, part_data in _parts(route.request.post_data_buffer or b"", header):
        if 'name="key"' in part_header:
            key = part_data.decode()
        elif 'name="file"' in part_header:
            data = part_data
            if 'filename="' in part_header:
                filename = part_header.split('filename="', 1)[1].split('"', 1)[0]
    return key, data, filename


def drop_mixed(page, photos: list[tuple[str, bytes]], blanks: list[tuple[str, str, int]]):
    """Drop real JPEG bytes plus browser-allocated files that are refused before upload."""
    payload = {
        "photos": [{"name": name, "b64": base64.b64encode(data).decode()} for name, data in photos],
        "blanks": [{"name": name, "type": kind, "size": size} for name, kind, size in blanks],
    }
    transfer = page.evaluate_handle(
        """payload => {
            const drop = new DataTransfer();
            for (const file of payload.photos) {
                const bytes = Uint8Array.from(atob(file.b64), c => c.charCodeAt(0));
                drop.items.add(new File([bytes], file.name, { type: "image/jpeg" }));
            }
            for (const file of payload.blanks) {
                drop.items.add(
                    new File([new Uint8Array(file.size)], file.name, { type: file.type })
                );
            }
            return drop;
        }""",
        payload,
    )
    page.dispatch_event("#drop-zone", "drop", {"dataTransfer": transfer})


def drop_jpegs(page, photos: list[tuple[str, bytes]]):
    drop_mixed(page, photos, [])


@pytest.fixture
def wired(page, _isolated_environment, bucket, stub_presets, monkeypatch):
    yield from _open(page, monkeypatch, None)


@pytest.fixture
def wired_labels(page, _isolated_environment, bucket, stub_presets, monkeypatch):
    yield from _open(page, monkeypatch, _labels)


@pytest.fixture
def wired_failed(page, _isolated_environment, bucket, stub_presets, monkeypatch):
    yield from _open(page, monkeypatch, _failed_label)


def _open(page, monkeypatch, handler):
    if handler is not None:
        monkeypatch.setenv("FAKE_PROVIDERS", "0")
        monkeypatch.setenv("OPENROUTER_API_KEY", TEST_KEY)
        monkeypatch.setenv("OPENROUTER_BASE_URL", BASE)
        chat.reset_pricing()
        monkeypatch.setattr(chat, "TRANSPORT", httpx.MockTransport(handler))
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    reset_settings()
    state = {"inflate": None, "stored": [], "abort_names": set(), "files_by_name": {}}

    def bucket_route(route):
        if route.request.method == "POST":
            key, data, filename = _form_file(route)
            if filename in state["abort_names"]:
                route.abort()
                return
            # Chromium's intercepted FormData omits a large file part, so a file chosen
            # from disk is copied from that path. Smaller drops are in the body.
            disk = state["files_by_name"].get(filename)
            if state["inflate"] is not None:
                data = b"x" * state["inflate"]
                disk = None
            if disk is not None and len(data or b"") < Path(disk).stat().st_size:
                put(key, disk)
                size = Path(disk).stat().st_size
            else:
                data = data or b""
                put_bytes(key, data)
                size = len(data)
            state["stored"].append((key, size))
            route.fulfill(status=204, headers={"Access-Control-Allow-Origin": "*"})
            return
        key = unquote(urlparse(route.request.url).path).lstrip("/")
        info = head_object(key)
        if info is None:
            route.fulfill(status=404)
            return
        if info["sizeBytes"] > 1_000_000:
            body = jpeg_bytes()
        else:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "object"
                get(key, str(path))
                body = path.read_bytes()
        route.fulfill(
            status=200,
            content_type="image/jpeg",
            body=body,
            headers={"Access-Control-Allow-Origin": "*"},
        )

    def stay_local(route):
        if route.request.url.startswith(("http://127.0.0.1", "http://localhost")):
            route.continue_()
            return
        route.abort()

    page.route("**/*", stay_local)
    page.route(S3, bucket_route)
    with serve(create_app()) as base_url:
        page.goto(base_url + "/new")
        page.bucket_state = state
        yield page
    labelling.wait_idle(timeout=120)
    planning.wait_idle(timeout=30)
    chat.reset_pricing()


def test_three_dropped_photos_land_in_the_bucket(wired):
    picture = jpeg_bytes()
    drop_jpegs(
        wired,
        [(f"photo-{index}.jpg", picture) for index in range(1, 4)],
    )

    expect(wired.locator("#photo-grid .tile")).to_have_count(3)
    keys = object_keys()
    assert len(keys) == 3
    assert len({key.split("/")[1] for key in keys}) == 1
    assert all(_KEY_RE.fullmatch(key) for key in keys)


def test_grid_shows_room_and_subject_from_mocked_openrouter(wired_labels):
    picture = jpeg_bytes()
    drop_jpegs(
        wired_labels,
        [("photo-1.jpg", picture), ("photo-2.jpg", picture)],
    )

    tiles = wired_labels.locator("#photo-grid .tile")
    expect(tiles.nth(0)).to_contain_text("kitchen")
    expect(tiles.nth(0)).to_contain_text("island with pendants")
    expect(tiles.nth(1)).to_contain_text("bedroom")
    expect(tiles.nth(1)).to_contain_text("double bed")


def test_labelling_failure_leaves_the_shoot_usable(wired_failed):
    picture = jpeg_bytes()
    drop_jpegs(wired_failed, [("photo-1.jpg", picture)])

    expect(wired_failed.locator("#label-note")).to_have_text(
        "The rooms are not labelled. The plan will be made from the photos alone."
    )
    expect(wired_failed.locator("#next")).to_be_enabled()
    wired_failed.locator("#start-from").select_option(label="Golden hour")
    wired_failed.locator("#next").click()
    expect(wired_failed.locator("#step-2")).to_be_visible()


def test_bad_files_are_refused_and_not_uploaded(wired):
    picture = jpeg_bytes()
    drop_mixed(
        wired,
        [(f"photo-{index}.jpg", picture) for index in range(1, 4)],
        [("huge.jpg", "image/jpeg", 30 * MB), ("walkthrough.mp4", "video/mp4", 8)],
    )

    refused = wired.locator("#refused")
    expect(refused).to_contain_text("huge.jpg: too large")
    expect(refused).to_contain_text("walkthrough.mp4: wrong type")
    expect(wired.locator("#photo-grid .tile")).to_have_count(3)
    keys = object_keys()
    assert len(keys) == 3
    assert not any(key.endswith(".mp4") for key in keys)
    assert all(head_object(key)["sizeBytes"] != 30 * MB for key in keys)


def test_oversized_object_is_deleted_and_shown_too_large(wired):
    wired.bucket_state["inflate"] = LIMIT + 1
    drop_jpegs(wired, [("photo-1.jpg", jpeg_bytes())])

    expect(wired.locator("#refused")).to_contain_text("too large")
    assert len(wired.bucket_state["stored"]) == 1
    key, size = wired.bucket_state["stored"][0]
    assert size == LIMIT + 1
    assert head_object(key) is None


def test_file_picker_takes_only_jpg_and_png(wired):
    expect(wired.get_by_label("Choose photos")).to_have_attribute("accept", "image/jpeg,image/png")


def test_refused_file_with_the_same_name_as_a_valid_one_is_not_sent(wired):
    picture = jpeg_bytes()
    drop_mixed(wired, [("a.jpg", picture)], [("a.jpg", "image/jpeg", 30 * MB)])

    expect(wired.locator("#photo-grid .tile")).to_have_count(1)
    keys = object_keys()
    assert len(keys) == 1
    assert head_object(keys[0])["sizeBytes"] == len(picture)


def test_bucket_failure_still_completes_and_lists_the_photo(wired):
    wired.bucket_state["abort_names"].add("photo-2.jpg")
    picture = jpeg_bytes()
    drop_jpegs(
        wired,
        [("photo-1.jpg", picture), ("photo-2.jpg", picture)],
    )

    expect(wired.locator("#refused")).to_contain_text("photo-2.jpg: did not arrive")
    expect(wired.locator("#photo-grid .tile")).to_have_count(1)
    assert len(object_keys()) == 1


def test_forty_photos_at_the_size_limit(wired, tmp_path, monkeypatch):
    monkeypatch.setattr(labelling, "start", lambda shoot_id: None)
    wired.set_default_timeout(180_000)
    blob = jpeg_bytes()
    paths = []
    for index in range(40):
        path = tmp_path / f"photo-{index + 1}.jpg"
        with path.open("wb") as handle:
            handle.write(blob)
            handle.write(b"\0" * (LIMIT - len(blob)))
        paths.append(path)
    wired.bucket_state["files_by_name"] = {path.name: str(path) for path in paths}

    wired.locator("#photo-input").set_input_files([str(path) for path in paths])

    expect(wired.locator("#photo-grid .tile")).to_have_count(40)
    keys = object_keys()
    assert len(keys) == 40
    shoot_id = keys[0].split("/")[1]
    assert all(key.startswith(f"photoshoots/{shoot_id}/") and key.endswith(".jpg") for key in keys)
    assert all(head_object(key)["sizeBytes"] == LIMIT for key in keys)
