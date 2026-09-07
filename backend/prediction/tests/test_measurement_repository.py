"""
Tests de l'extraction SQL (EN-37).

pd.read_sql est monkeypatché : on ne teste pas Postgres, seulement la requête
construite (colonnes, filtre optionnel, tri chronologique) et ses paramètres.
"""

import pandas as pd
import pytest

from prediction.repository import measurement_repository as repo


@pytest.fixture
def captured(monkeypatch):
    """Intercepte l'appel pd.read_sql et renvoie la requête + les params."""
    calls = {}

    def fake_read_sql(sql, con, params=None):
        calls["sql"] = str(sql)
        calls["params"] = params
        return pd.DataFrame(
            columns=[
                "site_id",
                "measurement_date",
                "consumption_kw",
                "data_quality",
                "null_reason",
            ]
        )

    monkeypatch.setattr(repo.pd, "read_sql", fake_read_sql)
    return calls


def test_query_is_ordered_by_site_then_date(captured):
    repo.get_measurements()
    assert "ORDER BY site_id, measurement_date" in captured["sql"]


def test_query_without_site_has_no_where_clause_and_empty_params(captured):
    repo.get_measurements()
    assert "WHERE" not in captured["sql"]
    assert captured["params"] == {}


def test_query_filters_by_site_when_provided(captured):
    repo.get_measurements("SITE001")
    assert "WHERE site_id = :site_id" in captured["sql"]
    assert captured["params"] == {"site_id": "SITE001"}
    # Le filtre doit venir avant le tri.
    assert captured["sql"].index("WHERE") < captured["sql"].index("ORDER BY")


def test_query_selects_columns_needed_downstream(captured):
    repo.get_measurements()
    for column in ("site_id", "measurement_date", "consumption_kw",
                   "data_quality", "null_reason"):
        assert column in captured["sql"]


def test_returns_a_dataframe(captured):
    assert isinstance(repo.get_measurements(), pd.DataFrame)
