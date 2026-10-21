import json

from app.evals.__main__ import main
from app.jobs import drafts
from app.jobs.schemas import JobCreate
from app.photoshoots import service as photoshoots
from tests.evals.conftest import STYLE
from tests.support.evals_rows import _jpeg, add_photoshoot, add_style, make_shoot_folders
from tests.support.library_rows import add_song


def _import(folder, out) -> dict:
    assert main(["import", "--folder", str(folder), "--out", str(out)]) == 0
    return json.loads((out / "shoots.json").read_text())


def test_import_makes_12_shoots_a_job_can_start_on(tmp_path, bucket):
    song = add_song()
    style = add_style(STYLE, song)

    shoots = _import(make_shoot_folders(tmp_path), tmp_path / "out")

    assert list(shoots) == [f"Shoot {n:02d}" for n in range(1, 13)]
    for shoot_id in shoots.values():
        assert photoshoots.get_photoshoot(shoot_id).status == "ready"
        job = drafts.create_job(
            JobCreate(photoshoot_id=shoot_id, style_text="warm", song_id=song, style_id=style)
        )
        assert job.photoshoot_id == shoot_id


def test_importing_again_reuses_the_uploaded_shoots(tmp_path, bucket):
    folder = make_shoot_folders(tmp_path, count=3)
    first = _import(folder, tmp_path / "out")

    assert _import(folder, tmp_path / "again") == first
    assert len(photoshoots.list_photoshoots()) == 3


def test_import_takes_only_jpg_and_png_files(tmp_path, bucket):
    shoot = tmp_path / "shoots" / "Shoot 01"
    shoot.mkdir(parents=True)
    for name in ("a.jpg", "b.JPEG", "c.png", "d.PNG", ".DS_Store", "notes.txt", "e.heic"):
        (shoot / name).write_bytes(_jpeg())

    shoots = _import(shoot.parent, tmp_path / "out")

    photos = photoshoots.get_photoshoot(shoots["Shoot 01"]).photos
    assert sorted(photo.original_name for photo in photos) == ["a.jpg", "b.JPEG", "c.png", "d.PNG"]


def test_duplicate_labels_use_the_newest_ready_shoot_and_say_so(tmp_path, bucket, capsys):
    add_photoshoot("Shoot 01", created_at="2026-10-01T00:00:00.000Z")
    newest = add_photoshoot("Shoot 01", created_at="2026-10-03T00:00:00.000Z")
    add_photoshoot("Shoot 01", created_at="2026-10-02T00:00:00.000Z")

    shoots = _import(make_shoot_folders(tmp_path, count=1), tmp_path / "out")

    assert shoots == {"Shoot 01": newest}
    assert "Shoot 01" in capsys.readouterr().out
