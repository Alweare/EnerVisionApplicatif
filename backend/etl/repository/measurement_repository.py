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