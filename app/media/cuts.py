"""Cut detection over PySceneDetect."""

from scenedetect import ContentDetector, detect

from app.media.errors import MediaError


def detect_cuts(video_path: str) -> list[float]:
    """Seconds at which a new scene starts, in order."""
    try:
        scenes = detect(str(video_path), ContentDetector())
    except Exception as exc:
        raise MediaError(str(exc)) from exc
    return [scene[0].get_seconds() for scene in scenes[1:]]
