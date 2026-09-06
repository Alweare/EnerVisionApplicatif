from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from etl.models.site import Site
from etl.models.measurement import Measurement
from etl.service.file_tracking_service import FileTrackingService
from etl.service.measurement_service import MeasurementService
from azure.storage.blob import BlobServiceClient
import logging
import json
import os
import time

logger = logging.getLogger(__name__)

FIELDS_TO_FILL = [
    "consumption_kw", "consumption_kwh", "voltage_v", "current_a",
    "power_factor", "temperature_celsius", "humidity_percent",
]

BLOB_PREFIX = "brute_data/"
DEFAULT_LOOKBACK_MINUTES = 3


class ETLService:

    def __init__(self, db: Session):
        self.db = db
        self.measurement_service = MeasurementService(db)
        self.file_tracking_service = FileTrackingService(db)

        account_name = os.getenv("AZURE_STORAGE_ACCOUNT")
        sas_token = os.getenv("AZURE_SAS_ETL")
        account_url = f"https://{account_name}.blob.core.windows.net"

        self.container_name = (
            os.getenv("AZURE_STORAGE_CONTAINER_NAME")
        )
        self.lookback_minutes = int(
            os.getenv("ETL_LOOKBACK_MINUTES", DEFAULT_LOOKBACK_MINUTES)
        )

        self.blob_service_client = BlobServiceClient(
            account_url=account_url,
            credential=sas_token
        )

        self.container_client = self.blob_service_client.get_container_client(self.container_name)

    # --- Extraction -------------------------------------------------------

    def list_recent_blob_paths(self, lookback_minutes: int = None) -> list[str]:

        minutes = self.lookback_minutes if lookback_minutes is None else lookback_minutes
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        recent = [
            blob
            for blob in self.container_client.list_blobs(name_starts_with=BLOB_PREFIX)
            if blob.last_modified >= cutoff
        ]
        recent.sort(key=lambda blob: blob.last_modified)

        logger.info(
            "%d fichier(s) déposé(s) depuis %s minute(s) sur Azure.",
            len(recent), minutes,
        )
        return [blob.name for blob in recent]

    def download_readings(self, blob_path: str) -> list[dict]:
        """Télécharge un blob et renvoie ses lectures sous forme de liste."""
        blob_client = self.container_client.get_blob_client(blob_path)
        content = blob_client.download_blob().readall()
        data = json.loads(content)
        return data if isinstance(data, list) else [data]

    # --- Transformation ---------------------------------------------------

    def forward_fill(self, site_id: str, reading: dict) -> dict:
        cleaned = dict(reading)
        missing_fields = [f for f in FIELDS_TO_FILL if cleaned.get(f) is None]

        if not missing_fields:
            return cleaned

        logger.info(f"[{site_id}] Champs manquants détectés : {missing_fields}")

        last = self.measurement_service.get_last_measurement(site_id)

        if last is None:
            logger.warning(
                f"[{site_id}] Aucune mesure précédente disponible — "
                f"les champs {missing_fields} restent null."
            )
            return cleaned

        for field in missing_fields:
            cleaned[field] = getattr(last, field)

        logger.info(f"[{site_id}] Forward-fill appliqué sur : {missing_fields}")
        return cleaned

    def transform(self, site_id: str, reading: dict) -> Measurement:
        cleaned = self.forward_fill(site_id, reading)
        return self.measurement_service.build_measurement(site_id, cleaned)

    # --- Chargement -------------------------------------------------------
    # Ajoute la mesure à la transaction en cours (voir add()).
    def load(self, measurement: Measurement) -> None:
        self.measurement_service.add_measurement(measurement)

    # Vérifie si le site existe en base.
    def _site_exists(self, site_id: str) -> bool:
        return bool(
            self.db.query(Site.site_id).filter(Site.site_id == site_id).scalar()
        )
    # Traite un fichier : téléchargement, transformation, ajout à la transaction.
    def process_blob(self, blob_path: str) -> bool:
        try:
            readings = self.download_readings(blob_path)
        except Exception as e:
            logger.error(f"[{blob_path}] Lecture du blob impossible : {e}")
            return False

        try:
            loaded = 0
            for reading in readings:
                site_id = reading.get("site_id")

                if not site_id:
                    logger.warning(
                        f"[{blob_path}] Lecture ignorée : site_id manquant."
                    )
                    continue

                if not self._site_exists(site_id):
                    logger.warning(
                        f"[{blob_path}][{site_id}] Site introuvable en BDD. "
                        f"Lecture ignorée."
                    )
                    continue

                self.load(self.transform(site_id, reading))
                loaded += 1

            self.file_tracking_service.mark_processed(blob_path)
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(
                f"[{blob_path}] Erreur pendant le traitement, transaction "
                f"annulée (le fichier sera retenté) : {e}"
            )
            return False

        logger.info(f"[{blob_path}] {loaded} mesure(s) insérée(s) et fichier tracé.")
        return True

    # --- Orchestration ----------------------------------------------------
    #récupère les fichiers récents triés chronologiquement
    def run(self, lookback_minutes: int = None) -> None:
        recent_paths = self.list_recent_blob_paths(lookback_minutes)

        if not recent_paths:
            return

        new_paths = self.file_tracking_service.filter_new_files(recent_paths)

        logger.info(
            "%d fichier(s) déjà traité(s) ignoré(s), %d à traiter.",
            len(recent_paths) - len(new_paths), len(new_paths),
        )

        for blob_path in new_paths:
            self.process_blob(blob_path)

    def start_continuous_run(self, interval: int = 60) -> None:
        logger.info("Démarrage du service ETL")
        while True:
            try:
                self.run()
            except Exception as e:
                logger.error(f"Erreur critique dans le cycle ETL : {e}")
                self.db.rollback()

            time.sleep(interval)
