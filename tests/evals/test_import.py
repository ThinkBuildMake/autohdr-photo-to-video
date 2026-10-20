import json

from app.evals import stubs
from app.evals.__main__ import main
from tests.support.evals_rows import add_photoshoot, make_shoot_folders


def test_import_makes_12_shoots_and_reuses_the_uploaded_one(tmp_path, monkeypatch):
    folder = make_shoot_folders(tmp_path)
    uploaded = add_photoshoot("Shoot 03")
    imported = []

    def fake_import(paths, label):
        imported.append(label)
        return f"id-{label}"

    monkeypatch.setattr(stubs, "import_photoshoot", fake_import)
    out = tmp_path / "out"

    assert main(["import", "--folder", str(folder), "--out", str(out)]) == 0

    shoots = json.loads((out / "shoots.json").read_text())
    assert len(shoots) == 12
    assert shoots["Shoot 03"] == uploaded
    assert len(imported) == 11
    assert "Shoot 03" not in imported


def test_import_passes_only_jpg_and_png_files(tmp_path, monkeypatch):
    shoot = tmp_path / "shoots" / "Shoot 01"
    shoot.mkdir(parents=True)
    for name in ("a.jpg", "b.JPEG", "c.png", "d.PNG", ".DS_Store", "notes.txt", "e.heic"):
        (shoot / name).write_bytes(b"x")
    passed = []
    monkeypatch.setattr(stubs, "import_photoshoot", lambda paths, label: passed.extend(paths))

    assert main(["import", "--folder", str(shoot.parent), "--out", str(tmp_path / "out")]) == 0

    assert sorted(p.rsplit("/", 1)[-1] for p in passed) == ["a.jpg", "b.JPEG", "c.png", "d.PNG"]
