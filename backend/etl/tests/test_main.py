import os
from unittest.mock import patch, MagicMock

os.environ.setdefault("POSTGRES_DB", "test_db")
os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_password")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_APP_USER", "test_app_user")

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