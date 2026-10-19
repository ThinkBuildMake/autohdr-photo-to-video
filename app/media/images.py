"""Image operations over Pillow: 16:9 centre crop and thumbnails."""

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from app.media.errors import MediaError

_W, _H = 1920, 1080
_QUALITY = 92


def _load(image_bytes: bytes) -> Image.Image:
    img = Image.open(BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def _jpeg(img: Image.Image) -> bytes:
    out = BytesIO()
    img.save(out, format="JPEG", quality=_QUALITY)
    return out.getvalue()


def crop16x9(image_bytes: bytes) -> bytes:
    """Centre crop to 16:9, long side at most 1920 px (never upscaled)."""
    try:
        img = _load(image_bytes)
        w, h = img.size
        # Largest centred 16:9 box inside the image.
        if w * _H >= h * _W:
            cw, ch = max(1, round(h * _W / _H)), h
        else:
            cw, ch = w, max(1, round(w * _H / _W))
        if cw >= _W:
            img = ImageOps.fit(img, (_W, _H), method=Image.Resampling.LANCZOS)
        else:
            left, top = (w - cw) // 2, (h - ch) // 2
            img = img.crop((left, top, left + cw, top + ch))
        return _jpeg(img)
    except (UnidentifiedImageError, OSError) as exc:
        raise MediaError(str(exc)) from exc


def thumbnail(image_bytes: bytes, long_side: int) -> bytes:
    """Shrink so the long side is at most long_side, keeping the shape."""
    try:
        img = _load(image_bytes)
        img.thumbnail((long_side, long_side), Image.Resampling.LANCZOS)
        return _jpeg(img)
    except (UnidentifiedImageError, OSError) as exc:
        raise MediaError(str(exc)) from exc
