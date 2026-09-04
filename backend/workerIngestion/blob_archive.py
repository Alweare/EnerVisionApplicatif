import os
import uuid

from azure.storage.blob.aio import ContainerClient

AZURE_STORAGE_ACCOUNT = os.environ.get("AZURE_STORAGE_ACCOUNT")
AZURE_STORAGE_CONTAINER_NAME = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "raw")
AZURE_SAS_INGESTION = os.environ.get("AZURE_SAS_INGESTION")

# Client partagé (pool de connexions réutilisé), même logique que le client
# httpx du repository. Le SAS token est scopé au conteneur (sr=c), donc un
# ContainerClient directement plutôt qu'un BlobServiceClient au niveau compte.
_container_client = ContainerClient.from_container_url(
    f"https://{AZURE_STORAGE_ACCOUNT}.blob.core.windows.net/"
    f"{AZURE_STORAGE_CONTAINER_NAME}?{AZURE_SAS_INGESTION}"
)


async def archive_raw(raw_json: str) -> str:
    """Écrit le JSON brut tel quel dans brute_data/, sans tri ni structure :
    c'est l'ETL qui relira tout et fera le nettoyage/tri à partir du contenu
    de chaque fichier (site_id, timestamp... sont déjà dans le JSON).

    `raw_json` doit être le texte non modifié d'une lecture (pas une
    resérialisation d'un modèle Pydantic) : c'est ce qui garantit qu'aucun
    champ ni valeur `null` n'est perdu par rapport à ce que la Mock API a
    réellement renvoyé.
    """
    blob_name = f"brute_data/{uuid.uuid4()}.json"
    # overwrite=False : un identifiant unique par écriture, donc un conflit de
    # nom ne devrait jamais arriver — et si ça arrive, on veut le savoir plutôt
    # qu'écraser silencieusement une archive déjà écrite.
    await _container_client.upload_blob(name=blob_name, data=raw_json, overwrite=False)
    return blob_name
