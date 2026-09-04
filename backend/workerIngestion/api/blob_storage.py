import logging
import os
import uuid

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob.aio import ContainerClient

logger = logging.getLogger(__name__)

AZURE_STORAGE_ACCOUNT = os.environ.get("AZURE_STORAGE_ACCOUNT")
AZURE_STORAGE_CONTAINER_NAME = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "raw")
AZURE_SAS_INGESTION = os.environ.get("AZURE_SAS_INGESTION")

# SAS scopé au conteneur (sr=c) : ContainerClient direct, pas de
# BlobServiceClient au niveau compte.
_container_client = ContainerClient.from_container_url(
    f"https://{AZURE_STORAGE_ACCOUNT}.blob.core.windows.net/"
    f"{AZURE_STORAGE_CONTAINER_NAME}?{AZURE_SAS_INGESTION}"
)


async def archive_raw(raw_json: str) -> str:
    """Écrit raw_json (texte brut, non reparsé) dans brute_data/."""
    blob_name = f"brute_data/{uuid.uuid4()}.json"
    try:
        await _container_client.upload_blob(name=blob_name, data=raw_json, overwrite=False)
    except ResourceExistsError:
        logger.warning("Blob déjà existant, ignoré : %s", blob_name)
    return blob_name
