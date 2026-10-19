"""Stand-ins Photoshoots borrows until S20 removes them, plus the old stub data.

Stand-ins: BUCKET (in-memory bucket), presign_upload, presign_download, put, get and
head_object (Files.presignUpload/presignDownload/put/get/headObject), delete_object (a delete
Files lacks), probe and thumbnail (Media.probe/thumbnail) and label_photos
(Providers.labelPhotos). S20 removes them all and calls the real modules.
"""

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


# --- Borrowed stand-ins (S20 removes them) ---------------------------------
BUCKET: dict[str, bytes] = {}


def presign_upload(key: str, content_type: str, max_bytes: int) -> dict:
    return {"url": "/stub-upload", "fields": {"key": key, "Content-Type": content_type}}


def presign_download(key: str, as_attachment: bool = False, filename: str | None = None) -> str:
    return f"/stub-bucket/{key}"


def put(key: str, path: str) -> None:
    with open(path, "rb") as handle:
        BUCKET[key] = handle.read()


def get(key: str, path: str) -> None:
    data = BUCKET[key]
    with open(path, "wb") as handle:
        handle.write(data)


def head_object(key: str) -> dict | None:
    data = BUCKET.get(key)
    return None if data is None else {"sizeBytes": len(data)}


def delete_object(key: str) -> None:
    BUCKET.pop(key, None)


def probe(path: str) -> dict:
    return {"width": 1920, "height": 1080}


def thumbnail(image_bytes: bytes, long_side: int) -> bytes:
    return image_bytes


def label_photos(photos: list[dict], photoshoot_id: str) -> list[dict]:
    return [
        {"photoId": photo["photoId"], "room": "other", "subject": "stub label"} for photo in photos
    ]
