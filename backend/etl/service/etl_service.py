from sqlalchemy.orm import Session

from etl.models.measurement import Measurement
from etl.service.measurement_service import MeasurementService

class ETLService:

    def __init__(self, db: Session):
        self.db = db
        self.measurement_service = MeasurementService(db)

    def extract(self, site_id: str) -> list[dict]:
        # todo données Azure Blob (dossier à traiter)
        return []

    def forward_fill(self, site_id: str, reading: dict) -> dict:
        # todo nettoyage des données : si null -> valeur précédente
        return

    def transform(self, site_id: str, reading: dict) -> Measurement:
        cleaned = self.forward_fill(site_id, reading)
        return self.measurement_service.build_measurement(site_id, cleaned)

    def load(self, measurement: Measurement) -> None:
        self.measurement_service.repository.save(measurement)

    # todo à lancer toutes les 60 secs
    def run_for_site(self, site_id: str) -> None:
        for reading in self.extract(site_id):
            measurement = self.transform(site_id, reading)
            self.load(measurement)
#           todo déplacer la ligne azure blob dans dossier traité
