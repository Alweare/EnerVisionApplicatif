from sqlalchemy.orm import Session

from core.api.repository.prediction_repository import PredictionRepository
from core.api.repository.site_repository import SiteRepository
from core.api.schemas import PredictionRead
from core.api.service.site_service import SiteNotFoundError

__all__ = ["PredictionService", "PredictionNotAvailableError", "SiteNotFoundError"]


class PredictionNotAvailableError(Exception):
    def __init__(self, site_id: str):
        self.site_id = site_id
        super().__init__(f"Aucune prédiction disponible pour le site '{site_id}'")


class PredictionService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = PredictionRepository(db)
        self.site_repository = SiteRepository(db)

    def get_prediction(self, site_id: str) -> PredictionRead:
        if not self.site_repository.exists(site_id):
            raise SiteNotFoundError(site_id)

        prediction = self.repository.get_current_by_site(site_id)
        if prediction is None:
            raise PredictionNotAvailableError(site_id)

        return prediction
