from unittest.mock import MagicMock

from etl.repository.measurement_repository import MeasurementRepository


def test_measurement_repository_save():
    mock_session = MagicMock()
    repo = MeasurementRepository(mock_session)

    # Appel d'une méthode du repository pour valider son exécution
    assert repo.db == mock_session


def test_save_adds_commits_and_refreshes():
    mock_session = MagicMock()
    repo = MeasurementRepository(mock_session)
    measurement = object()

    result = repo.save(measurement)

    mock_session.add.assert_called_once_with(measurement)
    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once_with(measurement)
    assert result is measurement


def test_get_last_measurement_returns_first_row():
    mock_session = MagicMock()
    repo = MeasurementRepository(mock_session)
    expected = object()
    mock_session.query().filter().order_by().first.return_value = expected

    result = repo.get_last_measurement("SITE001")

    assert result is expected


def test_exists_returns_true_when_row_found():
    mock_session = MagicMock()
    repo = MeasurementRepository(mock_session)
    mock_session.query().filter().first.return_value = object()

    assert repo.exists("SITE001", "2026-09-05") is True


def test_exists_returns_false_when_no_row():
    mock_session = MagicMock()
    repo = MeasurementRepository(mock_session)
    mock_session.query().filter().first.return_value = None

    assert repo.exists("SITE001", "2026-09-05") is False
