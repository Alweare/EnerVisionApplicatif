import os
import logging
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class AzureBlobCleaner:
    def __init__(self, container_name: str | None = None):
        account_name = os.getenv("AZURE_STORAGE_ACCOUNT")
        sas_token = os.getenv("AZURE_SAS_DELETE")

        if not account_name or not sas_token:
            raise ValueError("Les variables AZURE_STORAGE_ACCOUNT et AZURE_SAS_DELETE doivent être définies.")

        account_url = f"https://{account_name}.blob.core.windows.net"
        self.blob_service_client = BlobServiceClient(
            account_url=account_url,
            credential=sas_token
        )
        self.container_name = container_name or os.getenv("AZURE_CONTAINER_NAME")

    def clean_prefix(self, prefix: str = "brute_data/", dry_run: bool = True):
        """
        Supprime les blobs sous un préfixe donné.
        :param prefix: Le sous-dossier / préfixe à nettoyer.
        :param dry_run: Si True, liste uniquement ce qui serait supprimé sans rien effacer.
        """
        container_name = os.getenv("AZURE_CONTAINER_NAME")

        container_client = self.blob_service_client.get_container_client(container_name)
        logging.info(f"Recherche de blobs avec le préfixe '{prefix}'...")

        blobs = container_client.list_blobs(name_starts_with=prefix)
        count = 0

        for blob in blobs:
            count += 1
            if dry_run:
                logging.info(f"[DRY-RUN] À supprimer : {blob.name}")
            else:
                container_client.delete_blob(blob.name)
                logging.info(f"Supprimé : {blob.name}")

        logging.info(f"Opération terminée. Total blobs impactés : {count}")


if __name__ == "__main__":
    cleaner = AzureBlobCleaner()

    cleaner.clean_prefix(prefix="brute_data/", dry_run=False)