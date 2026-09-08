from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.api.schemas import SiteRead
from core.api.service.site_service import SiteNotFoundError, SiteService
from shared.database import get_db
from core.schemas import ErrorDetail

router = APIRouter(prefix="/api/v1/sites", tags=["Sites"])


@router.get(
    "",
    response_model=list[SiteRead],
    summary="Liste des sites",
    description="Retourne tous les sites supervisés, triés par `site_id`.",
)
def list_sites(db: Session = Depends(get_db)) -> list[SiteRead]:
    return SiteService(db).list_sites()


@router.get(
    "/{site_id}",
    response_model=SiteRead,
    summary="Détail d'un site",
    description="Retourne un site par son identifiant.",
    responses={
        404: {
            "model": ErrorDetail,
            "description": "Site inexistant",
        }
    },
)
def get_site(site_id: str, db: Session = Depends(get_db)) -> SiteRead:
    try:
        return SiteService(db).get_site(site_id)
    except SiteNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
