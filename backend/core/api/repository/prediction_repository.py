from sqlalchemy import func
from sqlalchemy.orm import Session

from core.api.models.prediction import Prediction
from core.api.schemas import PredictionRead
from datetime import datetime
from uuid import UUID
from core.api.models.site import Site
from core.api.models.user import UserSite

# Repli quand aucune échéance future n'est disponible : nombre de dernières
# prédictions connues renvoyées pour ne pas laisser la courbe vide.
_FALLBACK_LIMIT = 24


class PredictionRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_projection_by_site(self, site_id: str) -> list[PredictionRead]:
        """Série des prédictions horaires à venir pour un site.

        Échéances `predicted_for >= now()`, triées par échéance croissante.
        Si aucune échéance future n'existe, renvoie les dernières prédictions
        connues (également en ordre croissant).
        """
        base = self.db.query(Prediction).filter(Prediction.site_id == site_id)

        rows = (
            base.filter(Prediction.predicted_for >= func.now())
            .order_by(Prediction.predicted_for.asc())
            .all()
        )
        if not rows:
            rows = list(
                reversed(
                    base.order_by(Prediction.predicted_for.desc())
                    .limit(_FALLBACK_LIMIT)
                    .all()
                )
            )

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
        return [PredictionRead.model_validate(row) for row in rows]
