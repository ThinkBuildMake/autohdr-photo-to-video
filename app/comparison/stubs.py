"""Stand-ins Comparison borrows until the wiring stories remove them.

detect_cuts stands in for Files.get + Media.detectCuts on the job's video (removed by S22);
presign_download stands in for Files.presignDownload (removed by S25).
"""


def detect_cuts(video_key: str) -> list[float]:
    return []


def presign_download(key: str) -> str:
    return f"/stub-media/{key}"
