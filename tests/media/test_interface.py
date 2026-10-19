import inspect
import io

from PIL import Image

from app.media import errors, service

SIGNATURES = {
    "crop16x9": ["image_bytes"],
    "thumbnail": ["image_bytes", "long_side"],
    "extract_frames": ["clip_path", "per_second"],
    "probe": ["video_path"],
    "assemble": ["clips", "song_path", "song_offset_s", "out_path", "width", "height", "fps"],
    "detect_cuts": ["video_path"],
}


def test_service_exposes_the_six_operations():
    for name, params in SIGNATURES.items():
        assert list(inspect.signature(getattr(service, name)).parameters) == params


def test_media_error_is_the_shared_class():
    assert service.MediaError is errors.MediaError
    assert "MediaError" in service.__all__


def test_valid_input_does_not_raise_not_implemented():
    buf = io.BytesIO()
    Image.new("RGB", (320, 240), "red").save(buf, "JPEG")
    width, height = Image.open(io.BytesIO(service.crop16x9(buf.getvalue()))).size
    assert width / height > 1.7
