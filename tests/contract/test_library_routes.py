from app.library.stubs import CRISP_MODERN_ID, GOLDEN_HOUR_ID, STUB_SONG_ID

SONG_KEYS = {
    "id", "title", "artist", "licenceCode", "sourceUrl", "durationS", "credit",
}  # fmt: skip
STYLE_KEYS = {
    "id", "name", "authorName", "styleText", "song", "songOffsetS", "fps",
    "demoPhotoshootId", "referenceJobId",
}  # fmt: skip


def test_list_styles(client):
    response = client.get("/api/styles")

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"styles"}
    assert {s["name"] for s in body["styles"]} == {"Golden hour", "Crisp modern"}
    for style in body["styles"]:
        assert set(style) == {"id", "name", "authorName", "styleText", "song", "hasReference"}
        assert set(style["song"]) == SONG_KEYS
        assert style["song"]["licenceCode"] == "BY-NC"


def test_get_style(client):
    response = client.get(f"/api/styles/{GOLDEN_HOUR_ID}")

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"style", "referenceVideoUrl"}
    assert set(body["style"]) == STYLE_KEYS
    assert set(body["style"]["song"]) == SONG_KEYS


def test_get_unknown_style(client):
    response = client.get("/api/styles/nope")

    assert response.status_code == 404
    assert response.json()["error"] == "style_not_found"


def test_list_songs(client):
    response = client.get("/api/songs")

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"songs"}
    assert set(body["songs"][0]) == SONG_KEYS


def test_create_style(client):
    response = client.post(
        "/api/styles",
        json={
            "name": "Moody dusk",
            "authorName": "Sam",
            "styleText": "Dark and slow.",
            "songId": STUB_SONG_ID,
        },
    )

    body = response.json()
    assert response.status_code == 201
    assert set(body) == {"style"}
    assert set(body["style"]) == STYLE_KEYS
    assert body["style"]["name"] == "Moody dusk"


def test_create_style_with_taken_name(client):
    response = client.post(
        "/api/styles",
        json={
            "name": "Golden hour",
            "authorName": "Sam",
            "styleText": "Dark and slow.",
            "songId": STUB_SONG_ID,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"] == "name_taken"


def test_update_style(client):
    response = client.put(f"/api/styles/{CRISP_MODERN_ID}", json={"styleText": "Quicker still."})

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"style"}
    assert set(body["style"]) == STYLE_KEYS
    assert body["style"]["styleText"] == "Quicker still."
