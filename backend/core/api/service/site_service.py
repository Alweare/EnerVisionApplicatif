from uuid import UUID
from sqlalchemy.orm import Session

from core.api.repository.site_repository import SiteRepository
from core.api.schemas import SiteRead, SiteWithCurrentRead


class SiteNotFoundError(Exception):
    def __init__(self, site_id: str):
        self.site_id = site_id
        super().__init__(f"Site '{site_id}' introuvable")


class SiteService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = SiteRepository(db)

    def list_sites_for_user(
        self, user_id: UUID, active_only: bool = True
    ) -> list[SiteWithCurrentRead]:
        return self.repository.get_by_user(user_id, active_only)

    def list_sites(self) -> list[SiteRead]:
        return self.repository.get_all()

    def get_site(self, site_id: str) -> SiteRead:
        site = self.repository.get_by_id(site_id)
        if site is None:
            raise SiteNotFoundError(site_id)

        return site
