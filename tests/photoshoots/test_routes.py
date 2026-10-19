import time

from sqlalchemy import text

from app.db.base import session_scope
from app.photoshoots import labelling, stubs
from tests.photoshoots.conftest import jpeg_bytes


def _file(name="a.jpg", size=2_097_152, type_="image/jpeg"):
    return {"name": name, "size": size, "type": type_}


def _create(client, files, label="Shoot"):
    response = client.post("/api/photoshoots", json={"label": label, "files": files})
    assert response.status_code == 201
    return response.json()


def _key(body, index):
    return body["uploads"][index]["fields"]["key"]


def _shoot_count():
    with session_scope() as session:
        return session.execute(text("select count(*) from photoshoots")).scalar_one()


def test_three_jpegs_get_three_upload_forms(client):
    body = _create(client, [_file(f"{i}.jpg") for i in range(3)])

    assert body["photoshootId"]
    assert len(body["uploads"]) == 3
    for upload in body["uploads"]:
        assert upload["url"]
        assert (
            upload["fields"]["key"] == f"photoshoots/{body['photoshootId']}/{upload['photoId']}.jpg"
        )
    assert body["refused"] == []
    photos = client.get(f"/api/photoshoots/{body['photoshootId']}").json()["photoshoot"]["photos"]
    assert [(p["position"], p["status"]) for p in photos] == [
        (1, "awaiting_upload"),
        (2, "awaiting_upload"),
        (3, "awaiting_upload"),
    ]


def test_bad_files_refused_with_reasons(client):
    files = [
        _file("big.jpg", size=31_457_280),
        _file("tour.mp4", type_="video/mp4"),
        _file("ok.png", type_="image/png"),
    ]

    body = _create(client, files)

    assert len(body["uploads"]) == 1
    assert body["uploads"][0]["fields"]["key"].endswith(".png")
    assert body["refused"] == [
        {"name": "big.jpg", "reason": "too_large"},
        {"name": "tour.mp4", "reason": "wrong_type"},
    ]
    shoot = client.get(f"/api/photoshoots/{body['photoshootId']}").json()["photoshoot"]
    assert len(shoot["photos"]) == 1


def test_41_files_is_too_many_files(client):
    response = client.post(
        "/api/photoshoots", json={"files": [_file(f"{i}.jpg") for i in range(41)]}
    )

    assert response.status_code == 400
    assert response.json()["error"] == "too_many_files"
    assert _shoot_count() == 0


def test_complete_marks_uploaded_and_missing(client, monkeypatch):
    started = []
    monkeypatch.setattr(labelling, "start", started.append)
    body = _create(client, [_file(f"{i}.jpg") for i in range(3)])
    stubs.BUCKET[_key(body, 0)] = jpeg_bytes()
    stubs.BUCKET[_key(body, 2)] = jpeg_bytes()

    response = client.post(f"/api/photoshoots/{body['photoshootId']}/complete")

    assert response.status_code == 202
    shoot = response.json()["photoshoot"]
    assert shoot["status"] == "labelling"
    assert [p["status"] for p in shoot["photos"]] == ["uploaded", "missing", "uploaded"]
    assert started == [body["photoshootId"]]


def test_oversized_object_deleted(client):
    body = _create(client, [_file()])
    key = _key(body, 0)
    stubs.BUCKET[key] = b"x" * 27_262_976

    response = client.post(f"/api/photoshoots/{body['photoshootId']}/complete")

    assert key not in stubs.BUCKET
    assert response.json()["photoshoot"]["photos"][0]["status"] == "too_large"
    got = client.get(f"/api/photoshoots/{body['photoshootId']}").json()
    assert got["photoshoot"]["photos"][0]["status"] == "too_large"


def test_labels_arrive(client, monkeypatch):
    monkeypatch.setattr(
        stubs,
        "label_photos",
        lambda photos, shoot_id: [
            {"photoId": p["photoId"], "room": "kitchen", "subject": "kitchen island"}
            for p in photos
        ],
    )
    body = _create(client, [_file("a.jpg"), _file("b.jpg")])
    for index in range(2):
        stubs.BUCKET[_key(body, index)] = jpeg_bytes()
    client.post(f"/api/photoshoots/{body['photoshootId']}/complete")

    deadline = time.monotonic() + 5
    while True:
        shoot = client.get(f"/api/photoshoots/{body['photoshootId']}").json()["photoshoot"]
        if shoot["status"] != "labelling" or time.monotonic() > deadline:
            break
        time.sleep(0.05)

    assert shoot["status"] == "ready"
    assert [(p["room"], p["subject"]) for p in shoot["photos"]] == [
        ("kitchen", "kitchen island")
    ] * 2


def test_unknown_shoot_404(client):
    got = client.get("/api/photoshoots/x")
    done = client.post("/api/photoshoots/x/complete")

    assert got.status_code == 404
    assert got.json()["error"] == "photoshoot_not_found"
    assert done.status_code == 404


def test_file_key_never_changes(client, monkeypatch):
    monkeypatch.setattr(labelling, "start", lambda shoot_id: None)
    body = _create(client, [_file("a.jpg"), _file("b.jpg")])
    shoot_id = body["photoshootId"]

    def keys():
        with session_scope() as session:
            return session.execute(
                text("select id, file_key from photos where photoshoot_id=:i order by position"),
                {"i": shoot_id},
            ).all()

    stubs.BUCKET[_key(body, 0)] = jpeg_bytes()
    client.post(f"/api/photoshoots/{shoot_id}/complete")
    first = keys()
    stubs.BUCKET[_key(body, 1)] = jpeg_bytes()
    client.post(f"/api/photoshoots/{shoot_id}/complete")

    assert keys() == first
    assert all(key == f"photoshoots/{shoot_id}/{pid}.jpg" for pid, key in first)
