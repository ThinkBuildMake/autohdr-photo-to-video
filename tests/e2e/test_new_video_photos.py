import pytest
from playwright.sync_api import expect

from tests.e2e.stubs import ShootStub, drop_files, jpeg, photo
from tests.support.library_rows import stub_presets  # noqa: F401

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("stub_presets")]

MB = 1024 * 1024
THREE_JPEGS = [jpeg("photo-1.jpg"), jpeg("photo-2.jpg"), jpeg("photo-3.jpg")]
BAD_FILES = [jpeg("huge.jpg", 30 * MB), ("walkthrough.mp4", "video/mp4", 5 * MB)]


@pytest.fixture
def new_video(page, live_server):
    page.goto(live_server + "/new")
    return page


def test_dropped_photos_are_uploaded(new_video):
    shoot = ShootStub(new_video, [photo(1), photo(2), photo(3)])

    drop_files(new_video, THREE_JPEGS)

    expect(new_video.locator("#photo-grid .tile")).to_have_count(3)
    assert sorted(shoot.uploaded) == ["photo-1.jpg", "photo-2.jpg", "photo-3.jpg"]
    assert shoot.completed == 1


def test_refused_files_say_why(new_video):
    ShootStub(new_video, [photo(1), photo(2), photo(3)])

    drop_files(new_video, THREE_JPEGS + BAD_FILES)

    refused = new_video.locator("#refused")
    expect(refused).to_contain_text("huge.jpg: too large")
    expect(refused).to_contain_text("walkthrough.mp4: wrong type")
    expect(new_video.locator("#photo-grid .tile")).to_have_count(3)


def test_refused_files_are_never_sent_to_the_bucket(new_video):
    shoot = ShootStub(new_video, [photo(1), photo(2), photo(3)])

    drop_files(new_video, THREE_JPEGS + BAD_FILES)

    expect(new_video.locator("#photo-grid .tile")).to_have_count(3)
    assert sorted(shoot.uploaded) == ["photo-1.jpg", "photo-2.jpg", "photo-3.jpg"]


def test_refused_file_with_the_same_name_as_a_valid_one_is_not_sent(new_video):
    shoot = ShootStub(new_video, [photo(1)])

    drop_files(new_video, [jpeg("a.jpg", 30 * MB), jpeg("a.jpg", 1 * MB)])

    expect(new_video.locator("#photo-grid .tile")).to_have_count(1)
    assert shoot.uploaded == ["a.jpg"]
    assert MB < shoot.upload_sizes[0] < 2 * MB


def test_bucket_failure_still_completes_and_lists_the_photo(new_video):
    missing = {**photo(2), "status": "missing"}
    shoot = ShootStub(new_video, [photo(1), missing], unreachable={"photo-2.jpg"})

    drop_files(new_video, [jpeg("photo-1.jpg"), jpeg("photo-2.jpg")])

    expect(new_video.locator("#refused")).to_contain_text("photo-2.jpg: did not arrive")
    expect(new_video.locator("#photo-grid .tile")).to_have_count(1)
    assert shoot.completed == 1


def test_file_picker_takes_only_jpg_and_png(new_video):
    picker = new_video.get_by_label("Choose photos")

    expect(picker).to_have_attribute("accept", "image/jpeg,image/png")


def test_grid_shows_room_and_subject(new_video):
    photos = [photo(1, "kitchen", "island with pendants"), photo(2, "bedroom", "double bed")]
    ShootStub(new_video, photos)

    drop_files(new_video, [jpeg("photo-1.jpg"), jpeg("photo-2.jpg")])

    tiles = new_video.locator("#photo-grid .tile")
    expect(tiles.nth(0)).to_contain_text("kitchen")
    expect(tiles.nth(0)).to_contain_text("island with pendants")
    expect(tiles.nth(1)).to_contain_text("bedroom")
    expect(tiles.nth(1)).to_contain_text("double bed")


def test_grid_says_rooms_are_not_labelled(new_video):
    ShootStub(new_video, [photo(1), photo(2)], status="label_failed")

    drop_files(new_video, [jpeg("photo-1.jpg"), jpeg("photo-2.jpg")])

    expect(new_video.locator("#label-note")).to_have_text(
        "The rooms are not labelled. The plan will be made from the photos alone."
    )
