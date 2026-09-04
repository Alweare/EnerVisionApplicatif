from sqlalchemy.orm import Session

from core.api.repository.measurement_repository import MeasurementRepository
from core.api.repository.site_repository import SiteRepository
from core.api.schemas import MeasurementRead
from core.api.service.site_service import SiteNotFoundError

__all__ = ["MeasurementService", "MeasurementNotFoundError", "SiteNotFoundError"]


class MeasurementNotFoundError(Exception):
    def __init__(self, site_id: str):
        self.site_id = site_id
        super().__init__(f"Aucune mesure enregistrée pour le site '{site_id}'")


class MeasurementService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = MeasurementRepository(db)
        self.site_repository = SiteRepository(db)

    def get_current_measurement(self, site_id: str) -> MeasurementRead:
        if not self.site_repository.exists(site_id):
            raise SiteNotFoundError(site_id)

        measurement = self.repository.get_last_by_site(site_id)
        if measurement is None:
            raise MeasurementNotFoundError(site_id)

        return measurement

    def list_measurements(
        self, site_id: str, limit: int, offset: int
    ) -> list[MeasurementRead]:
        if not self.site_repository.exists(site_id):
            raise SiteNotFoundError(site_id)

        return self.repository.list_by_site(site_id, limit=limit, offset=offset)
