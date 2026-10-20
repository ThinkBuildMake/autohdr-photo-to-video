"""Files: the module's public interface to the private bucket.

Six blocking operations (callers keep them off the event loop):
presign_upload (15-minute browser upload form), presign_download (1-hour
link, optionally as an attachment), put and get (server-side file copy),
delete_object (remove a key) and head_object (size, or None when the key
is missing), plus the key builders that define the bucket layout.

The bucket is private; every browser read or write goes through a
presigned link. Links, their signatures and policies are never logged.
"""

from app.files.downloads import presign_download
from app.files.keys import (
    attempt_clip_key,
    frame_key,
    photo_key,
    song_key,
    video_key,
)
from app.files.objects import delete_object, get, put
from app.files.uploads import head_object, presign_upload

__all__ = [
    "attempt_clip_key",
    "delete_object",
    "frame_key",
    "get",
    "head_object",
    "photo_key",
    "presign_download",
    "presign_upload",
    "put",
    "song_key",
    "video_key",
]
