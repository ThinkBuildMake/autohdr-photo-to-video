import pytest

from tests.support.library_rows import add_song

SONG_KEYS = {
    "id", "title", "artist", "licenceCode", "sourceUrl", "durationS", "credit",
}  # fmt: skip
STYLE_KEYS = {
    "id", "name", "authorName", "styleText", "song", "songOffsetS", "fps",
    "demoPhotoshootId", "referenceJobId",
}  # fmt: skip
SUMMARY_KEYS = {"id", "name", "authorName", "styleText", "song", "hasReference"}


def _body(song_id, **over):
    return {
        "name": "Golden hour",
        "authorName": "Sam",
        "styleText": "Slow and warm, ending on a wide exterior.",
        "songId": song_id,
        **over,
    }


def _create(client, song_id, **over):
    return client.post("/api/styles", json=_body(song_id, **over))


def test_create_style_answers_201_with_fps_30_and_no_reference(client):
    song_id = add_song()

    response = _create(client, song_id)

    body = response.json()
    assert response.status_code == 201
    assert set(body) == {"style"}
    assert set(body["style"]) == STYLE_KEYS
    assert body["style"]["name"] == "Golden hour"
    assert body["style"]["authorName"] == "Sam"
    assert body["style"]["song"]["id"] == song_id
    assert body["style"]["fps"] == 30
    assert body["style"]["referenceJobId"] is None
    detail = client.get(f"/api/styles/{body['style']['id']}").json()
    assert detail["referenceVideoUrl"] is None


def test_list_styles_shows_author_text_song_and_no_reference(client):
    song_id = add_song()
    _create(client, song_id)

    response = client.get("/api/styles")

    styles = response.json()["styles"]
    assert response.status_code == 200
    assert len(styles) == 1
    assert set(styles[0]) == SUMMARY_KEYS
    assert styles[0]["name"] == "Golden hour"
    assert styles[0]["authorName"] == "Sam"
    assert styles[0]["styleText"] == "Slow and warm, ending on a wide exterior."
    assert styles[0]["song"]["title"] == "Track A"
    assert styles[0]["song"]["licenceCode"] == "BY-NC"
    assert styles[0]["hasReference"] is False


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_style_text_is_invalid_style(client, text):
    song_id = add_song()

    response = _create(client, song_id, styleText=text)

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_style"
    assert client.get("/api/styles").json()["styles"] == []


def test_fps_25_is_invalid_style(client):
    song_id = add_song()

    response = _create(client, song_id, fps=25)

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_style"
    assert client.get("/api/styles").json()["styles"] == []


def test_fps_24_is_accepted(client):
    song_id = add_song()

    response = _create(client, song_id, fps=24)

    assert response.status_code == 201
    assert response.json()["style"]["fps"] == 24


def test_taken_name_is_409_on_create(client):
    song_id = add_song()
    _create(client, song_id)

    response = _create(client, song_id, authorName="Lee")

    assert response.status_code == 409
    assert response.json()["error"] == "name_taken"
    assert len(client.get("/api/styles").json()["styles"]) == 1


def test_taken_name_is_409_on_rename(client):
    song_id = add_song()
    _create(client, song_id)
    other = _create(client, song_id, name="Crisp modern").json()["style"]["id"]

    response = client.put(f"/api/styles/{other}", json={"name": "Golden hour"})

    assert response.status_code == 409
    assert response.json()["error"] == "name_taken"


def test_keeping_its_own_name_on_update_is_allowed(client):
    song_id = add_song()
    style_id = _create(client, song_id).json()["style"]["id"]

    response = client.put(f"/api/styles/{style_id}", json={"name": "Golden hour"})

    assert response.status_code == 200


def test_edited_text_is_returned_by_get(client):
    song_id = add_song()
    style_id = _create(client, song_id).json()["style"]["id"]

    put = client.put(f"/api/styles/{style_id}", json={"styleText": "Faster, with hard cuts."})

    assert put.status_code == 200
    assert put.json()["style"]["styleText"] == "Faster, with hard cuts."
    body = client.get(f"/api/styles/{style_id}").json()
    assert set(body) == {"style", "referenceVideoUrl"}
    assert body["style"]["styleText"] == "Faster, with hard cuts."
    assert body["style"]["name"] == "Golden hour"
    assert body["style"]["song"]["id"] == song_id
    assert body["style"]["fps"] == 30


def test_update_refuses_invalid_fps_and_empty_text(client):
    song_id = add_song()
    style_id = _create(client, song_id).json()["style"]["id"]

    assert client.put(f"/api/styles/{style_id}", json={"fps": 25}).status_code == 400
    blank = client.put(f"/api/styles/{style_id}", json={"styleText": "  "})
    assert blank.json()["error"] == "invalid_style"


def test_unknown_style_is_404_on_get(client):
    response = client.get("/api/styles/x")

    assert response.status_code == 404
    assert response.json()["error"] == "style_not_found"
    assert "x" in response.json()["message"]


def test_unknown_style_is_404_on_put(client):
    response = client.put("/api/styles/x", json={"styleText": "Anything."})

    assert response.status_code == 404
    assert response.json()["error"] == "style_not_found"


def test_unknown_song_is_404_song_not_found(client):
    response = _create(client, "no-such-song")

    assert response.status_code == 404
    assert response.json()["error"] == "song_not_found"


def test_unknown_demo_photoshoot_is_404(client):
    song_id = add_song()

    response = _create(client, song_id, demoPhotoshootId="no-such-shoot")

    assert response.status_code == 404
    assert response.json()["error"] == "photoshoot_not_found"


def test_list_songs_has_licence_source_and_credit(client):
    add_song(source_url="https://example.com/music/track-a")

    response = client.get("/api/songs")

    songs = response.json()["songs"]
    assert response.status_code == 200
    assert set(response.json()) == {"songs"}
    assert len(songs) == 1
    assert set(songs[0]) == SONG_KEYS
    assert songs[0]["credit"] == "Track A, Artist A, CC BY-NC, https://example.com/music/track-a"
