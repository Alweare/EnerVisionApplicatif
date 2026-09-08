from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from core.api.models.prediction import Prediction
from core.api.models.site import Site
from core.api.models.user import UserSite


class PredictionRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_upcoming_for_user(
        self, user_id: UUID, now: datetime
    ) -> list[tuple[Prediction, Site]]:
        """Prédictions encore à venir pour les sites supervisés par l'utilisateur."""
        return (
            self.db.query(Prediction, Site)
            .join(Site, Site.site_id == Prediction.site_id)
            .join(UserSite, UserSite.site_id == Prediction.site_id)
            .filter(UserSite.user_id == user_id)
            .filter(Prediction.predicted_for >= now)
            .order_by(Prediction.site_id, Prediction.predicted_for)
            .all()
        )
