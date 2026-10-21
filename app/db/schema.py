"""Create every table. Idempotent; called by app start and worker start."""

from sqlalchemy import inspect, text

from app.db.base import Base, get_engine

TABLES = (
    "songs",
    "styles",
    "photoshoots",
    "photos",
    "jobs",
    "job_shots",
    "attempts",
    "provider_calls",
    "cut_checks",
)


def init_db() -> None:
    from app.comparison import models as _comparison  # noqa: F401
    from app.jobs import models as _jobs  # noqa: F401
    from app.library import models as _library  # noqa: F401
    from app.photoshoots import models as _photoshoots  # noqa: F401
    from app.providers import models as _providers  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(engine)
    # create_all never alters a table: add the column S24 follow-up put on job_shots.
    if "clip_inputs" not in {c["name"] for c in inspect(engine).get_columns("job_shots")}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE job_shots ADD COLUMN clip_inputs TEXT"))
