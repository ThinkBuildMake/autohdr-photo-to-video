"""Ids and photos the Jobs stand-in still borrows. S21 removes them."""

from app.shared.types import Photo

STUB_PHOTOSHOOT_ID = "44444444-4444-4444-8444-444444444444"
STUB_PHOTO_IDS = [
    "66666666-6666-4666-8666-666666666601",
    "66666666-6666-4666-8666-666666666602",
]
STUB_LABEL = "12 Oak Street"


def stub_photos() -> list[Photo]:
    rooms = ["exterior_front", "living"]
    return [
        Photo(
            id=photo_id,
            position=index,
            original_name=f"photo-{index + 1}.jpg",
            content_type="image/jpeg",
            size_bytes=2_000_000,
            status="uploaded",
            room=rooms[index],
            subject=f"stub subject {index + 1}",
            thumb_url=f"/stub-media/thumb-{index + 1}.jpg",
        )
        for index, photo_id in enumerate(STUB_PHOTO_IDS)
    ]
