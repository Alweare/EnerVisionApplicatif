import os
from unittest.mock import patch, MagicMock
from etl.service.etl_service import ETLService


@patch.dict(os.environ, {
    "AZURE_STORAGE_ACCOUNT": "mockaccount",
    "AZURE_SAS_ETL": "mocksastoken"
})
@patch("etl.service.etl_service.BlobServiceClient")
def test_etl_service_azure_connection(mock_blob_client):
    mock_db = MagicMock()

    service = ETLService(mock_db)

    mock_blob_client.assert_called_once_with(
        account_url="https://mockaccount.blob.core.windows.net",
        credential="mocksastoken"
    )