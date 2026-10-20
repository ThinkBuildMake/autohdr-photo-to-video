from app.db.base import session_scope
from app.db.schema import init_db
from app.library import service
from app.library.models import Song

FILE_KEY = "songs/sunrise-walk.mp3"
SONG_ID = "33333333-3333-4333-8333-333333333333"


def test_preview_url_is_a_presigned_get_of_the_song(bucket):
    init_db()
    with session_scope() as session:
        session.add(
            Song(
                id=SONG_ID,
                title="Sunrise Walk",
                artist="Example Artist",
                licence_code="BY-NC",
                source_url="https://example.com/music/sunrise-walk",
                file_key=FILE_KEY,
                duration_s=120.0,
            )
        )

    url = service.song_preview_url(SONG_ID)

    assert url.startswith("https://")
    assert FILE_KEY in url
