"""planner_photos hands the planner uploaded photos, in upload order, as JPEGs."""

import io

from PIL import Image

from app.photoshoots import service
from tests.photoshoots.conftest import seed_shoot


def test_planner_photos_returns_uploaded_in_position_order_with_jpeg():
    shoot_id, photo_ids = seed_shoot(
        ["uploaded", "awaiting_upload", "uploaded"], shoot_status="ready"
    )

    photos = service.planner_photos(shoot_id)

    assert [photo["photoId"] for photo in photos] == [photo_ids[0], photo_ids[2]]
    assert [set(photo) for photo in photos] == [{"photoId", "room", "subject", "jpegBytes"}] * 2
    for photo in photos:
        assert Image.open(io.BytesIO(photo["jpegBytes"])).format == "JPEG"
