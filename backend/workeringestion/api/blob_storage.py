import logging
import os
import uuid
from datetime import datetime, timezone
#test
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

_container_client = ContainerClient.from_container_url(
    f"https://{AZURE_STORAGE_ACCOUNT}.blob.core.windows.net/"
    f"{AZURE_STORAGE_CONTAINER_NAME}?{AZURE_SAS_INGESTION}"
)

MEASURES_PREFIX = "measures/"
ALERT_PATH = "alert/"

async def _upload(blob_name: str, raw_json: str) -> str:
    try:
        await _container_client.upload_blob(name=blob_name, data=raw_json, overwrite=False)

    # Collision d'UUID4 : le blob est déjà là, l'archivage est acquis.
    except ResourceExistsError:
        logger.warning("Blob déjà existant, ignoré : %s", blob_name)

    except ClientAuthenticationError:
        logger.exception(
            "SAS d'ingestion invalide ou expiré, blob non écrit : %s. "
            "Renouveler AZURE_SAS_INGESTION.", blob_name,
        )
        raise

    except ResourceNotFoundError:
        logger.exception(
            "Conteneur '%s' introuvable, blob non écrit : %s",
            AZURE_STORAGE_CONTAINER_NAME, blob_name,
        )
        raise

    except (ServiceRequestError, ServiceResponseError) as e:
        logger.exception("Azure injoignable, blob non écrit : %s (%s)", blob_name, e)
        raise

    except AzureError:
        logger.exception("Échec d'écriture du blob %s", blob_name)
        raise

    return blob_name



def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y/%m/%d")


async def archive_raw(raw_json: str) -> str:
    return await _upload(f"{MEASURES_PREFIX}{_day()}/{uuid.uuid4()}.json", raw_json)


async def archive_alerts_raw(raw_json: str) -> str:
    return await _upload(f"{ALERT_PATH}{_day()}/{uuid.uuid4()}.json", raw_json)
