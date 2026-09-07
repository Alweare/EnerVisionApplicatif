from sqlalchemy.orm import Session

from etl.models.measurement import Measurement
from etl.repository.measurement_repository import MeasurementRepository


class MeasurementService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = MeasurementRepository(db)

    def build_measurement(self, site_id: str, cleaned: dict) -> Measurement:
            return Measurement(
                site_id=site_id,
                measurement_date=cleaned["timestamp"],
                consumption_kw=cleaned["consumption_kw"],
                consumption_kwh=cleaned["consumption_kwh"],
                voltage_v=cleaned["voltage_v"],
                current_a=cleaned["current_a"],
                power_factor=cleaned["power_factor"],
                temperature_celsius=cleaned["temperature_celsius"],
                humidity_percent=cleaned["humidity_percent"],
                null_reason=cleaned["null_reasons"],
                forward_filled_fields=cleaned.get("forward_filled_fields", []),
                data_quality=cleaned["data_quality"],
        )

    def add_measurement(self, measurement: Measurement) -> Measurement:
        return self.repository.add(measurement)

    def get_last_measurements(self, site_id: str, limit: int):
        return self.repository.get_last_measurements(site_id, limit)

    def measurement_exists(self, site_id: str, measurement_date) -> bool:
        return self.repository.exists(site_id, measurement_date)
