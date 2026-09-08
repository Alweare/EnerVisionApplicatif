from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.api.repository.site_repository import SiteRepository
from core.api.schemas import PredictionRead
from core.api.service.model_registry import ConsumptionModel, load_consumption_model
from core.api.service.site_service import SiteNotFoundError

__all__ = ["PredictionService", "ModelNotAvailableError", "SiteNotFoundError"]

ModelLoader = Callable[[], ConsumptionModel | None]


class ModelNotAvailableError(Exception):
    def __init__(self) -> None:
        super().__init__("Aucun modèle de prédiction n'est disponible actuellement")


class PredictionService:
    def __init__(self, db: Session, model_loader: ModelLoader | None = None):
        self.site_repository = SiteRepository(db)
        self._load_model = model_loader or load_consumption_model

    def get_prediction(self, site_id: str) -> PredictionRead:
        if not self.site_repository.exists(site_id):
            raise SiteNotFoundError(site_id)

        model = self._load_model()
        if model is None:
            raise ModelNotAvailableError()

        forecast = model.predict_next(site_id)
        return PredictionRead(
            site_id=site_id,
            predicted_consumption_kw=forecast.predicted_consumption_kw,
            prediction_date=forecast.prediction_date,
            model_name=model.name,
            model_version=model.version,
            generated_at=datetime.now(tz=timezone.utc),
        )
