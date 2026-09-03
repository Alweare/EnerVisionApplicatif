import os
import sys

from azure.core.exceptions import HttpResponseError
from azure.storage.blob import ContainerClient
from dotenv import load_dotenv

load_dotenv()

REQUIRED = [
    "AZURE_STORAGE_ACCOUNT",
    "AZURE_SAS_INGESTION",
    "AZURE_SAS_ETL",
    "AZURE_SAS_MLFLOW",
]

TEST_BLOB = "_verify_access.json"
TEST_DATA = b'{"verification": true}'


def get_client(container: str, sas: str) -> ContainerClient:
    account = os.environ["AZURE_STORAGE_ACCOUNT"]
    return ContainerClient(
        account_url=f"https://{account}.blob.core.windows.net",
        container_name=container,
        credential=sas,
    )


def check(label: str, action, should_succeed: bool = True) -> bool:
    """Exécute une action et compare le résultat à ce qui est attendu."""
    try:
        action()
        ok = should_succeed
        detail = "autorisé"
    except HttpResponseError as exc:
        ok = not should_succeed
        detail = f"refusé ({exc.status_code})"

    print(f"  {'[OK]  ' if ok else '[FAIL]'} {label} — {detail}")
    return ok


def main() -> int:
    missing = [v for v in REQUIRED if not os.environ.get(v)]
    if missing:
        print("Variables manquantes dans .env :")
        for v in missing:
            print(f"  - {v}")
        return 1

    account = os.environ["AZURE_STORAGE_ACCOUNT"]
    print(f"\nCompte de stockage : {account}\n")

    ingestion = get_client("raw", os.environ["AZURE_SAS_INGESTION"])
    etl = get_client("raw", os.environ["AZURE_SAS_ETL"])
    mlflow = get_client("mlflow-artifacts", os.environ["AZURE_SAS_MLFLOW"])

    results = []

    results.append(check(
        "ingestion écrit dans raw",
        lambda: ingestion.upload_blob(TEST_BLOB, TEST_DATA, overwrite=True),
    ))

    results.append(check(
        "ETL lit dans raw",
        lambda: etl.download_blob(TEST_BLOB).readall(),
    ))

    results.append(check(
        "ETL ne peut pas écrire dans raw",
        lambda: etl.upload_blob("_interdit.json", TEST_DATA, overwrite=True),
        should_succeed=False,
    ))

    results.append(check(
        "MLflow écrit dans mlflow-artifacts",
        lambda: mlflow.upload_blob(TEST_BLOB, TEST_DATA, overwrite=True),
    ))

    # Nettoyage des blobs de test
    for client in (ingestion, mlflow):
        try:
            client.delete_blob(TEST_BLOB)
        except HttpResponseError:
            pass

    total = len(results)
    passed = sum(results)
    print(f"\n{passed}/{total} vérifications réussies\n")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())