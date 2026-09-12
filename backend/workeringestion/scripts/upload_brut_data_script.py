import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from azure.storage.blob.aio import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DAYS_BACK = int(os.getenv("SEED_DAYS_BACK"))

class HistoricalDataSeeder:
    def __init__(self, blob_service_client: BlobServiceClient, container_name: str):
        self.blob_service_client = blob_service_client
        self.container_name = container_name

    def generate_blob_name(self, ref_date: datetime) -> str:
        year = ref_date.strftime("%Y")
        month = ref_date.strftime("%m")
        day = ref_date.strftime("%d")

        return f"measures/{year}/{month}/{day}/{uuid.uuid4()}.json"

    async def archive_raw(self, content: str, blob_name: str):
        container_client = self.blob_service_client.get_container_client(self.container_name)
        blob_client = container_client.get_blob_client(blob_name)
        await blob_client.upload_blob(content, overwrite=True)

    async def fetch_and_archive_range(
            self,
            client: httpx.AsyncClient,
            start_time: datetime,
            end_time: datetime,
            limit: int = 1000
    ) -> int:
        params = {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "limit": limit,
        }

        mock_api_base_url = os.getenv("MOCK_API_URL")
        url = f"{mock_api_base_url}/api/v1/readings"

        try:
            response = await client.get(url, params=params, timeout=60.0)

            if response.status_code == 404:
                logger.warning("Aucune donnée trouvée [%s -> %s]", start_time, end_time)
                return 0

            response.raise_for_status()
            raw_text = response.text

            # Génération du chemin blob
            blob_name = self.generate_blob_name(start_time)

            # Sauvegarde dans Azure Blob Storage
            await self.archive_raw(raw_text, blob_name=blob_name)
            logger.info("Succès : Archivé -> %s (Taille: %d octets)", blob_name, len(raw_text))

            data = response.json()
            return len(data) if isinstance(data, list) else 1

        except httpx.HTTPStatusError as exc:
            logger.exception("Erreur HTTP %s lors de la requête : %s", exc.response.status_code, exc)
            return 0
        except Exception as exc:
            logger.exception("Erreur inattendue : %s", exc)
            return 0

    async def run(self, days_back: int = DAYS_BACK, chunk_hours: int = 24):
        """
        Parcourt les X (DAYS_BACK) derniers jours par tranche de 24h et extrait
        tous les sites en un seul fichier brut par intervalle.
        """
        now = datetime.now(timezone.utc)
        start_global = now - timedelta(days=days_back)

        async with httpx.AsyncClient(timeout=60.0) as client:
            total_processed = 0
            current_start = start_global

            logger.info("--- Début de l'extraction globale (TOUS LES SITES) ---")

            while current_start < now:
                current_end = min(current_start + timedelta(hours=chunk_hours), now)

                count = await self.fetch_and_archive_range(
                    client=client,
                    start_time=current_start,
                    end_time=current_end,
                    limit=1000
                )
                total_processed += count

                # Avancer la fenêtre temporelle
                current_start = current_end
                await asyncio.sleep(0.1)

            logger.info("=== FIN DU TRAITEMENT : %d enregistrements récupérés ===", total_processed)


async def main():
    account_name = os.getenv("AZURE_STORAGE_ACCOUNT")
    sas_token = os.getenv("AZURE_SAS_INGESTION")
    container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME")

    if not account_name or not sas_token:
        raise ValueError("Variables d'environnement AZURE_STORAGE_ACCOUNT ou AZURE_SAS_INGESTION manquantes.")

    account_url = f"https://{account_name}.blob.core.windows.net"

    async with BlobServiceClient(account_url=account_url, credential=sas_token) as blob_service_client:
        seeder = HistoricalDataSeeder(
            blob_service_client=blob_service_client,
            container_name=container_name
        )
        await seeder.run(days_back=DAYS_BACK, chunk_hours=24)


if __name__ == "__main__":
    asyncio.run(main())