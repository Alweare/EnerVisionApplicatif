from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.api.schemas import SiteWithCurrentRead
from core.api.service.site_service import SiteService
from core.security import AuthenticatedUser, get_current_user
from shared.database import get_db

router = APIRouter(prefix="/api/v1/me", tags=["Me"])


@router.get(
    "/sites",
    summary="Liste des sites de l'utilisateur connecté",
    description="Retourne tous les sites supervisés de l'utilisateur connecté, triés par `site_id`.",
)
def list_sites(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    active_only: bool = True,
) -> list[SiteWithCurrentRead]:
    return SiteService(db).list_sites_for_user(UUID(user.sub), active_only)
