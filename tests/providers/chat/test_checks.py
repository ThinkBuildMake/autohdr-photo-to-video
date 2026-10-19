import json
import subprocess

import pytest

from app.providers import checks
from app.providers.errors import ProviderError

IDS = {"photoshootId": "ps-1"}

EDIT_CLEAN = {
    "addedObjects": [],
    "removedObjects": [],
    "changedObjects": [],
    "architectureChanged": False,
    "notes": "Only the light changed.",
}
CLIP_CLEAN = {
    "aiScore": 0.1,
    "matchScore": 0.9,
    "peopleCount": 0,
    "addedObjects": [],
    "removedObjects": [],
    "changedObjects": [],
    "notes": "The clip matches the photo.",
}


def run_edit(openrouter, chat_answer, synthetic_jpeg, answer):
    openrouter.answer(json=chat_answer(json.dumps(answer)))
    return checks.check_edit(synthetic_jpeg("tan", "before"), synthetic_jpeg("tan", "after"), IDS)


def run_clip(openrouter, chat_answer, synthetic_jpeg, tmp_path, answer, with_clip=True):
    openrouter.answer(json=chat_answer(json.dumps(answer)))
    clip = tmp_path / "clip.mp4"
    if with_clip:
        clip.write_bytes(b"fake-mp4-bytes")
    frames = [synthetic_jpeg("gray", f"f{i}") for i in range(3)]
    return checks.check_clip(str(clip), frames, synthetic_jpeg("tan", "source"), IDS)


def test_edit_that_removes_a_window_is_caught(openrouter, chat_answer, synthetic_jpeg, rows):
    result = run_edit(
        openrouter,
        chat_answer,
        synthetic_jpeg,
        {
            "addedObjects": [],
            "removedObjects": ["window above the sink"],
            "changedObjects": [],
            "architectureChanged": True,
            "notes": "The window above the sink is gone.",
        },
    )

    assert result.architecture_changed is True
    assert any("window" in item for item in result.removed_objects)
    assert "window" in result.notes
    body = openrouter.body()
    assert body["model"] == "google/gemini-3.8-flash"
    parts = body["messages"][0]["content"]
    assert sum(1 for p in parts if p["type"] == "image_url") == 2
    (row,) = rows()
    assert (row.kind, row.status) == ("check_edit", "ok")


def test_clip_with_a_person_is_flagged(openrouter, chat_answer, synthetic_jpeg, tmp_path, rows):
    result = run_clip(
        openrouter,
        chat_answer,
        synthetic_jpeg,
        tmp_path,
        {
            **CLIP_CLEAN,
            "aiScore": 0.2,
            "peopleCount": 1,
            "notes": "A person with a camera appears in the mirror.",
        },
    )

    assert result.passed is False
    assert result.people_count == 1
    assert "person" in result.notes.lower()
    parts = openrouter.body()["messages"][0]["content"]
    kinds = [p["type"] for p in parts]
    assert kinds.count("video_url") == 1
    assert kinds.count("image_url") == 1 + 3
    video = next(p for p in parts if p["type"] == "video_url")
    assert video["video_url"]["url"].startswith("data:video/mp4;base64,")
    assert kinds.index("image_url") < kinds.index("video_url")
    (row,) = rows()
    assert (row.kind, row.status) == ("check_clip", "ok")


def test_person_prefix_when_notes_do_not_name_one(
    openrouter, chat_answer, synthetic_jpeg, tmp_path
):
    result = run_clip(
        openrouter,
        chat_answer,
        synthetic_jpeg,
        tmp_path,
        {**CLIP_CLEAN, "peopleCount": 2, "notes": "Something odd."},
    )
    assert result.notes.startswith("2 person(s) appear in the clip")


def test_missing_clip_file_sends_frames_only(openrouter, chat_answer, synthetic_jpeg, tmp_path):
    run_clip(openrouter, chat_answer, synthetic_jpeg, tmp_path, CLIP_CLEAN, with_clip=False)
    kinds = [p["type"] for p in openrouter.body()["messages"][0]["content"]]
    assert "video_url" not in kinds
    assert kinds.count("image_url") == 4


@pytest.mark.parametrize(
    "answer",
    [
        {**EDIT_CLEAN, "architectureChanged": False, "removedObjects": ["window"]},
        {**EDIT_CLEAN, "architectureChanged": False, "changedObjects": ["kitchen cabinet"]},
    ],
)
def test_vr5_app_decides_edit(openrouter, chat_answer, synthetic_jpeg, answer):
    assert run_edit(openrouter, chat_answer, synthetic_jpeg, answer).architecture_changed is True


def test_vr5_clean_edit(openrouter, chat_answer, synthetic_jpeg):
    result = run_edit(openrouter, chat_answer, synthetic_jpeg, EDIT_CLEAN)
    assert result.architecture_changed is False


