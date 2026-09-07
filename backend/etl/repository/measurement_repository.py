from sqlalchemy.orm import Session

from etl.models.measurement import Measurement

class MeasurementRepository:
    def __init__(self, db: Session):
        self.db = db

    def save(self, measurement: Measurement) -> Measurement:
        self.db.add(measurement)
        self.db.commit()
        self.db.refresh(measurement)
        return measurement

    def get_last_measurement(self, site_id: str) -> "Measurement | None":
        return (
            self.db.query(Measurement)
            .filter(Measurement.site_id == site_id)
            .order_by(Measurement.measurement_date.desc())
            .first()
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