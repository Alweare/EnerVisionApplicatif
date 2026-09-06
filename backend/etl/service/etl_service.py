from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from etl.models.site import Site
from etl.models.measurement import Measurement
from etl.service.alert_service import AlertService
from etl.service.file_tracking_service import FileTrackingService
from etl.service.measurement_service import MeasurementService
from azure.storage.blob import BlobServiceClient
import logging
import json
import os
import time

logger = logging.getLogger(__name__)

ALERT_PREFIX = "alert/"

DEFAULT_LOOKBACK_MINUTES = 24 * 60

FIELDS_TO_FILL = [
    "consumption_kw", "consumption_kwh", "voltage_v", "current_a",
    "power_factor", "temperature_celsius", "humidity_percent",
]

class ETLService:

    def __init__(self, db: Session):
        self.db = db
        self.measurement_service = MeasurementService(db)
        self.alert_service = AlertService(db)
        self.file_tracking_service = FileTrackingService(db)
        self.lookback_minutes = int(
            os.getenv("ETL_LOOKBACK_MINUTES", DEFAULT_LOOKBACK_MINUTES)
        )

        self.container_name = (
            os.getenv("AZURE_STORAGE_CONTAINER_NAME")
        )

        account_name = os.getenv("AZURE_STORAGE_ACCOUNT")
        sas_token = os.getenv("AZURE_SAS_ETL")
        account_url = f"https://{account_name}.blob.core.windows.net"

        self.blob_service_client = BlobServiceClient(
            account_url=account_url,
            credential=sas_token
        )

    def extract_all(self, limit: int = None) -> list[dict]:
        readings = []
        container_client = self.blob_service_client.get_container_client(self.container_name)
        prefix = "brute_data/"

        blobs = [b for b in container_client.list_blobs(name_starts_with=prefix) if not b.name.endswith('/')]

        if limit:
            blobs = blobs[-limit:]

        for blob in blobs:
            blob_client = container_client.get_blob_client(blob.name)
            content = blob_client.download_blob().readall()
            data = json.loads(content)

            items = data if isinstance(data, list) else [data]
            readings.extend(items)

        return readings

    def list_recent_alert_blobs(self, lookback_minutes: int = None) -> list[str]:

        minutes = self.lookback_minutes if lookback_minutes is None else lookback_minutes
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        recent = [
            blob
            for blob in self.container_client.list_blobs(name_starts_with=ALERT_PREFIX)
            if not blob.name.endswith("/") and blob.last_modified >= cutoff
        ]
        recent.sort(key=lambda blob: blob.last_modified)
        return [blob.name for blob in recent]

    def download_alerts(self, blob_path: str) -> list[dict]:
        content = self.container_client.get_blob_client(blob_path).download_blob().readall()
        data = json.loads(content)
        return data if isinstance(data, list) else [data]

    def stage_alert_blob(self, blob_path: str) -> int:
        raw_alerts = self.download_alerts(blob_path)

        known_sites = {site_id for (site_id,) in self.db.query(Site.site_id).all()}
        alerts = [
            self.alert_service.build_alert(raw)
            for raw in raw_alerts
            if self.alert_service.is_valid(raw) and raw["site_id"] in known_sites
        ]

        inserted = self.alert_service.save_all(alerts)
        self.file_tracking_service.mark_processed(blob_path)
        return inserted

    def run_alerts(self, lookback_minutes: int = None) -> int:

        recent_paths = self.list_recent_alert_blobs(lookback_minutes)
        new_paths = self.file_tracking_service.filter_new_files(recent_paths)

        logger.info(
            "Alertes : %d blob(s) dans la fenêtre, %d déjà traité(s), %d à lire.",
            len(recent_paths), len(recent_paths) - len(new_paths), len(new_paths),
        )

        if not new_paths:
            return 0

        inserted = 0
        try:
            for blob_path in new_paths:
                try:
                    with self.db.begin_nested():
                        inserted += self.stage_alert_blob(blob_path)
                except Exception as e:
                    logger.error(f"[{blob_path}] Blob en échec, sauté : {e}")
                    continue

            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"Erreur lors de l'insertion des alertes : {e}")
            return 0

        logger.info("Alertes : %d nouvelle(s) insérée(s).", inserted)
        return inserted

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

    def load(self, measurement: Measurement) -> None:
        self.measurement_service.save_measurement(measurement)

    def run(self, limit: int = None) -> None:
        for reading in self.extract_all(limit=limit):
            site_id = reading.get("site_id")

            if not site_id:
                logger.warning("Objet ignoré : site_id manquant dans la lecture.")
                continue

            site_existant = self.db.query(Site.site_id).filter(Site.site_id == site_id).scalar()

            if not site_existant:
                logger.warning(f"[{site_id}] Site introuvable en BDD. Objet ignoré, passage au suivant.")
                continue

            try:
                measurement = self.transform(site_id, reading)
                self.load(measurement)
            except Exception as e:
                logger.error(f"[{site_id}] Erreur lors du traitement de la mesure : {e}")
                self.db.rollback()
                continue

    def start_continuous_run(self, interval: int = 60) -> None:
        logger.info("Démarrage du service ETL en mode continu...")
        while True:
            try:
                self.run()
            except Exception as e:
                logger.error(f"Erreur critique dans le cycle ETL : {e}")
            try:
                self.run_alerts()
            except Exception as e:
                logger.error(f"Erreur critique dans le cycle des alertes : {e}")
                self.db.rollback()

            time.sleep(interval)