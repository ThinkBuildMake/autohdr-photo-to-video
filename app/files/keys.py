"""The bucket key layout."""


def photo_key(photoshoot_id: str, photo_id: str, ext: str) -> str:
    if ext not in ("jpg", "png"):
        raise ValueError("ext must be 'jpg' or 'png'")
    return f"photoshoots/{photoshoot_id}/{photo_id}.{ext}"


def frame_key(job_id: str, position: int, round_no: int, name: str) -> str:
    if name not in ("cropped", "edited"):
        raise ValueError("name must be 'cropped' or 'edited'")
    return f"jobs/{job_id}/shots/{position}/r{round_no}/{name}.jpg"


def attempt_clip_key(job_id: str, position: int, round_no: int, attempt_no: int) -> str:
    return f"jobs/{job_id}/shots/{position}/r{round_no}/a{attempt_no}.mp4"


def video_key(job_id: str, version: int) -> str:
    return f"jobs/{job_id}/video-v{version}.mp4"


def song_key(song_id: str, ext: str) -> str:
    return f"songs/{song_id}.{ext}"
