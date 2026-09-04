from unittest.mock import patch, MagicMock
from etl.main import main


@patch("etl.main.ETLService")
@patch("etl.main.SessionLocal")
def test_main_runs_etl(mock_session_local, mock_etl_service):
    mock_instance = MagicMock()
    mock_etl_service.return_value = mock_instance

    try:
        main()
    except Exception:
        pass

    mock_etl_service.assert_called_once()
    mock_instance.run.assert_called()