import os
from unittest.mock import MagicMock

os.environ.setdefault("POSTGRES_DB", "test_db")
os.environ.setdefault("POSTGRES_APP_USER", "test_app_user")
os.environ.setdefault("POSTGRES_APP_PWD", "test_app_pwd")

import shared.database as database


def test_get_db_yields_session_and_closes_it(monkeypatch):
    fake_session = MagicMock()
    monkeypatch.setattr(database, "SessionLocal", lambda: fake_session)

    gen = database.get_db()
    db = next(gen)

    assert db is fake_session
    fake_session.close.assert_not_called()

    gen.close()

    fake_session.close.assert_called_once()
