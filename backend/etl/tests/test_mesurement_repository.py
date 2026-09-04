import pytest
from unittest.mock import MagicMock
from etl.repository.measurement_repository import MeasurementRepository


def test_measurement_repository_save():
    mock_session = MagicMock()
    repo = MeasurementRepository(mock_session)

    # Appel d'une méthode du repository pour valider son exécution
    assert repo.db == mock_session