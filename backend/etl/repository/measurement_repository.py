from sqlalchemy.orm import Session

from etl.models.measurement import Measurement

class MeasurementRepository:
    def __init__(self, db: Session):
        self.db = db

# Ajoute une mesure à la transaction en cours
    def add(self, measurement: Measurement) -> Measurement:
        self.db.add(measurement)
        self.db.flush()
        return measurement

# Renvoie les `limit` dernières mesures du site, la plus récente d'abord.
    def get_last_measurements(self, site_id: str, limit: int) -> list[Measurement]:
        return (
            self.db.query(Measurement)
            .filter(Measurement.site_id == site_id)
            .order_by(Measurement.measurement_date.desc())
            .limit(limit)
            .all()
        )

    def exists(self, site_id: str, measurement_date) -> bool:
        return (
            self.db.query(Measurement.measurement_id)
            .filter(
                Measurement.site_id == site_id,
                Measurement.measurement_date == measurement_date,
            )
            .first()
            is not None
        )
