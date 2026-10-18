from app.photoshoots.stubs import STUB_PHOTOSHOOT_ID

PHOTO_KEYS = {
    "id", "position", "originalName", "contentType", "sizeBytes", "status", "room", "subject",
    "thumbUrl",
}  # fmt: skip


def _file(name="a.jpg", size=1000, type_="image/jpeg"):
    return {"name": name, "size": size, "type": type_}


def test_create_upload(client):
    response = client.post("/api/photoshoots", json={"label": "Shoot", "files": [_file()]})

    body = response.json()
    assert response.status_code == 201
    assert set(body) == {"photoshootId", "uploads", "refused"}
    assert set(body["uploads"][0]) == {"photoId", "name", "url", "fields"}
    assert body["refused"] == []


def test_create_upload_refuses_wrong_type_and_too_large(client):
    files = [_file(), _file("b.gif", type_="image/gif"), _file("c.jpg", size=26_214_401)]

    body = client.post("/api/photoshoots", json={"files": files}).json()

    assert [u["name"] for u in body["uploads"]] == ["a.jpg"]
    assert body["refused"] == [
        {"name": "b.gif", "reason": "wrong_type"},
        {"name": "c.jpg", "reason": "too_large"},
    ]


def test_create_upload_too_many_files(client):
    response = client.post(
        "/api/photoshoots", json={"files": [_file(f"{i}.jpg") for i in range(41)]}
    )

    assert response.status_code == 400
    assert response.json()["error"] == "too_many_files"


def test_create_upload_no_valid_files(client):
    response = client.post("/api/photoshoots", json={"files": [_file("a.gif", type_="image/gif")]})

    assert response.status_code == 400
    assert response.json()["error"] == "no_valid_files"


def test_complete_upload(client):
    response = client.post(f"/api/photoshoots/{STUB_PHOTOSHOOT_ID}/complete")

    body = response.json()
    assert response.status_code == 202
    assert set(body) == {"photoshoot"}
    assert set(body["photoshoot"]) == {"id", "status", "photos"}
    assert set(body["photoshoot"]["photos"][0]) == PHOTO_KEYS


def test_get_photoshoot(client):
    response = client.get(f"/api/photoshoots/{STUB_PHOTOSHOOT_ID}")

    body = response.json()
    assert response.status_code == 200
    assert set(body["photoshoot"]) == {"id", "label", "status", "photos"}
    assert set(body["photoshoot"]["photos"][0]) == PHOTO_KEYS


def test_unknown_photoshoot(client):
    response = client.get("/api/photoshoots/nope")

    assert response.status_code == 404
    assert response.json()["error"] == "photoshoot_not_found"