def test_edit_notes_list_items_they_do_not_mention(openrouter, chat_answer, synthetic_jpeg):
    result = run_edit(
        openrouter,
        chat_answer,
        synthetic_jpeg,
        {**EDIT_CLEAN, "addedObjects": ["a lamp"], "notes": "Looks fine."},
    )
    assert result.notes.startswith("Looks fine.")
    assert "added: a lamp" in result.notes


@pytest.mark.parametrize(
    "change",
    [
        {"peopleCount": 1},
        {"changedObjects": ["vent"]},
        {"addedObjects": ["a rug"]},
        {"removedObjects": ["a chair"]},
        {"aiScore": 0.9},
        {"matchScore": 0.1},
    ],
)
def test_vr5_app_decides_clip(openrouter, chat_answer, synthetic_jpeg, tmp_path, change):
    answer = {**CLIP_CLEAN, "passed": True, **change}
    result = run_clip(openrouter, chat_answer, synthetic_jpeg, tmp_path, answer)
    assert result.passed is False


def test_vr5_clean_clip_passes(openrouter, chat_answer, synthetic_jpeg, tmp_path):
    answer = {**CLIP_CLEAN, "passed": False}
    result = run_clip(openrouter, chat_answer, synthetic_jpeg, tmp_path, answer)
    assert result.passed is True


@pytest.mark.parametrize(
    "answer",
    [
        {**EDIT_CLEAN, "removedObjects": "window"},
        {k: v for k, v in EDIT_CLEAN.items() if k != "notes"},
    ],
)
def test_bad_edit_answer_is_bad_response(openrouter, chat_answer, synthetic_jpeg, rows, answer):
    with pytest.raises(ProviderError) as caught:
        run_edit(openrouter, chat_answer, synthetic_jpeg, answer)
    assert caught.value.kind == "bad_response"
    assert rows()[0].status == "error"


@pytest.mark.parametrize(
    "answer",
    [
        {**CLIP_CLEAN, "aiScore": "high"},
        {**CLIP_CLEAN, "peopleCount": 1.5},
        {**CLIP_CLEAN, "addedObjects": None},
        {k: v for k, v in CLIP_CLEAN.items() if k != "matchScore"},
    ],
)
def test_bad_clip_answer_is_bad_response(openrouter, chat_answer, synthetic_jpeg, tmp_path, answer):
    with pytest.raises(ProviderError) as caught:
        run_clip(openrouter, chat_answer, synthetic_jpeg, tmp_path, answer)
    assert caught.value.kind == "bad_response"


@pytest.mark.parametrize(
    ("reply", "kind"),
    [
        ({"status": 500, "json": {"error": {"message": "boom"}}}, "failed"),
        ({"raise_timeout": True}, "timeout"),
    ],
)
def test_check_500_and_timeout(openrouter, synthetic_jpeg, tmp_path, reply, kind):
    openrouter.answer(**reply)
    with pytest.raises(ProviderError) as caught:
        checks.check_edit(synthetic_jpeg(), synthetic_jpeg(), IDS)
    assert caught.value.kind == kind
    openrouter.answer(**reply)
    with pytest.raises(ProviderError) as caught:
        checks.check_clip(str(tmp_path / "none.mp4"), [synthetic_jpeg()], synthetic_jpeg(), IDS)
    assert caught.value.kind == kind


@pytest.mark.live
def test_live_check_edit(live, synthetic_jpeg):
    result = checks.check_edit(
        synthetic_jpeg("tan", "kitchen"), synthetic_jpeg("tan", "kitchen"), IDS
    )
    assert isinstance(result.architecture_changed, bool)


@pytest.mark.live
def test_live_check_clip(live, synthetic_jpeg, tmp_path):
    frames = []
    for i in range(3):
        path = tmp_path / f"f{i}.jpg"
        path.write_bytes(synthetic_jpeg("tan", f"frame {i}"))
        frames.append(path)
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            "1",
            "-i",
            str(tmp_path / "f%d.jpg"),
            "-start_number",
            "0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(clip),
        ],
        check=True,
    )
    result = checks.check_clip(
        str(clip), [p.read_bytes() for p in frames], synthetic_jpeg("tan", "source"), IDS
    )
    assert isinstance(result.passed, bool)


def test_vr5_app_decides(openrouter, chat_answer, synthetic_jpeg, tmp_path):
    edit = {**EDIT_CLEAN, "architectureChanged": False, "removedObjects": ["window"]}
    assert run_edit(openrouter, chat_answer, synthetic_jpeg, edit).architecture_changed is True
    clip = {**CLIP_CLEAN, "passed": True, "peopleCount": 1}
    assert run_clip(openrouter, chat_answer, synthetic_jpeg, tmp_path, clip).passed is False
    clean = run_clip(openrouter, chat_answer, synthetic_jpeg, tmp_path, CLIP_CLEAN)
    assert clean.passed is True
