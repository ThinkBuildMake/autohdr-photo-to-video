import json

import pytest

from app.library.seed import main

URL_A = "https://freemusicarchive.org/music/artist-a/track-a"


def _track(title="Track A", licence="BY-NC", url=URL_A, **extra):
    return {
        "title": title,
        "artist": "Artist A",
        "licence": licence,
        "sourceUrl": url,
        "fileKey": "songs/" + title.lower().replace(" ", "-") + ".mp3",
        "durationS": 95,
        **extra,
    }


def _manifest(tmp_path, tracks):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"tracks": tracks}))
    return str(path)


def test_seed_adds_track_a_with_licence_source_and_credit(tmp_path, client):
    assert main(["--manifest", _manifest(tmp_path, [_track()])]) == 0

    songs = client.get("/api/songs").json()["songs"]
    assert len(songs) == 1
    assert songs[0]["title"] == "Track A"
    assert songs[0]["artist"] == "Artist A"
    assert songs[0]["licenceCode"] == "BY-NC"
    assert songs[0]["sourceUrl"] == URL_A
    assert songs[0]["credit"] == f"Track A, Artist A, CC BY-NC, {URL_A}"


def test_no_derivatives_track_is_refused_and_named(tmp_path, client, capsys):
    tracks = [_track(), _track("Track B", "BY-NC-ND", "https://example.com/track-b")]

    assert main(["--manifest", _manifest(tmp_path, tracks)]) == 1

    out = capsys.readouterr()
    assert "Track B" in out.err and "BY-NC-ND" in out.err
    assert [s["title"] for s in client.get("/api/songs").json()["songs"]] == ["Track A"]


@pytest.mark.parametrize(
    ("licence", "code"),
    [
        ("BY-NC", "BY-NC"),
        ("BY-NC-SA", "BY-NC-SA"),
        ("CC BY-NC-SA 4.0", "BY-NC-SA"),
        ("CC BY-NC 4.0", "BY-NC"),
        ("BY-NC-ND", None),
        ("BY-ND", None),
        ("BY", None),
        ("BY-SA", None),
        ("CC0", None),
        ("CC BY-NC-ND 4.0", None),
    ],
)
def test_only_by_nc_and_by_nc_sa_are_added(tmp_path, client, capsys, licence, code):
    exit_code = main(["--manifest", _manifest(tmp_path, [_track("Track X", licence)])])

    songs = client.get("/api/songs").json()["songs"]
    if code is None:
        assert exit_code == 1
        assert songs == []
        assert "Track X" in capsys.readouterr().err
    else:
        assert exit_code == 0
        assert [s["licenceCode"] for s in songs] == [code]
        assert all(s["licenceCode"] in ("BY-NC", "BY-NC-SA") for s in songs)


def test_seed_twice_keeps_one_row(tmp_path, client):
    path = _manifest(tmp_path, [_track()])
    assert main(["--manifest", path]) == 0
    path = _manifest(tmp_path, [_track(durationS=100)])
    assert main(["--manifest", path]) == 0

    songs = client.get("/api/songs").json()["songs"]
    assert len(songs) == 1
    assert songs[0]["durationS"] == 100


def test_track_missing_a_field_is_refused(tmp_path, client, capsys):
    bad = _track("Track C")
    del bad["fileKey"]

    assert main(["--manifest", _manifest(tmp_path, [bad])]) == 1
    assert "Track C" in capsys.readouterr().err
    assert client.get("/api/songs").json()["songs"] == []


def test_snake_case_manifest_with_file_name_is_accepted(tmp_path, client):
    track = {
        "file": "a.mp3",
        "title": "Track A",
        "artist": "Artist A",
        "licence": "CC BY-NC 4.0",
        "licence_url": "https://creativecommons.org/licenses/by-nc/4.0/",
        "source_url": URL_A,
        "duration_s": 12.5,
        "credit": "ignored",
    }
    path = tmp_path / "m.json"
    path.write_text(json.dumps([track]))

    assert main(["--manifest", str(path)]) == 0
    assert client.get("/api/songs").json()["songs"][0]["durationS"] == 12.5
