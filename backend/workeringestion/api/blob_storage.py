import logging
import os
import uuid
from datetime import datetime, timezone

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob.aio import ContainerClient

logger = logging.getLogger(__name__)

AZURE_STORAGE_ACCOUNT = os.environ.get("AZURE_STORAGE_ACCOUNT")
AZURE_STORAGE_CONTAINER_NAME = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "raw")
AZURE_SAS_INGESTION = os.environ.get("AZURE_SAS_INGESTION")

_container_client = ContainerClient.from_container_url(
    f"https://{AZURE_STORAGE_ACCOUNT}.blob.core.windows.net/"
    f"{AZURE_STORAGE_CONTAINER_NAME}?{AZURE_SAS_INGESTION}"
)

MEASURES_PREFIX = "measures/"

async def archive_raw(raw_json: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    blob_name = f"{MEASURES_PREFIX}{day}/{uuid.uuid4()}.json"
    try:
        await _container_client.upload_blob(name=blob_name, data=raw_json, overwrite=False)
    except ResourceExistsError:
        logger.warning("Blob déjà existant, ignoré : %s", blob_name)
    return blob_name
