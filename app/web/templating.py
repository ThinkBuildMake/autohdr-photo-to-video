"""Jinja2 templates for the pages."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters["song_line"] = lambda song: (
    f"{song.title} by {song.artist}, CC {song.licence_code}"
)
