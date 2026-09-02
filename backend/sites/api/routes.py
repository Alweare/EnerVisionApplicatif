from fastapi import APIRouter, HTTPException

from backend.sites.repository import get_site, list_sites
from backend.sites.schemas import Site

router = APIRouter(prefix="/api/v1/sites", tags=["Sites"])


@router.get("", response_model=list[Site], summary="Liste tous les sites")
async def get_sites() -> list[Site]:
    return list_sites()


@router.get("/{site_id}", response_model=Site, summary="Détail d'un site")
async def get_site_detail(site_id: str) -> Site:
    site = get_site(site_id)
    if site is None:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' introuvable")
    return site
