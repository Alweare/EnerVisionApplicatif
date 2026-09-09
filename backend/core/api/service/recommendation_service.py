from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from core.api.models.recommendation import Recommendation
from core.api.repository.prediction_repository import PredictionRepository
from core.api.repository.recommendation_repository import RecommendationRepository
from core.api.service import recommendation_rules

__all__ = ["RecommendationService", "RecommendationNotFoundError"]


class RecommendationNotFoundError(Exception):
    def __init__(self, recommendation_id: UUID):
        self.recommendation_id = recommendation_id
        super().__init__(f"Recommandation '{recommendation_id}' introuvable")


class RecommendationService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = RecommendationRepository(db)
        self.prediction_repository = PredictionRepository(db)

    def list_for_user(
        self, user_id: UUID, status: str | None = None
    ) -> list[Recommendation]:
        return self.repository.list_for_user(user_id, status)

    def set_status(self, recommendation_id: UUID, status: str) -> Recommendation:
        updated = self.repository.update_status(recommendation_id, status)
        if updated is None:
            raise RecommendationNotFoundError(recommendation_id)
        return updated

    def generate_for_user(
        self, user_id: UUID, now: datetime | None = None
    ) -> int:
        """Applique les règles aux prédictions à venir, insère les nouvelles recos.

        Idempotent : une reco déjà émise pour un couple (prédiction, règle) n'est
        pas recréée. Retourne le nombre de recos réellement insérées.
        """
        # `ener.prediction.predicted_for` est un TIMESTAMP sans fuseau : on
        # compare avec un UTC naïf pour éviter tout décalage.
        now = now or datetime.now(tz=timezone.utc).replace(tzinfo=None)
        pairs = self.prediction_repository.list_upcoming_for_user(user_id, now)

        already = self.repository.existing_keys_for_predictions(
            [prediction.prediction_id for prediction, _ in pairs]
        )

        to_insert: list[dict] = []
        for prediction, site in pairs:
            for rule in recommendation_rules.evaluate(prediction, site):
                if (prediction.prediction_id, rule.key) in already:
                    continue
                to_insert.append(
                    {
                        "prediction_id": prediction.prediction_id,
                        "site_id": prediction.site_id,
                        "rule_key": rule.key,
                        "action_type": rule.action_type,
                        "message": rule.message(prediction, site, now),
                        "estimated_gain_kw": rule.estimated_gain_kw(prediction, site),
                        "predicted_for": prediction.predicted_for,
                        "status": "pending",
                    }
                )

        return self.repository.add_all(to_insert)
