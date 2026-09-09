from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.api.schemas import (
    RecommendationRead,
    RecommendationStatus,
    RecommendationStatusUpdate,
)
from core.api.service.recommendation_service import (
    RecommendationNotFoundError,
    RecommendationService,
)
from core.schemas import ErrorDetail
from core.security import AuthenticatedUser, get_current_user
from shared.database import get_db

router = APIRouter(prefix="/api/v1", tags=["Recommendations"])


@router.get(
    "/me/recommendations",
    summary="Recommandations pour les sites de l'utilisateur connecté",
    description=(
        "Recommandations générées à partir des prédictions de consommation "
        "(pics prévus), pour les sites supervisés par l'utilisateur connecté."
    ),
)
def list_my_recommendations(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    status: RecommendationStatus | None = None,
) -> list[RecommendationRead]:
    return RecommendationService(db).list_for_user(UUID(user.sub), status)


@router.post(
    "/me/recommendations/refresh",
    summary="Recalcule les recommandations de l'utilisateur connecté",
    description=(
        "Applique les règles aux prédictions à venir et insère les nouvelles "
        "recommandations. Idempotent. Retourne le nombre de recos créées."
    ),
)
def refresh_my_recommendations(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> dict[str, int]:
    created = RecommendationService(db).generate_for_user(UUID(user.sub))
    return {"created": created}


@router.patch(
    "/recommendations/{recommendation_id}",
    summary="Met à jour le statut d'une recommandation",
    description="Fait passer une reco de `pending` à `applied` ou `dismissed`.",
    responses={404: {"model": ErrorDetail, "description": "Recommandation inexistante"}},
)
def update_recommendation_status(
    recommendation_id: UUID,
    payload: RecommendationStatusUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> RecommendationRead:
    try:
        return RecommendationService(db).set_status(recommendation_id, payload.status)
    except RecommendationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
