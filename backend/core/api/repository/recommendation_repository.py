from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.api.models.prediction import Prediction
from core.api.models.recommendation import Recommendation
from core.api.models.user import UserSite


class RecommendationRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_for_user(
        self, user_id: UUID, status: str | None = None
    ) -> list[Recommendation]:
        query = (
            self.db.query(Recommendation)
            .join(
                UserSite,
                UserSite.site_id == Recommendation.site_id,
            )
            .filter(UserSite.user_id == user_id)
        )
        if status is not None:
            query = query.filter(Recommendation.status == status)
        return query.order_by(Recommendation.created_at.desc()).all()

    def get(self, recommendation_id: UUID) -> Recommendation | None:
        return (
            self.db.query(Recommendation)
            .filter(Recommendation.recommendation_id == recommendation_id)
            .first()
        )

    def update_status(
        self, recommendation_id: UUID, status: str
    ) -> Recommendation | None:
        recommendation = self.get(recommendation_id)
        if recommendation is None:
            return None
        recommendation.status = status
        self.db.commit()
        self.db.refresh(recommendation)
        return recommendation

    def existing_keys_for_predictions(
        self, prediction_ids: list[UUID]
    ) -> set[tuple[UUID, str]]:
        """Couples (prediction_id, rule_key) déjà présents, pour éviter les doublons."""
        if not prediction_ids:
            return set()
        rows = (
            self.db.query(Recommendation.prediction_id, Recommendation.rule_key)
            .filter(Recommendation.prediction_id.in_(prediction_ids))
            .all()
        )
        return {(prediction_id, rule_key) for prediction_id, rule_key in rows}

    def add_all(self, recommendations: list[dict]) -> int:
        """Insère les recos en ignorant celles déjà émises (index unique prediction_id + rule_key)."""
        if not recommendations:
            return 0
        statement = (
            insert(Recommendation.__table__)
            .values(recommendations)
            .on_conflict_do_nothing(
                index_elements=["prediction_id", "rule_key"]
            )
        )
        result = self.db.execute(statement)
        self.db.commit()
        return result.rowcount
