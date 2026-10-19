"""Stubs for what Library borrows from other modules, and the preset data other stubs share.

reference_video_url stands in for Files.presignDownload (removed by S21);
check_demo_photoshoot stands in for the Photoshoots table (removed by S25).
STUB_SONG and STUB_STYLES are ids and data that other modules' stubs and tests import.
"""

from app.photoshoots import service as photoshoots
from app.shared.types import Song, Style

GOLDEN_HOUR_ID = "11111111-1111-4111-8111-111111111111"
CRISP_MODERN_ID = "22222222-2222-4222-8222-222222222222"
STUB_SONG_ID = "33333333-3333-4333-8333-333333333333"
STUB_DEMO_PHOTOSHOOT_ID = "44444444-4444-4444-8444-444444444444"
STUB_REFERENCE_JOB_ID = "55555555-5555-4555-8555-555555555555"

STUB_SONG = Song(
    id=STUB_SONG_ID,
    title="Sunrise Walk",
    artist="Example Artist",
    licence_code="BY-NC",
    source_url="stub://songs/sunrise-walk",
    duration_s=120.0,
    credit="Sunrise Walk, Example Artist, CC BY-NC 4.0, stub://songs/sunrise-walk",
)

STUB_STYLES = [
    Style(
        id=GOLDEN_HOUR_ID,
        name="Golden hour",
        author_name="AutoHDR",
        style_text="Slow, warm and unhurried. Open on the front of the house, "
        "move through the main rooms with gentle dolly moves, and finish on a wide exterior.",
        song=STUB_SONG,
        song_offset_s=0.0,
        fps=24,
        demo_photoshoot_id=STUB_DEMO_PHOTOSHOOT_ID,
        reference_job_id=STUB_REFERENCE_JOB_ID,
    ),
    Style(
        id=CRISP_MODERN_ID,
        name="Crisp modern",
        author_name="AutoHDR",
        style_text="Fast and clean. Short shots on the beat, slider moves and quick cuts, "
        "every room shown once.",
        song=STUB_SONG,
        song_offset_s=4.0,
        fps=30,
        demo_photoshoot_id=STUB_DEMO_PHOTOSHOOT_ID,
        reference_job_id=None,
    ),
]


def reference_video_url(job_id: str) -> str:
    return "/stub-media/reference.mp4"


def check_demo_photoshoot(photoshoot_id: str) -> None:
    photoshoots.get_photoshoot(photoshoot_id)
