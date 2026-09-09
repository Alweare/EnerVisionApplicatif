"""
Tests de `repository/site_repository.py` (§Sites du besoin).

Même principe que test_measurement_repository.py : pd.read_sql est
monkeypatché, on ne teste jamais une vraie base.
"""

import pandas as pd
import pytest

from prediction.repository import site_repository as repo


@pytest.fixture
def captured(monkeypatch):
    calls = {}

    def fake_read_sql(sql, con):
        calls["sql"] = str(sql)
        return calls.get("_return", pd.DataFrame(columns=["site_id"]))

    monkeypatch.setattr(repo.pd, "read_sql", fake_read_sql)
    return calls


def test_query_filters_on_active_status(captured):
    repo.get_active_site_ids()
    assert "status = 'active'" in captured["sql"]


def test_query_is_ordered_by_site_id(captured):
    repo.get_active_site_ids()
    assert "ORDER BY site_id" in captured["sql"]


def test_returns_list_of_site_ids(monkeypatch):
    monkeypatch.setattr(
        repo.pd, "read_sql", lambda sql, con: pd.DataFrame({"site_id": ["SITE001", "SITE002"]})
    )

    assert repo.get_active_site_ids() == ["SITE001", "SITE002"]


def test_returns_empty_list_when_no_active_site(monkeypatch):
    monkeypatch.setattr(repo.pd, "read_sql", lambda sql, con: pd.DataFrame(columns=["site_id"]))

    assert repo.get_active_site_ids() == []
