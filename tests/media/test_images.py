from io import BytesIO

import pytest
from PIL import Image

from app.media.errors import MediaError
from app.media.images import crop16x9, thumbnail


def _jpeg(size, color=(10, 20, 30)) -> bytes:
    out = BytesIO()
    Image.new("RGB", size, color).save(out, format="JPEG")
    return out.getvalue()


def test_crop_4000x3000_to_1920x1080():
    img = Image.open(BytesIO(crop16x9(_jpeg((4000, 3000)))))
    assert img.size == (1920, 1080)
    assert img.format == "JPEG"


def test_thumbnail_keeps_shape():
    img = Image.open(BytesIO(thumbnail(_jpeg((4000, 3000)), 512)))
    assert img.size == (512, 384)
    assert img.format == "JPEG"


def test_crop_portrait_is_16x9():
    img = Image.open(BytesIO(crop16x9(_jpeg((3000, 4000)))))
    assert img.size == (1920, 1080)


def _banded(size, band_box, band=(0, 0, 255), rest=(255, 0, 0)) -> bytes:
    src = Image.new("RGB", size, rest)
    src.paste(band, band_box)
    out = BytesIO()
    src.save(out, format="JPEG", quality=95)
    return out.getvalue()


def _is_blue(px) -> bool:
    r, g, b = px
    return b > 200 and r < 60


def test_crop_is_centre_crop_not_squash():
    # Red top/bottom 375 rows are exactly what a 4:3 -> 16:9 centre crop removes;
    # a squash would leave them visible at the top and bottom edges.
    res = Image.open(BytesIO(crop16x9(_banded((4000, 3000), (0, 375, 4000, 2625)))))
    assert res.size == (1920, 1080)
    for xy in [(960, 5), (960, 1074), (5, 5), (1914, 1074), (960, 540)]:
        assert _is_blue(res.getpixel(xy)), xy


def test_crop_portrait_is_centre_crop_not_squash():
    # Only the centred 3000x1688 band survives the crop of a 3000x4000 image.
    res = Image.open(BytesIO(crop16x9(_banded((3000, 4000), (0, 1156, 3000, 2844)))))
    assert res.size == (1920, 1080)
    for xy in [(960, 5), (960, 1074), (5, 5), (1914, 1074), (960, 540)]:
        assert _is_blue(res.getpixel(xy)), xy


def test_crop_small_image_not_upscaled():
    img = Image.open(BytesIO(crop16x9(_jpeg((800, 800)))))
    assert img.size == (800, 450)


def test_crop_non_image_raises_media_error():
    with pytest.raises(MediaError, match="cannot identify image file"):
        crop16x9(b"not an image")
    with pytest.raises(MediaError, match="cannot identify image file"):
        thumbnail(b"not an image", 512)
