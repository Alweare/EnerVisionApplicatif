from sqlalchemy import func
from sqlalchemy.orm import Session

from core.api.models.prediction import Prediction
from core.api.schemas import PredictionRead
from datetime import datetime
from uuid import UUID
from core.api.models.site import Site
from core.api.models.user import UserSite

class PredictionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_current_by_site(self, site_id: str) -> PredictionRead | None:
        """Prédiction la plus pertinente pour un site.

        La prochaine échéance à venir (`predicted_for >= now()`) si elle existe,
        sinon la plus récente parmi les échéances passées.
        """
        base = self.db.query(Prediction).filter(Prediction.site_id == site_id)

        row = (
            base.filter(Prediction.predicted_for >= func.now())
            .order_by(Prediction.predicted_for.asc())
            .first()
        )
        if row is None:
            row = base.order_by(Prediction.predicted_for.desc()).first()

        return PredictionRead.model_validate(row) if row is not None else None

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
