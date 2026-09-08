from sqlalchemy.orm import Session

from core.api.repository.measurement_repository import MeasurementRepository
from core.api.repository.model_repository import ModelRepository
from core.api.repository.prediction_repository import PredictionRepository
from core.api.repository.site_repository import SiteRepository
from core.api.schemas import SitePredictionRead
from core.api.service.site_service import SiteNotFoundError

__all__ = ["PredictionService", "PredictionNotAvailableError", "SiteNotFoundError"]

DEFAULT_HISTORY_LIMIT = 200


class PredictionNotAvailableError(Exception):
    def __init__(self, site_id: str):
        self.site_id = site_id
        super().__init__(f"Aucune prédiction disponible pour le site '{site_id}'")


def _consumption(point) -> float:
    value = point.predicted_consumption_kw
    return value if value is not None else float("-inf")


class PredictionService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = PredictionRepository(db)
        self.site_repository = SiteRepository(db)
        self.measurement_repository = MeasurementRepository(db)
        self.model_repository = ModelRepository(db)

    def get_prediction(
        self, site_id: str, history_limit: int = DEFAULT_HISTORY_LIMIT
    ) -> SitePredictionRead:
        if not self.site_repository.exists(site_id):
            raise SiteNotFoundError(site_id)

        projection = self.repository.list_projection_by_site(site_id)
        if not projection:
            raise PredictionNotAvailableError(site_id)

        history = self.measurement_repository.list_by_site(
            site_id, limit=history_limit, offset=0
        )

        # La projection ne doit couvrir que le futur : on écarte les points
        # antérieurs à la dernière mesure connue (référentiels horaires
        # potentiellement décalés). Repli sur la série complète si le filtre
        # ne laisse rien.
        if history:
            last_measured = max(m.measurement_date for m in history)
            upcoming = [p for p in projection if p.predicted_for > last_measured]
            if upcoming:
                projection = upcoming

        peak = max(projection, key=_consumption)

        model = None
        if peak.model_version is not None:
            model = self.model_repository.get_by_version(peak.model_version)

        return SitePredictionRead(
            site_id=site_id,
            prediction=peak,
            points=projection,
            model=model,
            history=history,
        )
