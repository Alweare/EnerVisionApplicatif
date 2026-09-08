from unittest.mock import MagicMock

from etl.repository.alert_repository import AlertRepository


def test_add_does_nothing_on_an_empty_batch():
    db = MagicMock()
    repository = AlertRepository(db)

    assert repository.add([]) == 0
    db.execute.assert_not_called()


def test_add_returns_the_number_of_new_rows():
    db = MagicMock()
    db.execute.return_value.rowcount = 1
    repository = AlertRepository(db)

    inserted = repository.add(
        [{"alert_id": "ALR-1", "site_id": "SITE001"}]
    )

    assert inserted == 1
    db.execute.assert_called_once()


def test_add_ignores_alerts_already_in_database():
    db = MagicMock()
    db.execute.return_value.rowcount = 0
    repository = AlertRepository(db)

    repository.add([{"alert_id": "ALR-1", "site_id": "SITE001"}])

    statement = str(db.execute.call_args[0][0])
    assert "ON CONFLICT" in statement.upper()
    assert "DO NOTHING" in statement.upper()
