import sqlite3

from app.config import get_settings
from app.db.schema import TABLES


def test_healthz_answers_200_without_credentials(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_start_creates_the_nine_tables(client):
    connection = sqlite3.connect(get_settings().DATABASE_PATH)
    try:
        rows = connection.execute("select name from sqlite_master where type = 'table'").fetchall()
    finally:
        connection.close()

    assert {name for (name,) in rows} >= set(TABLES)
    assert len(TABLES) == 9
