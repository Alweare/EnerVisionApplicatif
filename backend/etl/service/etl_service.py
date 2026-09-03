from sqlalchemy.orm import Session

from etl.models.measurement import Measurement
from etl.service.measurement_service import MeasurementService
import logging

logger = logging.getLogger(__name__)

FIELDS_TO_FILL = [
    "consumption_kw", "consumption_kwh", "voltage_v", "current_a",
    "power_factor", "temperature_celsius", "humidity_percent",
]

class ETLService:

    def __init__(self, db: Session):
        self.db = db
        self.measurement_service = MeasurementService(db)

    def extract(self, site_id: str) -> list[dict]:
        # todo données Azure Blob (dossier à traiter)
        return []

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

    # todo à lancer toutes les 60 secs
    def run_for_site(self, site_id: str) -> None:
        for reading in self.extract(site_id):
            measurement = self.transform(site_id, reading)
            self.load(measurement)
#           todo déplacer la ligne azure blob dans dossier traité
