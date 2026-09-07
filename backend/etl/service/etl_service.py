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

FIELDS_TO_FILL = [
    "consumption_kw", "consumption_kwh", "voltage_v", "current_a",
    "power_factor", "temperature_celsius", "humidity_percent",
]

DEFAULT_FORWARD_FILL_DEPTH = 3

BLOB_PREFIX = "measures/"
# Les alertes ne sont pas rangées par date : le worker écrit à plat.
ALERT_PREFIX = "alert/"
DEFAULT_LOOKBACK_MINUTES = 24 * 60


def cycles_since_real_value(field: str, recents: list) -> int:
    cycles = 0
    for measurement in recents:
        is_real = (
            getattr(measurement, field) is not None
            and field not in (measurement.forward_filled_fields or [])
        )
        if is_real:
            break
        cycles += 1
    return cycles


class ETLService:

    def __init__(self, db: Session):
        self.db = db
        self.measurement_service = MeasurementService(db)
        self.alert_service = AlertService(db)
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
        self.forward_fill_depth = int(
            os.getenv("ETL_FORWARD_FILL_DEPTH", DEFAULT_FORWARD_FILL_DEPTH)
        )

        self.blob_service_client = BlobServiceClient(
            account_url=account_url,
            credential=sas_token
        )

        self.container_client = self.blob_service_client.get_container_client(self.container_name)

    # --- Extraction -------------------------------------------------------

    def _day_prefixes(self, cutoff: datetime, now: datetime) -> list[str]:
        """Préfixes des jours couverts par la fenêtre. Un seul en général,
        deux quand la fenêtre enjambe minuit."""
        prefixes = []
        day = cutoff.date()
        while day <= now.date():
            prefixes.append(f"{BLOB_PREFIX}{day:%Y/%m/%d}/")
            day += timedelta(days=1)
        return prefixes

    def list_recent_blob_paths(self, lookback_minutes: int = None) -> list[str]:
        """Ne liste que les jours de la fenêtre, pas tout le conteneur : le
        coût ne dépend donc plus de l'ancienneté du conteneur."""
        minutes = self.lookback_minutes if lookback_minutes is None else lookback_minutes
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=minutes)

        recent = [
            blob
            for prefix in self._day_prefixes(cutoff, now)
            for blob in self.container_client.list_blobs(name_starts_with=prefix)
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
        """Comble les champs nuls avec la valeur réelle la plus récente.

        Une valeur n'est jamais recopiée plus de forward_fill_depth fois de
        suite : passé ce seuil le champ reste nul, faute de quoi une panne
        durable prolongerait la dernière mesure indéfiniment.
        """
        cleaned = dict(reading)
        cleaned["forward_filled_fields"] = []
        missing_fields = [f for f in FIELDS_TO_FILL if cleaned.get(f) is None]

        if not missing_fields:
            return cleaned

        logger.info(f"[{site_id}] Champs manquants détectés : {missing_fields}")

        recents = self.measurement_service.get_last_measurements(
            site_id, self.forward_fill_depth
        )

        if not recents:
            logger.warning(
                f"[{site_id}] Aucune mesure précédente disponible — "
                f"les champs {missing_fields} restent null."
            )
            return cleaned

        filled, exhausted, still_null = [], [], []
        for field in missing_fields:
            if cycles_since_real_value(field, recents) >= self.forward_fill_depth:
                exhausted.append(field)
                continue

            value = next(
                (v for v in (getattr(m, field) for m in recents) if v is not None),
                None,
            )
            if value is None:
                still_null.append(field)
            else:
                cleaned[field] = value
                filled.append(field)

        cleaned["forward_filled_fields"] = filled

        if filled:
            logger.info(f"[{site_id}] Forward-fill appliqué sur : {filled}")
        if exhausted:
            logger.warning(
                f"[{site_id}] Déjà {self.forward_fill_depth} recopies consécutives — "
                f"restent null : {exhausted}"
            )
        if still_null:
            logger.warning(
                f"[{site_id}] Aucune valeur dans les {self.forward_fill_depth} derniers "
                f"enregistrements — restent null : {still_null}"
            )
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
    def stage_blob(self, blob_path: str) -> int:
        readings = self.download_readings(blob_path)
        loaded = 0

        for reading in readings:
            site_id = reading.get("site_id")

            if not site_id:
                logger.warning(f"[{blob_path}] Lecture ignorée : site_id manquant.")
                continue

            if not self._site_exists(site_id):
                logger.warning(
                    f"[{blob_path}][{site_id}] Site introuvable en BDD. "
                    f"Lecture ignorée."
                )
                continue

            measurement = self.transform(site_id, reading)

            # Filet de sécurité : si le blob a déjà été traité (traçabilité
            # perdue, blob redéposé), la mesure existe déjà en base.
            if self.measurement_service.measurement_exists(
                measurement.site_id, measurement.measurement_date
            ):
                continue

            self.load(measurement)
            loaded += 1

        self.file_tracking_service.mark_processed(blob_path)
        return loaded

    def process_batch(self, blob_paths: list[str]) -> bool:
        staged_files = 0
        staged_measurements = 0

        try:
            for blob_path in blob_paths:
                try:
                    with self.db.begin_nested():
                        staged_measurements += self.stage_blob(blob_path)
                except Exception as e:
                    logger.error(
                        f"[{blob_path}] Fichier en échec, annulé et sauté "
                        f"(sera rejoué) : {e}"
                    )
                    continue
                staged_files += 1

            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(
                "Erreur pendant le lot, transaction annulée : %d fichier(s) "
                "seront rejoués au prochain cycle : %s", staged_files, e,
            )
            return False

        logger.info(
            "Lot validé : %d fichier(s) tracé(s), %d mesure(s) insérée(s).",
            staged_files, staged_measurements,
        )
        return True

    # --- Orchestration ----------------------------------------------------
    #récupère les fichiers récents triés chronologiquement
    # --- Alertes ----------------------------------------------------------
    # Listage à plat : contrairement aux mesures, les blobs d'alertes ne sont
    # pas rangés par jour.
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

    def run(self, lookback_minutes: int = None) -> None:
        recent_paths = self.list_recent_blob_paths(lookback_minutes)

        if not recent_paths:
            return

        new_paths = self.file_tracking_service.filter_new_files(recent_paths)

        logger.info(
            "%d fichier(s) déjà traité(s) ignoré(s), %d à traiter.",
            len(recent_paths) - len(new_paths), len(new_paths),
        )

        if not new_paths:
            return

        self.process_batch(new_paths)

    def start_continuous_run(self, interval: int = 60) -> None:
        logger.info("Démarrage du service ETL")
        while True:
            try:
                self.run()
            except Exception as e:
                logger.error(f"Erreur critique dans le cycle ETL : {e}")

            # try séparé : un échec côté alertes ne doit pas priver les mesures
            # du cycle suivant, et réciproquement.
            try:
                self.run_alerts()
            except Exception as e:
                logger.error(f"Erreur critique dans le cycle des alertes : {e}")
                self.db.rollback()
                self.db.rollback()

            time.sleep(interval)