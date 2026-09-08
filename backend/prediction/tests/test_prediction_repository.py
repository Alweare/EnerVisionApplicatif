from contextlib import contextmanager
from datetime import datetime

import pandas as pd
import pytest

from prediction.repository import prediction_repository as repo


class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))


class FakeEngine:
    def __init__(self):
        self.connection = FakeConnection()

    @contextmanager
    def begin(self):
        yield self.connection


def test_record_prediction_inserts_expected_row():
    engine = FakeEngine()
    predicted_for = datetime(2026, 1, 1, 12, 0, 0)

    repo.record_prediction(
        site_id="SITE001",
        predicted_for=predicted_for,
        predicted_consumption_kw=42.5,
        model_version="3",
        engine=engine,
    )

    assert len(engine.connection.calls) == 1
    sql, params = engine.connection.calls[0]
    assert "INSERT INTO ener.prediction" in sql
    assert params == {
        "site_id": "SITE001",
        "predicted_for": predicted_for,
        "predicted_consumption_kw": 42.5,
        "model_version": "3",
    }


@pytest.fixture
def captured(monkeypatch):
    calls = {}

    def fake_read_sql(sql, con, params=None):
        calls["sql"] = str(sql)
        calls["params"] = params
        return calls.get("_return", pd.DataFrame(
            columns=["site_id", "predicted_for", "predicted_consumption_kw", "consumption_kw", "null_reason"]
        ))

    monkeypatch.setattr(repo.pd, "read_sql", fake_read_sql)
    return calls


def test_get_matched_predictions_filters_by_model_version(captured):
    repo.get_matched_predictions("3", engine=object())
    assert captured["params"] == {"model_version": "3"}
    assert "WHERE p.model_version = :model_version" in captured["sql"]


def test_get_matched_predictions_returns_empty_dataframe_when_no_rows(captured):
    result = repo.get_matched_predictions("3", engine=object())
    assert result.empty


def test_get_matched_predictions_excludes_tainted_rows(monkeypatch):
    df = pd.DataFrame(
        {
            "site_id": ["SITE001", "SITE001", "SITE001"],
            "predicted_for": [datetime(2026, 1, 1)] * 3,
            "predicted_consumption_kw": [10.0, 20.0, 30.0],
            "consumption_kw": [11.0, 21.0, 31.0],
            "null_reason": [None, ["consumption_sensor_failure"], ["temperature_sensor_failure"]],
        }
    )
    monkeypatch.setattr(repo.pd, "read_sql", lambda sql, con, params=None: df)

    result = repo.get_matched_predictions("3", engine=object())

    assert len(result) == 2
    assert set(result["predicted_consumption_kw"]) == {10.0, 30.0}


def test_get_matched_predictions_drops_rows_with_missing_actuals(monkeypatch):
    df = pd.DataFrame(
        {
            "site_id": ["SITE001", "SITE001"],
            "predicted_for": [datetime(2026, 1, 1)] * 2,
            "predicted_consumption_kw": [10.0, 20.0],
            "consumption_kw": [11.0, None],
            "null_reason": [None, None],
        }
    )
    monkeypatch.setattr(repo.pd, "read_sql", lambda sql, con, params=None: df)

    result = repo.get_matched_predictions("3", engine=object())

    assert len(result) == 1
