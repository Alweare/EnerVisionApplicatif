from sqlalchemy.orm import Session

from core.api.models.measurement import Measurement
from core.api.schemas import MeasurementRead


class MeasurementRepository:
    """Seule couche autorisée à manipuler l'ORM : renvoie des DTO en sortie."""

    def __init__(self, db: Session):
        self.db = db

    def get_last_by_site(self, site_id: str) -> MeasurementRead | None:
        row = (
            self.db.query(Measurement)
            .filter(Measurement.site_id == site_id)
            .order_by(Measurement.measurement_date.desc())
            .first()
        )
        return MeasurementRead.model_validate(row) if row is not None else None

    def list_by_site(
        self, site_id: str, limit: int, offset: int
    ) -> list[MeasurementRead]:
        rows = (
            self.db.query(Measurement)
            .filter(Measurement.site_id == site_id)
            .order_by(Measurement.measurement_date.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [MeasurementRead.model_validate(row) for row in rows]
