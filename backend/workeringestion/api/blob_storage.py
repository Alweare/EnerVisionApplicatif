import logging
import os
import uuid

from azure.core.exceptions import (
    AzureError,
    ClientAuthenticationError,
    ResourceExistsError,
    ResourceNotFoundError,
    ServiceRequestError,
    ServiceResponseError,
)
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

BRUTE_DATA_PATH = "brute_data/"
ALERT_PATH = "alert/"


# Les erreurs sont journalisées ici puis relancées : les avaler ferait loguer
# « Lecture archivée » au poller pour une donnée jamais écrite. L'appelant
# intercepte déjà et poursuit le cycle.
async def _upload(blob_name: str, raw_json: str) -> str:
    try:
        await _container_client.upload_blob(name=blob_name, data=raw_json, overwrite=False)

    # Collision d'UUID4 : le blob est déjà là, l'archivage est acquis.
    except ResourceExistsError:
        logger.warning("Blob déjà existant, ignoré : %s", blob_name)

    except ClientAuthenticationError:
        logger.error(
            "SAS d'ingestion invalide ou expiré, blob non écrit : %s. "
            "Renouveler AZURE_SAS_INGESTION.", blob_name,
        )
        raise

    except ResourceNotFoundError:
        logger.error(
            "Conteneur '%s' introuvable, blob non écrit : %s",
            AZURE_STORAGE_CONTAINER_NAME, blob_name,
        )
        raise

    except (ServiceRequestError, ServiceResponseError) as e:
        logger.error("Azure injoignable, blob non écrit : %s (%s)", blob_name, e)
        raise

    except AzureError:
        logger.exception("Échec d'écriture du blob %s", blob_name)
        raise

    return blob_name


async def archive_raw(raw_json: str) -> str:
    return await _upload(f"{BRUTE_DATA_PATH}{uuid.uuid4()}.json", raw_json)


async def archive_alerts_raw(raw_json: str) -> str:
    return await _upload(f"{ALERT_PATH}{uuid.uuid4()}.json", raw_json)
