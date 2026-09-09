from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.api.models.measurement import Measurement
from core.api.schemas import HistoryPoint, MeasurementRead


class MeasurementRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_hourly_by_site(self, site_id: str, hours: int) -> list[HistoryPoint]:
        """Consommation moyenne par heure sur la fenêtre `hours`.

        La fenêtre est ancrée sur la dernière mesure du site (pas sur `now()`,
        décalé par rapport aux `measurement_date` en heure locale).
        """
        latest = (
            self.db.query(func.max(Measurement.measurement_date))
            .filter(Measurement.site_id == site_id)
            .scalar()
        )
        if latest is None:
            return []

        since = latest - timedelta(hours=hours)
        bucket = func.date_trunc("hour", Measurement.measurement_date)

        rows = (
            self.db.query(
                bucket.label("bucket"),
                func.avg(Measurement.consumption_kw).label("avg_kw"),
            )
            .filter(Measurement.site_id == site_id)
            .filter(Measurement.measurement_date >= since)
            .group_by(bucket)
            .order_by(bucket)
            .all()
        )
        return [
            HistoryPoint(measured_at=row.bucket, consumption_kw=row.avg_kw)
            for row in rows
        ]

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
